"""Localhost capture server for the Chrome extension (`mbot serve`).

The extension streams 16 kHz mono Int16 PCM over one WebSocket:
  - text frame  {"type": "start", "title": "..."}      -> {"type": "started", ...}
  - binary frame: 1 tag byte (0=mic, 1=tab) + Int16LE PCM samples
  - text frame  {"type": "stop"}                       -> {"type": "note", ...}

Sessions are written in the exact same on-disk format as audiocap (chunked
WAVs + manifest.jsonl), so transcription/summarization/search are shared.
"""

import asyncio
import json
import logging
import os
import subprocess
import wave
from datetime import datetime
from pathlib import Path

from websockets.asyncio.server import ServerConnection, serve

from . import config, notes, recorder, transcribe

log = logging.getLogger(__name__)

SAMPLE_RATE = 16000
TAG_STREAMS = {0: "mic", 1: "sys"}


class ChunkWriter:
    """Chunked WAV writer mirroring audiocap's behavior, fed raw Int16 PCM."""

    def __init__(self, stream: str, session_dir: Path, chunk_seconds: int):
        self.stream = stream
        self.dir = session_dir
        self.chunk_frames = chunk_seconds * SAMPLE_RATE
        self.index = 0
        self.frames_in_chunk = 0
        self.total_frames = 0
        self.wav: wave.Wave_write | None = None
        self.filename = ""

    def append(self, pcm: bytes) -> None:
        if not pcm:
            return
        if self.wav is None:
            self._open_chunk()
        assert self.wav is not None
        self.wav.writeframes(pcm)
        frames = len(pcm) // 2
        self.frames_in_chunk += frames
        self.total_frames += frames
        if self.frames_in_chunk >= self.chunk_frames:
            self.close_chunk()

    def _open_chunk(self) -> None:
        self.index += 1
        self.filename = f"{self.stream}-{self.index:04d}.wav"
        # The file deliberately stays open across append() calls (closed in close_chunk).
        self.wav = wave.open(str(self.dir / self.filename), "wb")  # noqa: SIM115
        self.wav.setnchannels(1)
        self.wav.setsampwidth(2)
        self.wav.setframerate(SAMPLE_RATE)
        self.frames_in_chunk = 0

    def close_chunk(self) -> None:
        if self.wav is None:
            return
        self.wav.close()
        self.wav = None
        if self.frames_in_chunk == 0:
            return
        end = self.total_frames / SAMPLE_RATE
        start = (self.total_frames - self.frames_in_chunk) / SAMPLE_RATE
        with (self.dir / "manifest.jsonl").open("a") as f:
            f.write(
                json.dumps(
                    {
                        "stream": self.stream,
                        "file": self.filename,
                        "start": round(start, 3),
                        "end": round(end, 3),
                    }
                )
                + "\n"
            )
        self.frames_in_chunk = 0


class WsSession:
    """One recording driven by one WebSocket connection."""

    def __init__(self, title: str | None):
        if recorder.current_recording():
            raise RuntimeError("a recording is already in progress")
        self.started_at = datetime.now()
        name = f"{self.started_at:%Y%m%d-%H%M%S}-{notes.slugify(title or 'meeting')}"
        self.session_dir = config.SESSIONS_DIR / name
        self.session_dir.mkdir(parents=True, exist_ok=True)
        recorder.write_meta(
            self.session_dir,
            {
                "title": title,
                "started_at": self.started_at.isoformat(timespec="seconds"),
                "session_dir": str(self.session_dir),
                "source": "chrome-extension",
            },
        )
        self.writers = {
            stream: ChunkWriter(stream, self.session_dir, config.CHUNK_SECONDS)
            for stream in TAG_STREAMS.values()
        }
        self.transcriber = transcribe.LiveTranscriber(self.session_dir)
        self.transcriber.start()
        config.DATA_DIR.mkdir(parents=True, exist_ok=True)
        config.CURRENT_FILE.write_text(
            json.dumps(
                {
                    "pid": os.getpid(),
                    "session_dir": str(self.session_dir),
                    "started_at": self.started_at.isoformat(timespec="seconds"),
                }
            )
        )

    def feed(self, frame: bytes) -> None:
        stream = TAG_STREAMS.get(frame[0])
        if stream:
            self.writers[stream].append(frame[1:])

    async def finish(self) -> tuple[Path, bool]:
        for writer in self.writers.values():
            writer.close_chunk()
        await asyncio.to_thread(self.transcriber.finish)
        meta = recorder.read_meta(self.session_dir)
        ended = datetime.now()
        meta["ended_at"] = ended.isoformat(timespec="seconds")
        meta["duration_s"] = round((ended - self.started_at).total_seconds())
        recorder.write_meta(self.session_dir, meta)
        config.CURRENT_FILE.unlink(missing_ok=True)
        return await asyncio.to_thread(recorder.finalize_session, self.session_dir)


async def _handle(ws: ServerConnection) -> None:
    session: WsSession | None = None
    try:
        async for message in ws:
            if isinstance(message, bytes):
                if session and len(message) > 1:
                    session.feed(message)
                continue
            event = json.loads(message)
            if event.get("type") == "start" and session is None:
                try:
                    session = WsSession(event.get("title") or None)
                except RuntimeError as e:
                    await ws.send(json.dumps({"type": "error", "message": str(e)}))
                    return
                log.info("recording %s", session.session_dir.name)
                await ws.send(json.dumps({"type": "started", "session": session.session_dir.name}))
            elif event.get("type") == "stop" and session is not None:
                log.info("stopping — transcribing remaining chunks…")
                note_path, summarized = await session.finish()
                log.info("note: %s", note_path)
                await ws.send(
                    json.dumps(
                        {
                            "type": "note",
                            "path": str(note_path),
                            "summarized": summarized,
                        }
                    )
                )
                if os.environ.get("MBOT_NO_OPEN") != "1":
                    subprocess.run(["open", str(note_path)], check=False)
                session = None
    finally:
        if session is not None:
            # browser/extension went away mid-meeting: salvage everything
            log.info("connection lost — finalizing session anyway…")
            note_path, _ = await session.finish()
            log.info("note: %s", note_path)


async def _serve(host: str, port: int) -> None:
    async with serve(_handle, host, port, max_size=2**22):
        log.info("mbot serve — listening on ws://%s:%d", host, port)
        log.info("Start/stop recordings from the Chrome extension. Ctrl+C to quit.")
        await asyncio.get_running_loop().create_future()


def run(host: str = "127.0.0.1", port: int | None = None) -> None:
    port = port or int(os.environ.get("MBOT_PORT", "8765"))
    try:
        asyncio.run(_serve(host, port))
    except KeyboardInterrupt:
        print("\nbye")
