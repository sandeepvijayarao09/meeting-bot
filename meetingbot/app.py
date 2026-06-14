"""Menu bar app (rumps): start/stop recording from the 🎙 icon."""

import subprocess
import threading

import rumps

from . import config, notes, recorder, summarize


class MeetingBotApp(rumps.App):
    def __init__(self) -> None:
        super().__init__("🎙", title="🎙")
        self.recorder: recorder.Recorder | None = None
        self.toggle_item = rumps.MenuItem("Start Recording", callback=self.toggle)
        self.status_item = rumps.MenuItem("Idle")
        self.status_item.set_callback(None)
        self.menu = [
            self.toggle_item,
            self.status_item,
            None,
            rumps.MenuItem("Open Last Note", callback=self.open_last_note),
            rumps.MenuItem("Open Notes Folder", callback=self.open_notes_folder),
        ]
        self.timer = rumps.Timer(self.tick, 1)
        self.elapsed = 0
        self.busy = False

    # -- recording control ----------------------------------------------

    def toggle(self, _: object) -> None:
        if self.busy:
            return
        if self.recorder is None:
            threading.Thread(target=self._start, daemon=True).start()
        else:
            threading.Thread(target=self._stop, daemon=True).start()

    def _start(self) -> None:
        self.busy = True
        try:
            rec = recorder.Recorder()
            rec.start()
            self.recorder = rec
            self.elapsed = 0
            self.timer.start()
            self.toggle_item.title = "Stop & Summarize"
            self.status_item.title = "Recording…"
        except Exception as e:
            rumps.notification("Meeting Bot", "Could not start recording", str(e))
        finally:
            self.busy = False

    def _stop(self) -> None:
        self.busy = True
        self.timer.stop()
        self.title = "🎙"
        self.toggle_item.title = "Start Recording"
        self.status_item.title = "Transcribing…"
        rec, self.recorder = self.recorder, None
        if rec is None:
            self.busy = False
            return
        try:
            rec.stop()
            if summarize.have_key():
                self.status_item.title = "Summarizing…"
            note_path, summarized = rec.finalize()
            self.status_item.title = "Idle"
            rumps.notification(
                "Meeting Bot",
                "Note ready" if summarized else "Transcript saved (no API key)",
                str(note_path.name),
            )
            subprocess.run(["open", str(note_path)], check=False)
        except Exception as e:
            self.status_item.title = "Error"
            rumps.notification("Meeting Bot", "Failed to finish meeting", str(e))
        finally:
            self.busy = False

    def tick(self, _: object) -> None:
        self.elapsed += 1
        m, s = divmod(self.elapsed, 60)
        self.title = f"🔴 {m:02d}:{s:02d}"

    # -- shortcuts -------------------------------------------------------

    def open_last_note(self, _: object) -> None:
        recent = notes.list_notes()
        if recent:
            subprocess.run(["open", str(recent[0])], check=False)
        else:
            rumps.notification("Meeting Bot", "No notes yet", "Record a meeting first.")

    def open_notes_folder(self, _: object) -> None:
        config.NOTES_DIR.mkdir(parents=True, exist_ok=True)
        subprocess.run(["open", str(config.NOTES_DIR)], check=False)


def main() -> None:
    MeetingBotApp().run()


if __name__ == "__main__":
    main()
