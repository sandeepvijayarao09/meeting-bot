#!/usr/bin/env bash
# Remove Meeting Bot: the installed app, the mbot CLI shim, and any leftover
# LaunchAgents from older installs. Leaves your notes and recordings in place.
set -euo pipefail
UID_NUM="$(id -u)"
AGENTS="$HOME/Library/LaunchAgents"

# Older versions auto-started these background agents; remove if present.
for label in com.meetingbot.serve com.meetingbot.menubar; do
  if [ -f "$AGENTS/$label.plist" ]; then
    launchctl bootout "gui/$UID_NUM/$label" 2>/dev/null || true
    rm -f "$AGENTS/$label.plist"
    echo "removed $label"
  fi
done

rm -rf "/Applications/MeetingBot.app" && echo "removed /Applications/MeetingBot.app"
rm -f "$HOME/.local/bin/mbot" && echo "removed ~/.local/bin/mbot"
echo "(notes, recordings, and the PATH line in ~/.zshrc were left in place)"
