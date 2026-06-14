"""Configuration: env vars + sensible defaults.

Reads ~/.config/meetingbot/.env first, then a repo-local .env (repo wins).
"""

import os
from pathlib import Path

from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parent.parent
CONFIG_DIR = Path.home() / ".config" / "meetingbot"

load_dotenv(CONFIG_DIR / ".env")
load_dotenv(PROJECT_ROOT / ".env", override=True)


def _path(env: str, default: Path) -> Path:
    raw = os.environ.get(env)
    return Path(raw).expanduser() if raw else default


DATA_DIR = _path("MBOT_DATA_DIR", Path.home() / ".local" / "share" / "meetingbot")
SESSIONS_DIR = DATA_DIR / "sessions"
NOTES_DIR = _path("MBOT_NOTES_DIR", PROJECT_ROOT / "notes")
DB_PATH = DATA_DIR / "index.db"
CURRENT_FILE = DATA_DIR / "current.json"
USAGE_LOG = DATA_DIR / "usage.log"

AUDIOCAP_BIN = _path("MBOT_AUDIOCAP", PROJECT_ROOT / "mac" / ".build" / "release" / "audiocap")

CHUNK_SECONDS = int(os.environ.get("MBOT_CHUNK_SECONDS", "30"))
WHISPER_MODEL = os.environ.get("MBOT_WHISPER_MODEL", "mlx-community/whisper-large-v3-turbo")

NVIDIA_API_KEY = os.environ.get("NVIDIA_API_KEY", "").strip()
NIM_BASE_URL = os.environ.get("MBOT_NIM_BASE_URL", "https://integrate.api.nvidia.com/v1")
NIM_MODEL = os.environ.get("MBOT_NIM_MODEL", "meta/llama-3.3-70b-instruct")

PROMPT_TEMPLATE = PROJECT_ROOT / "prompts" / "meeting_summary.md"

SPEAKER_LABELS = {"mic": "Me", "sys": "Them"}

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
