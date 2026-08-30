"""Configuration: env vars + sensible defaults.

Reads ~/.config/meetingbot/.env first, then a repo-local .env (repo wins).
"""

import os
import sys
from pathlib import Path

from dotenv import load_dotenv

# True inside the PyInstaller sidecar the macOS app bundles (scripts/build-sidecar.sh).
# There the package lives in Contents/Resources/_internal, so `__file__`-relative repo
# paths (prompts/, notes/, mac/.build/) do not exist: bundled data is unpacked to
# `sys._MEIPASS` instead, and nothing under the signed bundle is writable.
FROZEN = getattr(sys, "frozen", False)
_MEIPASS = getattr(sys, "_MEIPASS", None)

#: Repo checkout root. Only meaningful when running from source.
PROJECT_ROOT = Path(__file__).resolve().parent.parent
#: Root for read-only resources shipped alongside the code (prompt templates).
RESOURCE_ROOT = Path(_MEIPASS) if _MEIPASS else PROJECT_ROOT

CONFIG_DIR = Path.home() / ".config" / "meetingbot"

load_dotenv(CONFIG_DIR / ".env")
if not FROZEN:
    load_dotenv(PROJECT_ROOT / ".env", override=True)


def _path(env: str, default: Path) -> Path:
    raw = os.environ.get(env)
    return Path(raw).expanduser() if raw else default


DATA_DIR = _path("MBOT_DATA_DIR", Path.home() / ".local" / "share" / "meetingbot")
SESSIONS_DIR = DATA_DIR / "sessions"
# Frozen builds must not write inside the signed app bundle; fall back to the data
# dir, matching Paths.notesDirectory in the macOS app (which also pins MBOT_NOTES_DIR).
_DEFAULT_NOTES_DIR = DATA_DIR / "notes" if FROZEN else PROJECT_ROOT / "notes"
NOTES_DIR = _path("MBOT_NOTES_DIR", _DEFAULT_NOTES_DIR)
DB_PATH = DATA_DIR / "index.db"
CURRENT_FILE = DATA_DIR / "current.json"
USAGE_LOG = DATA_DIR / "usage.log"

# From source this is the SwiftPM build product; in the sidecar it would sit next to
# the frozen executable. The macOS app never needs it — it captures in-process via
# CaptureKit — so a frozen build without it is not an error (see `mbot doctor`).
_DEFAULT_AUDIOCAP = (
    Path(sys.executable).resolve().parent / "audiocap"
    if FROZEN
    else PROJECT_ROOT / "mac" / ".build" / "release" / "audiocap"
)
AUDIOCAP_BIN = _path("MBOT_AUDIOCAP", _DEFAULT_AUDIOCAP)

CHUNK_SECONDS = int(os.environ.get("MBOT_CHUNK_SECONDS", "30"))
WHISPER_MODEL = os.environ.get("MBOT_WHISPER_MODEL", "mlx-community/whisper-large-v3-turbo")
# Optional domain vocabulary (product names, jargon, people) seeded into Whisper
# so they're spelled correctly instead of phonetically ("Postgres", not "PostGas").
# Comma/space separated, e.g. "Postgres, Kubernetes, OAuth".
VOCAB = os.environ.get("MBOT_VOCAB", "").strip()

# Eloquent-style transcript refinement tier, applied to the note's transcript and
# the summarizer's input (the raw transcript.jsonl is always preserved verbatim):
#   off   — raw Whisper transcript, no cleanup (legacy behavior)
#   local — deterministic on-device cleanup (strip fillers, collapse false starts
#           and repetitions, fix punctuation/capitalization). $0, offline, default.
#   cloud — local cleanup THEN an NIM polish pass; falls back to local if the key
#           is missing or the request fails. Opt-in (spends credits per meeting).
REFINE = os.environ.get("MBOT_REFINE", "local").strip().lower()

NVIDIA_API_KEY = os.environ.get("NVIDIA_API_KEY", "").strip()
NIM_BASE_URL = os.environ.get("MBOT_NIM_BASE_URL", "https://integrate.api.nvidia.com/v1")
NIM_MODEL = os.environ.get("MBOT_NIM_MODEL", "openai/gpt-oss-120b")
# Reasoning effort for reasoning models (gpt-oss). "low" is ~40% faster and
# cheaper than the default for note-taking with equal quality; "none" disables.
NIM_REASONING = os.environ.get("MBOT_NIM_REASONING", "low").strip().lower()
# Per-request timeout (seconds) for NIM calls. The OpenAI SDK defaults to 600s, which
# lets a slow/unresponsive API hang the app's Stop→"Processing…" for up to 10 minutes;
# bound it so summarization fails fast (and the note falls back to transcript-only).
NIM_TIMEOUT = float(os.environ.get("MBOT_NIM_TIMEOUT", "90"))

PROMPTS_DIR = RESOURCE_ROOT / "prompts"
PROMPT_TEMPLATE = PROMPTS_DIR / "meeting_summary.md"  # default / general

# Meeting-type templates ("Recipes"): each is prompts/<name>.md sharing the same
# {{TITLE}}/{{DATE}}/{{DURATION}}/{{NOTES}}/{{TRANSCRIPT}} tokens.
TEMPLATE = os.environ.get("MBOT_TEMPLATE", "default")
TEMPLATES = ["default", "standup", "one_on_one", "interview", "sales_call"]


def resolve_template(name: str | None) -> Path:
    """Path to a template prompt by name, falling back to the default."""
    if name and name != "default":
        candidate = PROMPTS_DIR / f"{name}.md"
        if candidate.exists():
            return candidate
    return PROMPT_TEMPLATE


SPEAKER_LABELS = {"mic": "Me", "sys": "Them"}

# Include a talk-time analytics section in each note (Me/Them ratio, etc.).
ANALYTICS = os.environ.get("MBOT_ANALYTICS", "1") not in ("0", "false", "no")

# Export targets, comma-separated. "markdown" is always included implicitly.
# Options: markdown, apple_notes, google_docs
EXPORTERS = os.environ.get("MBOT_EXPORTERS", "markdown")

# Apple Notes: folder to file notes under. It is created in the first account
# that has it; put it under your iCloud account to sync to cloud / other devices,
# or an "On My Mac" account to keep notes on-device only.
APPLE_NOTES_FOLDER = os.environ.get("MBOT_APPLE_NOTES_FOLDER", "Meeting Bot")

# Google Docs OAuth: client secrets (downloaded from Google Cloud Console) and
# the cached user token live here. Optional Drive folder to file docs under.
GOOGLE_CLIENT_SECRETS = _path(
    "MBOT_GOOGLE_CLIENT_SECRETS", CONFIG_DIR / "google_client_secret.json"
)
GOOGLE_TOKEN = _path("MBOT_GOOGLE_TOKEN", CONFIG_DIR / "google_token.json")
GOOGLE_DRIVE_FOLDER_ID = os.environ.get("MBOT_GOOGLE_DRIVE_FOLDER_ID", "").strip()
