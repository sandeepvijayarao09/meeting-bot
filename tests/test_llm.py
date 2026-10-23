"""Backend selection, availability, and dispatch for the generation seam.

Availability is the interesting part. Everything downstream — summaries, Ask,
the cloud refine tier, transforms — asks `is_available()` to decide between a
real summary and a transcript-only note. Getting it wrong in the optimistic
direction turns a graceful degrade into a failed meeting note, so each backend's
notion of "ready" is pinned here: a key for cloud, weights on disk for local,
and never for `none`.

No test here loads a model or opens a socket.
"""

from __future__ import annotations

from typing import Any

import pytest

from meetingbot import config, llm


@pytest.fixture(autouse=True)
def _no_cached_model(monkeypatch: pytest.MonkeyPatch) -> None:
    """Keep the process-wide model cache out of the tests."""
    monkeypatch.setattr(llm, "_loaded", None)


# ------------------------------------------------------------- availability


def test_local_is_available_only_with_weights(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(config, "LLM_BACKEND", "local")
    monkeypatch.setattr(llm, "local_model_ready", lambda: True)
    assert llm.is_available() is True
    monkeypatch.setattr(llm, "local_model_ready", lambda: False)
    assert llm.is_available() is False


def test_local_needs_no_api_key(monkeypatch: pytest.MonkeyPatch) -> None:
    """The whole point of on-device: no key, no account, no vendor."""
    monkeypatch.setattr(config, "LLM_BACKEND", "local")
    monkeypatch.setattr(config, "LLM_API_KEY", "")
    monkeypatch.setattr(llm, "local_model_ready", lambda: True)
    assert llm.is_available() is True


def test_cloud_is_available_only_with_a_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(config, "LLM_BACKEND", "cloud")
    monkeypatch.setattr(config, "LLM_API_KEY", "k")
    assert llm.is_available() is True
    monkeypatch.setattr(config, "LLM_API_KEY", "")
    assert llm.is_available() is False


def test_none_is_never_available(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(config, "LLM_BACKEND", "none")
    monkeypatch.setattr(config, "LLM_API_KEY", "k")
    monkeypatch.setattr(llm, "local_model_ready", lambda: True)
    assert llm.is_available() is False


def test_local_readiness_tracks_the_model_cache(monkeypatch: pytest.MonkeyPatch) -> None:
    """`local_model_ready` must ask about the configured Gemma repo, not Whisper."""
    from meetingbot import models

    asked: list[str] = []

    def fake(repo: str | None = None) -> bool:
        asked.append(repo or "")
        return True

    monkeypatch.setattr(models, "is_downloaded", fake)
    monkeypatch.setattr(config, "GEMMA_MODEL", "mlx-community/gemma-4-e4b-it-4bit")
    assert llm.local_model_ready() is True
    assert asked == ["mlx-community/gemma-4-e4b-it-4bit"]


# ----------------------------------------------------------------- dispatch


def test_complete_refuses_when_disabled(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(config, "LLM_BACKEND", "none")
    with pytest.raises(llm.LLMUnavailableError, match="disabled"):
        llm.complete("sys", "user")


def test_complete_routes_to_local_by_default(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(config, "LLM_BACKEND", "local")
    seen: dict[str, Any] = {}

    def fake(system: str, user: str, max_tokens: int, temperature: float) -> str:
        seen.update(system=system, user=user, max_tokens=max_tokens, temperature=temperature)
        return "local answer"

    monkeypatch.setattr(llm, "_complete_local", fake)
    assert llm.complete("S", "U", max_tokens=64, temperature=0.5) == "local answer"
    assert seen == {"system": "S", "user": "U", "max_tokens": 64, "temperature": 0.5}


def test_complete_routes_to_cloud_when_selected(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(config, "LLM_BACKEND", "cloud")
    monkeypatch.setattr(llm, "_complete_cloud", lambda *a: "cloud answer")
    assert llm.complete("S", "U") == "cloud answer"


def test_local_complete_refuses_without_weights(monkeypatch: pytest.MonkeyPatch) -> None:
    """Fail with the fix, rather than letting mlx-lm raise something opaque."""
    monkeypatch.setattr(llm, "local_model_ready", lambda: False)
    with pytest.raises(llm.LLMUnavailableError, match="download-model --llm"):
        llm._complete_local("S", "U", 16, 0.2)


def test_cloud_complete_refuses_without_a_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(config, "LLM_API_KEY", "")
    with pytest.raises(llm.LLMUnavailableError, match="LLM_API_KEY"):
        llm._complete_cloud("S", "U", 16, 0.2)


# ------------------------------------------------------------ prompt render


class _Tokenizer:
    """Chat template that accepts a system turn and returns a string."""

    def apply_chat_template(self, messages: list[dict[str, str]], **_: Any) -> str:
        return "|".join(f"{m['role']}:{m['content']}" for m in messages)

    def decode(self, ids: Any) -> str:  # pragma: no cover - not reached for str
        return str(ids)


class _NoSystemTokenizer(_Tokenizer):
    """Gemma's template historically rejects a system turn."""

    def apply_chat_template(self, messages: list[dict[str, str]], **kw: Any) -> str:
        if any(m["role"] == "system" for m in messages):
            raise ValueError("System role not supported")
        return super().apply_chat_template(messages, **kw)


def test_render_uses_the_system_turn_when_supported() -> None:
    assert llm._render_prompt(_Tokenizer(), "SYS", "USR") == "system:SYS|user:USR"


def test_render_folds_system_into_user_when_rejected() -> None:
    """Losing the system prompt entirely would quietly degrade every summary."""
    out = llm._render_prompt(_NoSystemTokenizer(), "SYS", "USR")
    assert out == "user:SYS\n\nUSR"
    assert "SYS" in out and "USR" in out


def test_render_decodes_token_ids() -> None:
    class _IdsTokenizer(_Tokenizer):
        def apply_chat_template(self, messages: list[dict[str, str]], **_: Any) -> list[int]:
            return [1, 2, 3]

        def decode(self, ids: Any) -> str:
            return f"decoded{ids}"

    assert llm._render_prompt(_IdsTokenizer(), "S", "U") == "decoded[1, 2, 3]"


# --------------------------------------------------------- reasoning strip


class TestStripReasoning:
    """Gemma 4 thinks out loud before answering, in channel tokens.

    Shipped unstripped, the chain of thought landed verbatim in the user's note and
    `generate_title` turned its first line into the title *and* the filename
    (`2026-10-22-2308-channel-thought.md`). Only a real end-to-end summary surfaced
    it, so these pin it shut.
    """

    def test_keeps_only_the_answer(self) -> None:
        raw = "<|channel>thought\nThinking Process:\n1. Analyze...<channel|>## Summary\n- a point"
        assert llm.strip_reasoning(raw) == "## Summary\n- a point"

    def test_uses_the_last_terminator(self) -> None:
        """A model that re-enters thinking must not smuggle the earlier block out."""
        raw = "<|channel>a<channel|>draft<|channel>b<channel|>final answer"
        assert llm.strip_reasoning(raw) == "final answer"

    def test_unterminated_thought_yields_nothing(self) -> None:
        """Out of tokens mid-thought: there is no answer, so do not pass off reasoning."""
        assert llm.strip_reasoning("<|channel>thought\nStill thinking and then cut") == ""
        assert llm.strip_reasoning("  <|think|>pondering") == ""

    def test_plain_output_is_untouched(self) -> None:
        assert llm.strip_reasoning("## Summary\n- a point") == "## Summary\n- a point"

    def test_stray_markers_are_removed(self) -> None:
        assert llm.strip_reasoning("<channel|>answer <|channel> tail") == "answer  tail"

    def test_titles_never_start_with_a_channel_token(self) -> None:
        """The exact regression: the title came from the thinking block's first line."""
        raw = "<|channel>thought\nI should title this...<channel|>Q3 Launch Planning"
        assert llm.strip_reasoning(raw) == "Q3 Launch Planning"
        assert "channel" not in llm.strip_reasoning(raw)


def test_local_generation_strips_reasoning(monkeypatch: pytest.MonkeyPatch) -> None:
    """End to end through _complete_local, where the leak actually happened."""
    monkeypatch.setattr(llm, "local_model_ready", lambda: True)
    monkeypatch.setattr(llm, "_load_local", lambda: (object(), _Tokenizer()))
    monkeypatch.setattr(llm, "_render_prompt", lambda *a: "prompt")

    import sys
    import types

    fake = types.ModuleType("mlx_lm")
    fake.generate = lambda *a, **k: "<|channel>thinking hard<channel|>THE ANSWER"  # type: ignore[attr-defined]
    sample_utils = types.ModuleType("mlx_lm.sample_utils")
    sample_utils.make_sampler = lambda **k: None  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "mlx_lm", fake)
    monkeypatch.setitem(sys.modules, "mlx_lm.sample_utils", sample_utils)

    assert llm._complete_local("S", "U", 128, 0.2) == "THE ANSWER"


def test_token_budget_leaves_room_for_thinking(monkeypatch: pytest.MonkeyPatch) -> None:
    """Reasoning spends from the same budget; without headroom the answer is cut off."""
    monkeypatch.setattr(llm, "local_model_ready", lambda: True)
    monkeypatch.setattr(llm, "_load_local", lambda: (object(), _Tokenizer()))
    monkeypatch.setattr(llm, "_render_prompt", lambda *a: "prompt")
    monkeypatch.setattr(config, "GEMMA_THINKING_HEADROOM", 999)
    seen: dict[str, Any] = {}

    import sys
    import types

    fake = types.ModuleType("mlx_lm")

    def gen(*a: Any, **k: Any) -> str:
        seen.update(k)
        return "answer"

    fake.generate = gen  # type: ignore[attr-defined]
    sample_utils = types.ModuleType("mlx_lm.sample_utils")
    sample_utils.make_sampler = lambda **k: None  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "mlx_lm", fake)
    monkeypatch.setitem(sys.modules, "mlx_lm.sample_utils", sample_utils)

    llm._complete_local("S", "U", 100, 0.2)
    assert seen["max_tokens"] == 100 + 999


# ------------------------------------------------------------------ describe


def test_describe_names_the_on_device_model(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(config, "LLM_BACKEND", "local")
    monkeypatch.setattr(config, "GEMMA_MODEL", "mlx-community/gemma-4-e4b-it-4bit")
    assert "gemma-4-e4b-it-4bit" in llm.describe()
    assert "on device" in llm.describe()


def test_describe_names_the_cloud_endpoint(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(config, "LLM_BACKEND", "cloud")
    monkeypatch.setattr(config, "LLM_MODEL", "gemma-4-e4b-it")
    monkeypatch.setattr(config, "LLM_BASE_URL", "https://example.test/v1")
    assert llm.describe() == "gemma-4-e4b-it via https://example.test/v1"


def test_describe_when_disabled(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(config, "LLM_BACKEND", "none")
    assert "disabled" in llm.describe()


def test_no_vendor_is_hard_coded() -> None:
    """The point of the change: nothing in the seam names a specific vendor."""
    source = (__import__("pathlib").Path(llm.__file__)).read_text().lower()
    assert "nvidia" not in source
    assert "nvapi" not in source
