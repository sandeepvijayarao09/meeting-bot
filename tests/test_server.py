import json
import wave
from pathlib import Path

import numpy as np

from meetingbot.server import SAMPLE_RATE, ChunkWriter


def pcm_seconds(seconds: float) -> bytes:
    return np.zeros(int(seconds * SAMPLE_RATE), dtype=np.int16).tobytes()


class TestChunkWriter:
    def test_rolls_chunks_and_writes_manifest(self, tmp_path: Path) -> None:
        writer = ChunkWriter("mic", tmp_path, chunk_seconds=1)
        writer.append(pcm_seconds(0.6))
        writer.append(pcm_seconds(0.6))  # crosses the 1 s boundary -> chunk closes
        writer.append(pcm_seconds(0.3))
        writer.close_chunk()

        manifest = [
            json.loads(line) for line in (tmp_path / "manifest.jsonl").read_text().splitlines()
        ]
        assert [m["file"] for m in manifest] == ["mic-0001.wav", "mic-0002.wav"]
        assert manifest[0]["start"] == 0.0
        assert manifest[0]["end"] == 1.2
        assert manifest[1]["start"] == 1.2
        assert manifest[1]["end"] == 1.5

    def test_wav_format_is_whisper_ready(self, tmp_path: Path) -> None:
        writer = ChunkWriter("sys", tmp_path, chunk_seconds=1)
        writer.append(pcm_seconds(0.5))
        writer.close_chunk()
        with wave.open(str(tmp_path / "sys-0001.wav"), "rb") as w:
            assert w.getnchannels() == 1
            assert w.getsampwidth() == 2
            assert w.getframerate() == SAMPLE_RATE
            assert w.getnframes() == SAMPLE_RATE // 2

    def test_empty_writer_produces_nothing(self, tmp_path: Path) -> None:
        writer = ChunkWriter("mic", tmp_path, chunk_seconds=1)
        writer.close_chunk()
        writer.append(b"")
        assert not (tmp_path / "manifest.jsonl").exists()
        assert list(tmp_path.glob("*.wav")) == []

    def test_close_without_new_data_is_idempotent(self, tmp_path: Path) -> None:
        writer = ChunkWriter("mic", tmp_path, chunk_seconds=1)
        writer.append(pcm_seconds(0.2))
        writer.close_chunk()
        writer.close_chunk()
        manifest = (tmp_path / "manifest.jsonl").read_text().splitlines()
        assert len(manifest) == 1
