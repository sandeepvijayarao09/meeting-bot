"""Model cache detection, explicit download, and the build exclusions it relies on.

The model is deliberately absent from the app bundle, which makes
`models.is_downloaded()` the thing standing between a user and a silent 1.5 GB
fetch in the middle of their first meeting. The partial-download cases below are
the ones that matter: a snapshot directory existing is not the same as a model
being usable, and treating it as such sends the stall somewhere deeper and
harder to read.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from meetingbot import models

ROOT = Path(__file__).resolve().parent.parent


@pytest.fixture
def hf_cache(tmp_path, monkeypatch):
    """Point huggingface_hub's cache at a temp dir and return it."""
    cache = tmp_path / "hub"
    cache.mkdir()
    monkeypatch.setattr(
        "huggingface_hub.constants.HF_HUB_CACHE",
        str(cache),
        raising=False,
    )
    return cache


def _snapshot(cache: Path, repo: str = "mlx-community/whisper-large-v3-turbo") -> Path:
    snap = cache / ("models--" + repo.replace("/", "--")) / "snapshots" / "abc123"
    snap.mkdir(parents=True)
    return snap


def test_absent_when_nothing_cached(hf_cache) -> None:
    assert models.is_downloaded() is False
    assert models.local_snapshot() is None


def test_present_when_config_and_weights_exist(hf_cache) -> None:
    snap = _snapshot(hf_cache)
    (snap / "config.json").write_text("{}")
    (snap / "weights.safetensors").write_bytes(b"\x00")

    assert models.is_downloaded() is True
    assert models.local_snapshot() == snap


def test_weights_without_config_reads_as_absent(hf_cache) -> None:
    """A half-finished download must not look ready, or the stall just moves."""
    snap = _snapshot(hf_cache)
    (snap / "weights.safetensors").write_bytes(b"\x00")

    assert models.is_downloaded() is False


def test_config_without_weights_reads_as_absent(hf_cache) -> None:
    """The failure mode mlx-whisper would otherwise hit at load time."""
    snap = _snapshot(hf_cache)
    (snap / "config.json").write_text("{}")

    assert models.is_downloaded() is False


def test_disk_usage_sums_blobs_not_snapshot_symlinks(hf_cache) -> None:
    """Snapshots are symlinks into blobs; summing them would report ~nothing."""
    repo_dir = hf_cache / "models--mlx-community--whisper-large-v3-turbo"
    blobs = repo_dir / "blobs"
    blobs.mkdir(parents=True)
    (blobs / "a").write_bytes(b"x" * 1000)
    (blobs / "b").write_bytes(b"x" * 2000)

    assert models.disk_usage() == 3000


def test_disk_usage_is_zero_when_absent(hf_cache) -> None:
    assert models.disk_usage() == 0


def test_download_rejects_a_repo_with_no_weights(hf_cache, monkeypatch) -> None:
    """snapshot_download succeeds on a weightless repo; we must not call that ready."""
    empty = hf_cache / "empty"
    empty.mkdir()
    (empty / "config.json").write_text("{}")
    monkeypatch.setattr(
        "huggingface_hub.snapshot_download",
        lambda **kw: str(empty),
    )

    with pytest.raises(RuntimeError, match=r"no .* weights"):
        models.download()


def test_download_returns_snapshot_and_reports_progress(hf_cache, monkeypatch) -> None:
    ready = hf_cache / "ready"
    ready.mkdir()
    (ready / "weights.safetensors").write_bytes(b"\x00")
    monkeypatch.setattr("huggingface_hub.snapshot_download", lambda **kw: str(ready))

    seen: list[str] = []
    assert models.download(on_progress=seen.append) == ready
    assert any("Downloading" in m for m in seen)
    assert any("ready" in m for m in seen)


def test_download_asks_only_for_the_formats_mlx_reads(hf_cache, monkeypatch) -> None:
    """Pulling PyTorch-format duplicates would roughly double the transfer."""
    ready = hf_cache / "ready"
    ready.mkdir()
    (ready / "weights.safetensors").write_bytes(b"\x00")
    captured: dict = {}

    def fake(**kw):
        captured.update(kw)
        return str(ready)

    monkeypatch.setattr("huggingface_hub.snapshot_download", fake)
    models.download()

    assert "*.safetensors" in captured["allow_patterns"]
    assert not any(p.endswith(".bin") for p in captured["allow_patterns"])


def test_remove_reclaims_and_deletes(hf_cache) -> None:
    repo_dir = hf_cache / "models--mlx-community--whisper-large-v3-turbo"
    blobs = repo_dir / "blobs"
    blobs.mkdir(parents=True)
    (blobs / "a").write_bytes(b"x" * 500)

    assert models.remove() == 500
    assert not repo_dir.exists()
    assert models.is_downloaded() is False


# --------------------------------------------------------------- build exclusions


def _sidecar_script() -> str:
    return (ROOT / "scripts" / "build-sidecar.sh").read_text()


def test_frozen_entry_calls_freeze_support_before_the_cli() -> None:
    """Frozen, sys.executable is `mbot`, so multiprocessing re-runs this binary.

    Without freeze_support() the child gets Python's flags parsed as CLI options
    ("No such option: -B"), dies, and takes the semaphore tracker with it — which
    is what 1.0.1 does on every transcription.
    """
    entry = (ROOT / "scripts" / "sidecar_entry.py").read_text()
    assert "freeze_support()" in entry
    assert entry.index("freeze_support()") < entry.index("from meetingbot.cli import app")


@pytest.mark.parametrize(
    "module", ["torch", "torchvision", "torchaudio", "mypy", "pytest", "coverage"]
)
def test_sidecar_excludes_unreachable_heavyweights(module: str) -> None:
    """319 MB of PyTorch shipped to every user for a code path nothing imports."""
    assert f"--exclude-module {module}" in _sidecar_script()


@pytest.mark.parametrize("module", ["numba", "llvmlite", "scipy"])
def test_sidecar_keeps_what_transcription_imports(module: str) -> None:
    """mlx_whisper/transcribe.py imports .timing at module scope — these must stay.

    Excluding them shrinks the bundle and breaks transcription, which is a far
    worse trade than the megabytes are worth.
    """
    assert f"--exclude-module {module}" not in _sidecar_script()


def test_sidecar_prunes_unread_google_discovery_docs() -> None:
    """582 discovery documents, 96 MB, behind cache_discovery=False."""
    script = _sidecar_script()
    assert "discovery_cache/documents" in script
    assert "docs.v1.json" in script


def test_google_exporter_still_disables_discovery_cache() -> None:
    """The pruning is only safe while this flag holds; pin it so it cannot drift."""
    exporter = (ROOT / "meetingbot" / "exporters" / "google_docs.py").read_text()
    builds = re.findall(r"build\(\s*\"(\w+)\"", exporter)
    assert builds, "expected the exporter to build Google services"
    assert exporter.count("cache_discovery=False") == len(builds)
    # Any API we build must keep its discovery document in the pruned set.
    script = _sidecar_script()
    for api in builds:
        assert f"{api}.v" in script, f'build("{api}") has no retained discovery doc'
