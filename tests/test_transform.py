import pytest

from meetingbot import config, summarize, transform


class TestTransformValidation:
    def test_unknown_kind_raises(self) -> None:
        with pytest.raises(ValueError, match="unknown transform"):
            transform.transform("text", "nonsense")

    def test_no_key_raises(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(config, "NVIDIA_API_KEY", "")
        with pytest.raises(summarize.MissingAPIKeyError, match=r"build\.nvidia\.com"):
            transform.transform("text", "short")


class TestTransformTemplates:
    def test_all_transforms_have_templates_with_token(self) -> None:
        for kind in transform.TRANSFORMS:
            path = config.PROMPTS_DIR / "transforms" / f"{kind}.md"
            assert path.exists(), kind
            assert "{{TEXT}}" in path.read_text(), kind

    @pytest.mark.parametrize("kind", transform.TRANSFORMS)
    def test_fills_template_with_source(self, kind: str, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(config, "NVIDIA_API_KEY", "nvapi-test")
        seen: list[str] = []

        def fake_complete(system: str, user: str, **k: object) -> str:
            seen.append(user)
            return "RESULT"

        monkeypatch.setattr(summarize, "complete", fake_complete)
        assert transform.transform("THE_TRANSCRIPT_BODY", kind) == "RESULT"
        assert "THE_TRANSCRIPT_BODY" in seen[0]
        assert "{{TEXT}}" not in seen[0]  # token was substituted


class TestTransformMapReduce:
    def test_long_input_condenses_before_transforming(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(config, "NVIDIA_API_KEY", "nvapi-test")
        monkeypatch.setattr(summarize, "MAX_DIRECT_CHARS", 100)
        monkeypatch.setattr(summarize, "PIECE_CHARS", 60)
        calls: list[str] = []

        def fake_complete(system: str, user: str, **k: object) -> str:
            calls.append(user)
            return "condensed"

        monkeypatch.setattr(summarize, "complete", fake_complete)
        long_text = "\n".join(f"**Me** [00:0{i % 10}]: line {i}" for i in range(40))
        transform.transform(long_text, "key_points")
        # several condense calls precede the final transform call
        assert len(calls) > 2
        assert summarize.CONDENSE_PROMPT[:30] in calls[0]
        assert "condensed" in calls[-1]  # final transform sees the condensed text
