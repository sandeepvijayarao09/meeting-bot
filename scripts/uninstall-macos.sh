#!/usr/bin/env bash
# Remove Meeting Bot LaunchAgents and the mbot CLI shim. Leaves notes/recordings.
set -euo pipefail
UID_NUM="$(id -u)"
AGENTS="$HOME/Library/LaunchAgents"

for label in com.meetingbot.serve com.meetingbot.menubar; do
  launchctl bootout "gui/$UID_NUM/$label" 2>/dev/null || true
  rm -f "$AGENTS/$label.plist"
  echo "removed $label"
done
rm -f "$HOME/.local/bin/mbot"
echo "removed ~/.local/bin/mbot"
echo "(notes, recordings, and the PATH line in ~/.zshrc were left in place)"
