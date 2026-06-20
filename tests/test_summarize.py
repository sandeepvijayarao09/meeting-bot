import pytest

from meetingbot import config, summarize


class TestTemplateFill:
    def test_fill_replaces_all_tokens(self) -> None:
        out = summarize._fill("A {{X}} B {{Y}} {{X}}", X="1", Y="2")
        assert out == "A 1 B 2 1"

    def test_fill_leaves_unknown_tokens(self) -> None:
        assert summarize._fill("{{UNKNOWN}}", X="1") == "{{UNKNOWN}}"

    def test_prompt_template_has_all_tokens(self) -> None:
        template = config.PROMPT_TEMPLATE.read_text()
        for token in ("{{TITLE}}", "{{DATE}}", "{{DURATION}}", "{{NOTES}}", "{{TRANSCRIPT}}"):
            assert token in template


class TestSplit:
    def test_split_respects_line_boundaries(self) -> None:
        text = "\n".join(f"line {i}" for i in range(100)) + "\n"
        pieces = summarize._split_on_lines(text, 200)
        assert "".join(pieces) == text
        assert all(len(p) <= 210 for p in pieces)
        assert all(p.endswith("\n") for p in pieces)

    def test_split_short_text_single_piece(self) -> None:
        assert summarize._split_on_lines("hello\n", 1000) == ["hello\n"]


class TestApiKeyHandling:
    def test_no_key_raises(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(config, "NVIDIA_API_KEY", "")
        assert not summarize.have_key()
        with pytest.raises(summarize.MissingAPIKeyError, match=r"build\.nvidia\.com"):
            summarize.summarize_meeting("transcript")

    def test_have_key(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(config, "NVIDIA_API_KEY", "nvapi-test")
        assert summarize.have_key()


class TestReasoningKwargs:
    def test_gpt_oss_gets_low_effort(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(config, "NIM_MODEL", "openai/gpt-oss-120b")
        monkeypatch.setattr(config, "NIM_REASONING", "low")
        assert summarize._reasoning_kwargs() == {"reasoning_effort": "low"}

    def test_non_reasoning_model_omits_param(self, monkeypatch: pytest.MonkeyPatch) -> None:
        # llama-3.3-70b rejects reasoning_effort, so it must not be sent.
        monkeypatch.setattr(config, "NIM_MODEL", "meta/llama-3.3-70b-instruct")
        monkeypatch.setattr(config, "NIM_REASONING", "low")
        assert summarize._reasoning_kwargs() == {}

    def test_none_disables_even_for_gpt_oss(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(config, "NIM_MODEL", "openai/gpt-oss-120b")
        monkeypatch.setattr(config, "NIM_REASONING", "none")
        assert summarize._reasoning_kwargs() == {}


class TestGenerateTitle:
    def test_strips_quotes_label_and_punctuation(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(summarize, "complete", lambda *a, **k: 'Title: "Q3 Launch Planning."')
        assert summarize.generate_title("## Summary\n- launch") == "Q3 Launch Planning"

    def test_takes_first_nonempty_line(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(summarize, "complete", lambda *a, **k: "\n\nBilling Rewrite Sync\n")
        assert summarize.generate_title("notes") == "Billing Rewrite Sync"

    def test_empty_source_skips_call(self, monkeypatch: pytest.MonkeyPatch) -> None:
        called = False

        def boom(*a: object, **k: object) -> str:
            nonlocal called
            called = True
            return "x"

        monkeypatch.setattr(summarize, "complete", boom)
        assert summarize.generate_title("", "") == ""
        assert not called

    def test_api_failure_returns_empty(self, monkeypatch: pytest.MonkeyPatch) -> None:
        def boom(*a: object, **k: object) -> str:
            raise RuntimeError("network down")

        monkeypatch.setattr(summarize, "complete", boom)
        assert summarize.generate_title("some notes") == ""


class TestSummarizeMeeting:
    def test_single_call_embeds_everything(self, monkeypatch: pytest.MonkeyPatch) -> None:
        prompts: list[str] = []

        def fake_chat(content: str, max_tokens: int = 3000) -> str:
            prompts.append(content)
            return "## Summary\n- ok"

        monkeypatch.setattr(summarize, "_chat", fake_chat)
        result = summarize.summarize_meeting(
            "THE_TRANSCRIPT", user_notes="MY_NOTES", title="Sync", date="2026-06-12"
        )
        assert result == "## Summary\n- ok"
        assert len(prompts) == 1
        assert "THE_TRANSCRIPT" in prompts[0]
        assert "MY_NOTES" in prompts[0]
        assert "Sync" in prompts[0]

    def test_empty_notes_shows_none(self, monkeypatch: pytest.MonkeyPatch) -> None:
        prompts: list[str] = []
        monkeypatch.setattr(summarize, "_chat", lambda c, max_tokens=3000: prompts.append(c) or "x")
        summarize.summarize_meeting("t", user_notes="  ")
        assert "(none)" in prompts[0]

    def test_long_transcript_map_reduces(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(summarize, "MAX_DIRECT_CHARS", 100)
        monkeypatch.setattr(summarize, "PIECE_CHARS", 60)
        calls: list[str] = []

        def fake_chat(content: str, max_tokens: int = 3000) -> str:
            calls.append(content)
            return "condensed minutes"

        monkeypatch.setattr(summarize, "_chat", fake_chat)
        long_transcript = "\n".join(f"**Me** [00:0{i % 10}]: blah blah" for i in range(20))
        summarize.summarize_meeting(long_transcript)
        # several condense calls + one final summary call
        assert len(calls) > 2
        assert "condensed minutes" in calls[-1]
        assert summarize.CONDENSE_PROMPT[:30] in calls[0]
