"""The text-generation backend behind summaries, Ask, refinement, and transforms.

Default is **local Gemma 4 via MLX** — on device, no API key, no network, no
vendor. That is the whole point: the product's claim is that a meeting never
leaves your Mac, and routing finished transcripts to someone's cloud was the one
place that claim leaked.

A `cloud` backend remains, deliberately provider-neutral (any OpenAI-compatible
`base_url` + model, e.g. Google AI Studio serving Gemma). It is no longer the
default and nothing hard-codes a vendor.

Everything funnels through :func:`complete`, which is the only place a request is
made; `summarize`, `ask`, `refine` and `transform` all call it.

The model is **not bundled** — see `models.py`. On-device generation is slower
than a datacenter and the 4B-class E4B is weaker than a 100B-class hosted model,
which is the trade being made for privacy and for not needing a key at all.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from . import config

if TYPE_CHECKING:
    from openai import OpenAI


class LLMUnavailableError(RuntimeError):
    """No usable backend: the local model is missing, or cloud has no key."""


def backend() -> str:
    """Which backend is selected: ``local``, ``cloud`` or ``none``."""
    return config.LLM_BACKEND


# --------------------------------------------------------------- local (MLX)

# Loading Gemma costs seconds and gigabytes of RAM, and a single `mbot process`
# run completes several times (summary, title, maybe a refine pass). Hold the
# loaded model for the life of the process; callers are short-lived CLI runs.
_loaded: tuple[Any, Any] | None = None


def _load_local() -> tuple[Any, Any]:
    global _loaded
    if _loaded is None:
        from mlx_lm import load

        # load() returns (model, tokenizer) and, for some repos, a third config
        # element — take the first two rather than unpacking a fixed arity.
        loaded = load(config.GEMMA_MODEL)
        _loaded = (loaded[0], loaded[1])
    return _loaded


# Gemma 4 is a reasoning model: it emits its chain of thought in a channel block
# before the answer. Left in, that block lands verbatim in the user's note — and
# `generate_title` happily turns its first line into the note's title and filename
# ("<|channel>thought"). These are real tokenizer tokens, not prose.
_THOUGHT_END = "<channel|>"
_THOUGHT_START = "<|channel>"
_THINK = "<|think|>"


def strip_reasoning(text: str) -> str:
    """Drop the model's thinking block, keeping only the answer it finally gave.

    Thinking measurably improves the summaries, so it stays enabled and is removed
    here instead. Everything before the *last* channel terminator is reasoning; a
    block that never terminates means the model ran out of tokens mid-thought, and
    there is no answer to salvage.
    """
    if _THOUGHT_END in text:
        text = text.rsplit(_THOUGHT_END, 1)[1]
    elif text.lstrip().startswith((_THOUGHT_START, _THINK)):
        return ""
    return text.replace(_THOUGHT_START, "").replace(_THINK, "").strip()


def _render_prompt(tokenizer: Any, system: str, user: str) -> str:
    """Apply the chat template, tolerating templates with no system role.

    Gemma's template historically rejects a `system` turn, so fall back to
    folding the system prompt into the user turn rather than failing the request.
    """
    messages = [{"role": "system", "content": system}, {"role": "user", "content": user}]
    try:
        rendered = tokenizer.apply_chat_template(messages, add_generation_prompt=True)
    except Exception:
        merged = [{"role": "user", "content": f"{system}\n\n{user}"}]
        rendered = tokenizer.apply_chat_template(merged, add_generation_prompt=True)
    # Templates may return token ids or a string depending on the tokenizer.
    if isinstance(rendered, str):
        return rendered
    return str(tokenizer.decode(rendered))


def _complete_local(system: str, user: str, max_tokens: int, temperature: float) -> str:
    if not local_model_ready():
        raise LLMUnavailableError(
            f"{config.GEMMA_MODEL} is not downloaded. Fetch it once with:\n"
            "    mbot download-model --llm"
        )
    from mlx_lm import generate
    from mlx_lm.sample_utils import make_sampler

    model, tokenizer = _load_local()
    text = generate(
        model,
        tokenizer,
        prompt=_render_prompt(tokenizer, system, user),
        # Reasoning tokens are spent before the answer begins, so the cap has to
        # cover both or the answer is truncated away entirely.
        max_tokens=max_tokens + config.GEMMA_THINKING_HEADROOM,
        sampler=make_sampler(temp=temperature),
        verbose=False,
    )
    return strip_reasoning(str(text))


def local_model_ready() -> bool:
    """True when the Gemma weights are cached locally."""
    from . import models

    return models.is_downloaded(config.GEMMA_MODEL)


# --------------------------------------------------- cloud (OpenAI-compatible)


def _client() -> OpenAI:
    if not config.LLM_API_KEY:
        raise LLMUnavailableError(
            "LLM_API_KEY is not set for the cloud backend. Either set it, or use the "
            "default on-device backend (MBOT_LLM_BACKEND=local)."
        )
    from openai import OpenAI

    # Bound the request: the SDK default (600s) can hang Stop→"Processing…" for ten
    # minutes. One retry keeps the worst case ~2x the timeout.
    return OpenAI(
        base_url=config.LLM_BASE_URL,
        api_key=config.LLM_API_KEY,
        timeout=config.LLM_TIMEOUT,
        max_retries=1,
    )


def _complete_cloud(system: str, user: str, max_tokens: int, temperature: float) -> str:
    resp = _client().chat.completions.create(
        model=config.LLM_MODEL,
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        temperature=temperature,
        max_tokens=max_tokens,
    )
    return (resp.choices[0].message.content or "").strip()


# --------------------------------------------------------------------- public


def is_available() -> bool:
    """True when a summary can actually be produced right now.

    Callers use this to degrade to a transcript-only note instead of failing, so
    it must answer for the *selected* backend rather than in general.
    """
    if config.LLM_BACKEND == "none":
        return False
    if config.LLM_BACKEND == "cloud":
        return bool(config.LLM_API_KEY)
    return local_model_ready()


def describe() -> str:
    """One line for `mbot doctor`."""
    if config.LLM_BACKEND == "none":
        return "disabled (transcript-only notes)"
    if config.LLM_BACKEND == "cloud":
        return f"{config.LLM_MODEL} via {config.LLM_BASE_URL}"
    return f"{config.GEMMA_MODEL} (on device, MLX)"


def complete(
    system_prompt: str, user_prompt: str, max_tokens: int = 4096, temperature: float = 0.2
) -> str:
    """One completion from the selected backend."""
    if config.LLM_BACKEND == "none":
        raise LLMUnavailableError("The LLM backend is disabled (MBOT_LLM_BACKEND=none).")
    if config.LLM_BACKEND == "cloud":
        return _complete_cloud(system_prompt, user_prompt, max_tokens, temperature)
    return _complete_local(system_prompt, user_prompt, max_tokens, temperature)


def ping() -> str:
    """Cheap round-trip so `doctor` can prove the backend actually answers."""
    return complete("You are a health check.", "Reply with the single word: ok", max_tokens=16)
