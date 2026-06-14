"""Google Docs exporter (OAuth installed-app flow + Docs/Drive API).

One-time setup (no recurring cost):
  1. In Google Cloud Console, create an OAuth client of type "Desktop app" and
     enable the Google Docs API and Google Drive API.
  2. Download the client secret JSON to ~/.config/meetingbot/google_client_secret.json
  3. Run `mbot auth-google` once to authorize in the browser.

Each meeting then becomes a Google Doc in your Drive (cloud), optionally inside a
folder set via MBOT_GOOGLE_DRIVE_FOLDER_ID.
"""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING, Any

from .. import config
from .base import ExporterError, ExportResult, NeedsSetupError
from .mdconvert import to_docs_requests

if TYPE_CHECKING:
    from google.oauth2.credentials import Credentials

SCOPES = [
    "https://www.googleapis.com/auth/documents",
    "https://www.googleapis.com/auth/drive.file",
]


def _load_credentials() -> Credentials | None:
    """Return valid cached credentials, refreshing if needed, else None."""
    from google.auth.transport.requests import Request
    from google.oauth2.credentials import Credentials

    if not config.GOOGLE_TOKEN.exists():
        return None
    creds: Credentials = Credentials.from_authorized_user_file(  # type: ignore[no-untyped-call]
        str(config.GOOGLE_TOKEN), SCOPES
    )
    if creds.valid:
        return creds
    if creds.expired and creds.refresh_token:
        creds.refresh(Request())  # type: ignore[no-untyped-call]
        config.GOOGLE_TOKEN.write_text(creds.to_json())  # type: ignore[no-untyped-call]
        return creds
    return None


def authorize() -> None:
    """Run the interactive browser OAuth flow and cache the token. CLI-invoked."""
    from google_auth_oauthlib.flow import InstalledAppFlow

    if not config.GOOGLE_CLIENT_SECRETS.exists():
        raise NeedsSetupError(
            f"Google client secret not found at {config.GOOGLE_CLIENT_SECRETS}\n"
            "Create a 'Desktop app' OAuth client in Google Cloud Console (enable the "
            "Docs + Drive APIs), download the JSON there, then re-run `mbot auth-google`."
        )
    flow = InstalledAppFlow.from_client_secrets_file(str(config.GOOGLE_CLIENT_SECRETS), SCOPES)
    creds = flow.run_local_server(port=0)
    config.GOOGLE_TOKEN.parent.mkdir(parents=True, exist_ok=True)
    config.GOOGLE_TOKEN.write_text(creds.to_json())


def _services(creds: Credentials) -> tuple[Any, Any]:
    from googleapiclient.discovery import build

    docs = build("docs", "v1", credentials=creds, cache_discovery=False)
    drive = build("drive", "v3", credentials=creds, cache_discovery=False)
    return docs, drive


class GoogleDocsExporter:
    name = "google_docs"

    def available(self) -> bool:
        try:
            return _load_credentials() is not None
        except Exception:
            return False

    def export(self, meta: dict[str, Any], summary_md: str, transcript_md: str) -> ExportResult:
        creds = _load_credentials()
        if creds is None:
            raise NeedsSetupError("Google Docs is not authorized. Run `mbot auth-google` once.")
        started = datetime.fromisoformat(meta["started_at"])
        title = meta.get("title") or f"Meeting {started:%b %-d %H:%M}"
        note_md = f"{summary_md}\n\n## Transcript\n\n{transcript_md}"
        build_plan = to_docs_requests(note_md, title=title)

        try:
            docs, drive = _services(creds)
            doc = docs.documents().create(body={"title": title}).execute()
            doc_id = doc["documentId"]
            docs.documents().batchUpdate(
                documentId=doc_id,
                body={
                    "requests": [
                        {"insertText": {"location": {"index": 1}, "text": build_plan.text}},
                        *build_plan.requests,
                    ]
                },
            ).execute()
            if config.GOOGLE_DRIVE_FOLDER_ID:
                drive.files().update(
                    fileId=doc_id,
                    addParents=config.GOOGLE_DRIVE_FOLDER_ID,
                    fields="id, parents",
                ).execute()
        except Exception as e:
            raise ExporterError(f"Google Docs API error: {e}") from e

        return ExportResult(
            target=self.name,
            location=f"https://docs.google.com/document/d/{doc_id}/edit",
        )
