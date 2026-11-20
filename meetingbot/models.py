"""Whisper model presence checks and explicit, resumable download.

The transcription model is deliberately **not** bundled in the app: at ~1.5 GB it
would dwarf the rest of the download, and most of it is useless to a user who
never records. mlx-whisper fetches it from Hugging Face on first use instead.

Left implicit, that fetch lands in the worst possible place — the middle of
someone's first meeting, with no progress indication and no way to tell a slow
download from a hang. These helpers make it explicit so the app can ask once, up
front, and show progress while it runs.
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from . import config

# mlx-whisper loads a model directory by reading these; a snapshot missing either
# one is a partial download, not a usable model.
_REQUIRED = ("config.json",)
_WEIGHTS_GLOB = "*.safetensors"

# Pulling only what mlx-whisper reads avoids the PyTorch-format duplicates some
# repos also carry (which would roughly double the transfer for nothing).
_ALLOW_PATTERNS = ["*.json", "*.safetensors", "*.txt", "*.tiktoken"]


def cache_dir(repo: str | None = None) -> Path:
    """Directory huggingface_hub uses for `repo`'s snapshots."""
    repo = repo or config.WHISPER_MODEL
    from huggingface_hub.constants import HF_HUB_CACHE

    return Path(HF_HUB_CACHE) / ("models--" + repo.replace("/", "--"))


def local_snapshot(repo: str | None = None) -> Path | None:
    """Return the cached snapshot usable for transcription, or None.

    A snapshot counts only when the weights and config are both present, so a
    download interrupted halfway reads as absent and gets retried rather than
    failing later inside mlx-whisper.
    """
    snapshots = cache_dir(repo) / "snapshots"
    if not snapshots.is_dir():
        return None
    for snap in sorted(snapshots.iterdir(), reverse=True):
        if not snap.is_dir():
            continue
        if all((snap / f).exists() for f in _REQUIRED) and any(snap.glob(_WEIGHTS_GLOB)):
            return snap
    return None


def is_downloaded(repo: str | None = None) -> bool:
    """True when the model is cached and complete enough to transcribe with."""
    return local_snapshot(repo) is not None


def disk_usage(repo: str | None = None) -> int:
    """Bytes the cached model occupies (0 when absent).

    Walks the blob store rather than the snapshot, because snapshots are symlinks
    into it — summing the links would report a few kilobytes.
    """
    blobs = cache_dir(repo) / "blobs"
    if not blobs.is_dir():
        return 0
    return sum(f.stat().st_size for f in blobs.iterdir() if f.is_file())


def download(
    repo: str | None = None,
    on_progress: Callable[[str], None] | None = None,
) -> Path:
    """Fetch the model into the Hugging Face cache and return its snapshot path.

    Resumable and idempotent: huggingface_hub skips blobs it already holds, so a
    retry after a dropped connection continues rather than restarting.
    """
    repo = repo or config.WHISPER_MODEL
    if on_progress:
        on_progress(f"Downloading {repo}…")

    from huggingface_hub import snapshot_download

    path = Path(snapshot_download(repo_id=repo, allow_patterns=_ALLOW_PATTERNS))

    # snapshot_download returns happily if the repo simply has no weights, which
    # would leave the app thinking it is ready to transcribe.
    if not any(path.glob(_WEIGHTS_GLOB)):
        raise RuntimeError(f"{repo} downloaded but contains no {_WEIGHTS_GLOB} weights")

    if on_progress:
        on_progress(f"Model ready at {path}")
    return path


def remove(repo: str | None = None) -> int:
    """Delete the cached model. Returns the bytes reclaimed."""
    import shutil

    freed = disk_usage(repo)
    target = cache_dir(repo)
    if target.is_dir():
        shutil.rmtree(target)
    return freed
