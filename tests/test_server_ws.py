"""End-to-end tests of the Chrome-extension WebSocket protocol.

Spins up the real `mbot serve` handler in-process and drives it exactly like the
extension does (start → tagged PCM frames → stop), plus the failure paths
(dropped connection, double-record). Transcription stays local + cheap because
the streamed audio is silence, which the pipeline skips (no Whisper model).
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

import pytest
from websockets.asyncio.client import connect
from websockets.asyncio.server import serve
from websockets.exceptions import InvalidStatus

from meetingbot import recorder, server


async def _recv(ws, timeout: float = 20.0) -> dict:
    return json.loads(await asyncio.wait_for(ws.recv(), timeout))


def _silent_frame(tag: int, samples: int = 1600) -> bytes:
    return bytes([tag]) + b"\x00\x00" * samples  # 1 tag byte + Int16 silence


def _run(coro) -> None:
    asyncio.run(asyncio.wait_for(coro, timeout=40))


class TestExtensionProtocol:
    def test_happy_path_start_stream_stop_note(
        self, isolated: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("MBOT_NO_OPEN", "1")

        async def scenario() -> None:
            async with serve(server._handle, "127.0.0.1", 0) as srv:
                port = srv.sockets[0].getsockname()[1]
                async with connect(f"ws://127.0.0.1:{port}") as ws:
                    await ws.send(json.dumps({"type": "start", "title": "WS test"}))
                    started = await _recv(ws)
                    assert started["type"] == "started"
                    # Stream both tagged streams, as the extension does.
                    for _ in range(3):
                        await ws.send(_silent_frame(0))  # mic
                        await ws.send(_silent_frame(1))  # tab/system
                    await ws.send(json.dumps({"type": "stop"}))
                    note = await _recv(ws, timeout=30)
                    assert note["type"] == "note"
                    assert Path(note["path"]).exists()

        _run(scenario())

    def test_dropped_connection_still_finalizes(
        self, isolated: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("MBOT_NO_OPEN", "1")

        async def scenario() -> None:
            async with serve(server._handle, "127.0.0.1", 0) as srv:
                port = srv.sockets[0].getsockname()[1]
                async with connect(f"ws://127.0.0.1:{port}") as ws:
                    await ws.send(json.dumps({"type": "start", "title": "dropped"}))
                    assert (await _recv(ws))["type"] == "started"
                    await ws.send(_silent_frame(1))
                    # Disconnect WITHOUT sending stop — server must salvage the note.
                # Give the server's finally-block time to finalize.
                for _ in range(60):
                    if list(recorder.config.NOTES_DIR.glob("*.md")):
                        break
                    await asyncio.sleep(0.1)
                assert list(recorder.config.NOTES_DIR.glob("*.md"))

        _run(scenario())

    def test_second_recording_is_rejected(
        self, isolated: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("MBOT_NO_OPEN", "1")
        # In tests the pytest PID isn't a "meetingbot" process, so force the
        # lock check to trust it — otherwise the guard would treat it as stale.
        monkeypatch.setattr(recorder, "_pid_is_meetingbot", lambda pid: True)

        async def scenario() -> None:
            async with serve(server._handle, "127.0.0.1", 0) as srv:
                port = srv.sockets[0].getsockname()[1]
                async with connect(f"ws://127.0.0.1:{port}") as a:
                    await a.send(json.dumps({"type": "start", "title": "first"}))
                    assert (await _recv(a))["type"] == "started"
                    async with connect(f"ws://127.0.0.1:{port}") as b:
                        await b.send(json.dumps({"type": "start", "title": "second"}))
                        reply = await _recv(b)
                        assert reply["type"] == "error"
                        assert "already" in reply["message"].lower()

        _run(scenario())


def _origin_matches(origin: str) -> bool:
    """Would the server's allow-list admit this Origin? (mirrors websockets' fullmatch)."""
    return any(
        entry is not None and entry.fullmatch(origin) is not None
        for entry in server._allowed_origins()
    )


class TestOriginAllowList:
    """`_allowed_origins()` must admit the extension + CLI, and reject web pages."""

    def test_admits_browser_extension_origins(self) -> None:
        assert _origin_matches("chrome-extension://abcdefghijklmnopabcdefghijklmnop")
        assert _origin_matches("moz-extension://11111111-2222-3333-4444-555555555555")

    def test_rejects_web_page_origins(self) -> None:
        assert not _origin_matches("https://evil.example")
        assert not _origin_matches("http://localhost:3000")
        assert not _origin_matches("https://meet.google.com")

    def test_admits_originless_clients(self) -> None:
        # CLI/native clients (and these tests) send no Origin; a web page never can.
        assert None in server._allowed_origins()

    def test_pinned_origin_is_exact(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("MBOT_ALLOWED_ORIGIN", "chrome-extension://pinnedid")
        assert _origin_matches("chrome-extension://pinnedid")
        assert not _origin_matches("chrome-extension://someotherid")


class TestOriginHandshake:
    """End-to-end: the running server enforces the allow-list during the handshake."""

    def test_web_page_origin_is_rejected(self, isolated: Path) -> None:
        async def scenario() -> None:
            async with serve(
                server._handle, "127.0.0.1", 0, origins=server._allowed_origins()
            ) as srv:
                port = srv.sockets[0].getsockname()[1]
                with pytest.raises(InvalidStatus) as excinfo:
                    async with connect(
                        f"ws://127.0.0.1:{port}",
                        additional_headers={"Origin": "https://evil.example"},
                    ):
                        pass  # handshake must fail before we get here
                assert excinfo.value.response.status_code == 403

        _run(scenario())

    def test_extension_origin_is_accepted(self, isolated: Path) -> None:
        async def scenario() -> None:
            async with serve(
                server._handle, "127.0.0.1", 0, origins=server._allowed_origins()
            ) as srv:
                port = srv.sockets[0].getsockname()[1]
                # Entering the context means the handshake succeeded — origin accepted.
                async with connect(
                    f"ws://127.0.0.1:{port}",
                    additional_headers={"Origin": "chrome-extension://testextensionid"},
                ):
                    pass

        _run(scenario())
