from pathlib import Path

import pytest

from meetingbot import capture, config


def test_missing_binary_raises_helpful_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(config, "AUDIOCAP_BIN", tmp_path / "nope" / "audiocap")
    with pytest.raises(capture.AudiocapError, match="swift build"):
        capture.start(tmp_path)
