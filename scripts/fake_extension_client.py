"""Simulates the Chrome extension against `mbot serve` — for testing/debugging.

Usage: python scripts/fake_extension_client.py <mic.wav> <tab.wav>
Both WAVs must be 16 kHz mono 16-bit (what the extension sends).
"""

import asyncio
import json
import sys
import wave

from websockets.asyncio.client import connect

TAG = {"mic": 0, "tab": 1}
CHUNK_SAMPLES = 3200  # 200 ms, roughly the extension's batching


async def stream_wav(ws, path: str, tag: int) -> None:
    with wave.open(path, "rb") as w:
        assert w.getframerate() == 16000 and w.getnchannels() == 1, "need 16kHz mono"
        data = w.readframes(w.getnframes())
    step = CHUNK_SAMPLES * 2
    for i in range(0, len(data), step):
        await ws.send(bytes([tag]) + data[i : i + step])
        await asyncio.sleep(0.005)  # accelerated "real time"


async def main() -> None:
    mic_wav, tab_wav = sys.argv[1], sys.argv[2]
    async with connect("ws://127.0.0.1:8765") as ws:
        await ws.send(json.dumps({"type": "start", "title": "Extension test meeting"}))
        print("server:", await ws.recv())
        await stream_wav(ws, mic_wav, TAG["mic"])
        await stream_wav(ws, tab_wav, TAG["tab"])
        await ws.send(json.dumps({"type": "stop"}))
        print("server:", await ws.recv())


if __name__ == "__main__":
    asyncio.run(main())
