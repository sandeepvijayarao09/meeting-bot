import wave
from pathlib import Path

import numpy as np
import pytest

from meetingbot import config


@pytest.fixture
def isolated(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Redirect all on-disk state into a temp dir."""
    data = tmp_path / "data"
    monkeypatch.setattr(config, "DATA_DIR", data)
    monkeypatch.setattr(config, "SESSIONS_DIR", data / "sessions")
    monkeypatch.setattr(config, "NOTES_DIR", tmp_path / "notes")
    monkeypatch.setattr(config, "DB_PATH", data / "index.db")
    monkeypatch.setattr(config, "CURRENT_FILE", data / "current.json")
    monkeypatch.setattr(config, "USAGE_LOG", data / "usage.log")
    monkeypatch.setattr(config, "NVIDIA_API_KEY", "")
    # Keep tests off the real ~/.config Google credentials.
    monkeypatch.setattr(config, "GOOGLE_TOKEN", data / "google_token.json")
    monkeypatch.setattr(config, "GOOGLE_CLIENT_SECRETS", data / "google_client_secret.json")
    monkeypatch.setattr(config, "EXPORTERS", "markdown")
    return tmp_path


def write_wav(path: Path, samples: np.ndarray, rate: int = 16000) -> Path:
    pcm = (np.clip(samples, -1.0, 1.0) * 32767).astype(np.int16)
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes(pcm.tobytes())
    return path


def tone(seconds: float = 1.0, rate: int = 16000, hz: float = 440.0) -> np.ndarray:
    t = np.linspace(0, seconds, int(seconds * rate), endpoint=False)
    return (0.3 * np.sin(2 * np.pi * hz * t)).astype(np.float32)
