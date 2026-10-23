"""The deadline the release gate runs its blocking external calls under.

`scripts/preflight-release.sh` hung forever on the one bundle it most needs to
audit: an app dragged out of a freshly downloaded DMG carries
com.apple.quarantine, and Gatekeeper blocks the nested, ad-hoc-signed sidecar at
exec time. `"$MBOT" --version` never returned, nothing was printed, and the gate
that exists to catch release defects caught nothing at all.

`scripts/with-timeout.sh` is the fix, so what matters is that it reports the
command's own status when the command finishes and a *distinguishable* status
when it does not — a timeout that looked like success would restore the original
silence, in a less obvious form. The last tests pin the wiring, because the
helper is worth nothing if a future edit reintroduces an unbounded call.
"""

from __future__ import annotations

import re
import subprocess
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
HELPER = ROOT / "scripts" / "with-timeout.sh"
PREFLIGHT = ROOT / "scripts" / "preflight-release.sh"

# The status GNU timeout uses; the script branches on it by name.
TIMEOUT_STATUS = 124


def _run(snippet: str) -> subprocess.CompletedProcess[str]:
    """Run `snippet` in a bash that has sourced the helper."""
    return subprocess.run(
        ["bash", "-c", f'source "{HELPER}"\n{snippet}'],
        capture_output=True,
        text=True,
        timeout=120,
    )


def test_returns_zero_when_the_command_succeeds() -> None:
    assert _run("with_timeout 10 true").returncode == 0


def test_returns_the_commands_own_failure_status() -> None:
    """Statuses have to survive the wrapper, or every check reads as a timeout."""
    assert _run('with_timeout 10 sh -c "exit 7"').returncode == 7


def test_returns_127_when_the_command_does_not_exist() -> None:
    assert _run("with_timeout 10 /no/such/binary 2>/dev/null").returncode == 127


def test_passes_output_through_for_capture() -> None:
    """The gate parses what these commands print, so the wrapper must be clear."""
    result = _run('out="$(with_timeout 10 printf hello)"; printf "[%s]" "$out"')
    assert result.stdout == "[hello]"


def test_reports_the_timeout_status_when_the_command_hangs() -> None:
    assert _run("with_timeout 1 sleep 30").returncode == TIMEOUT_STATUS


def test_timeout_status_is_distinct_from_success_and_common_failures() -> None:
    """A timeout that collided with a real status would be indistinguishable."""
    assert TIMEOUT_STATUS not in (0, 1, 2, 127)
    assert f"TIMEOUT_STATUS={TIMEOUT_STATUS}" in HELPER.read_text()


def test_returns_as_soon_as_the_command_finishes() -> None:
    """A helper that always waited out its deadline would make the gate crawl."""
    started = time.monotonic()
    assert _run("with_timeout 30 true").returncode == 0
    assert time.monotonic() - started < 10


def test_kills_the_command_it_timed_out_on(tmp_path: Path) -> None:
    """Leaving it running would hold the pipe the caller is still reading."""
    marker = tmp_path / "finished"
    assert _run(f"with_timeout 1 sh -c 'sleep 4; : > \"{marker}\"'").returncode == TIMEOUT_STATUS

    time.sleep(5)
    assert not marker.exists()


def test_timing_out_stays_quiet_on_stderr() -> None:
    """The shell's own "Terminated: 15" notice would land mid-report."""
    result = _run("with_timeout 1 sleep 30")
    assert result.stderr == ""


# ------------------------------------------------------------- the gate's wiring


def _preflight() -> str:
    return PREFLIGHT.read_text()


def test_preflight_sources_the_helper() -> None:
    assert "with-timeout.sh" in _preflight()


def test_every_sidecar_invocation_is_bounded() -> None:
    """The quarantined-bundle hang was here, and nothing else would catch it."""
    # Every mention that runs it, as opposed to assigning it or testing for it.
    calls = [
        line
        for line in _preflight().splitlines()
        if re.search(r'(?<!-x )"\$MBOT"', line) and "MBOT=" not in line
    ]
    assert calls, "expected the gate to run the bundled sidecar"
    for call in calls:
        assert "with_timeout" in call, f"unbounded sidecar call: {call.strip()}"


def test_gatekeeper_calls_are_bounded() -> None:
    """spctl and stapler both ask Gatekeeper, and stapler reaches Apple."""
    calls = [
        line
        for line in _preflight().splitlines()
        if re.search(r"\b(spctl -a|xcrun stapler validate)\b", line)
        and not line.lstrip().startswith("#")
    ]
    assert len(calls) == 3, f"expected spctl + stapler on the app and the DMG, got {calls}"
    for call in calls:
        assert "with_timeout" in call, f"unbounded Gatekeeper call: {call.strip()}"


def test_timeouts_are_reported_as_failures() -> None:
    """Treating a deadline as a pass is the silence this exists to end."""
    body = _preflight()
    assert body.count("$TIMEOUT_STATUS") >= 5
    for match in re.finditer(r'"\$TIMEOUT_STATUS"\)(.*?)(?=\n\s*\*\)|\n\s*esac)', body, re.S):
        assert "fail " in match.group(1), f"timeout branch does not fail: {match.group(1)!r}"
