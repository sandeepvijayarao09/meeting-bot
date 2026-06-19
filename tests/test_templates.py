import pytest

from meetingbot import config, summarize


class TestTemplateResolution:
    def test_default_resolves_to_general(self) -> None:
        assert config.resolve_template("default") == config.PROMPT_TEMPLATE
        assert config.resolve_template(None) == config.PROMPT_TEMPLATE

    def test_known_templates_exist(self) -> None:
        for name in ("standup", "one_on_one", "interview", "sales_call"):
            path = config.resolve_template(name)
            assert path.exists()
            assert path.name == f"{name}.md"

    def test_unknown_template_falls_back(self) -> None:
        assert config.resolve_template("nonsense") == config.PROMPT_TEMPLATE


class TestSummarizeUsesTemplate:
    def test_selected_template_text_is_used(self, monkeypatch: pytest.MonkeyPatch) -> None:
        prompts: list[str] = []
        monkeypatch.setattr(
            summarize, "_chat", lambda content, max_tokens=3000: prompts.append(content) or "ok"
        )
        summarize.summarize_meeting("**Me** [00:00]: hi", template="standup")
        # The standup template has distinctive section headers.
        assert "Updates" in prompts[0]
        assert "Blockers" in prompts[0]

    def test_default_template_used_when_none(self, monkeypatch: pytest.MonkeyPatch) -> None:
        prompts: list[str] = []
        monkeypatch.setattr(
            summarize, "_chat", lambda content, max_tokens=3000: prompts.append(content) or "ok"
        )
        summarize.summarize_meeting("**Me** [00:00]: hi")
        assert "## Decisions" in prompts[0]  # from the general template
