#!/usr/bin/env bash
# Install Meeting Bot on macOS: build the app + capture helper, sync the Python
# pipeline, and put the `mbot` CLI on PATH. Nothing auto-starts or runs in the
# background — you open MeetingBot.app and it only records when you click Start.
#
# Idempotent — safe to re-run after pulling changes. Uninstall: scripts/uninstall-macos.sh
set -euo pipefail

PROJECT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BIN="$HOME/.local/bin"
UV="$(command -v uv || echo /opt/homebrew/bin/uv)"
APP_NAME="${APP_NAME:-MB}"  # must match scripts/build-app.sh's output (dist/${APP_NAME}.app)

echo "▸ Meeting Bot install — project: $PROJECT"
[ -x "$UV" ] || { echo "✗ uv not found. Install: brew install uv"; exit 1; }

echo "▸ Building the app + capture helper (Swift)…"
( cd "$PROJECT/mac" && swift build -c release >/dev/null )

echo "▸ Syncing Python environment…"
( cd "$PROJECT" && "$UV" sync >/dev/null )

echo "▸ Building ${APP_NAME}.app…"
APP_NAME="$APP_NAME" bash "$PROJECT/scripts/build-app.sh" >/dev/null

echo "▸ Installing ${APP_NAME}.app to /Applications…"
rm -rf "/Applications/${APP_NAME}.app"
cp -R "$PROJECT/dist/${APP_NAME}.app" "/Applications/"
xattr -cr "/Applications/${APP_NAME}.app" 2>/dev/null || true

mkdir -p "$BIN"
echo "▸ Installing mbot CLI to $BIN/mbot"
cat > "$BIN/mbot" <<EOF
#!/bin/sh
exec "$PROJECT/.venv/bin/mbot" "\$@"
EOF
chmod +x "$BIN/mbot"

# Ensure ~/.local/bin is on PATH for interactive zsh shells.
if ! grep -q 'Meeting Bot CLI' "$HOME/.zshrc" 2>/dev/null; then
  printf '\n# Meeting Bot CLI\nexport PATH="$HOME/.local/bin:$PATH"\n' >> "$HOME/.zshrc"
  echo "  added ~/.local/bin to PATH in ~/.zshrc (open a new terminal to pick it up)"
fi

echo
echo "✓ Installed — nothing runs in the background. Next:"
echo "  1. Open ${APP_NAME}.app (Spotlight → 'Meeting Bot'). Click Start to record; Stop to make a note."
echo "  2. Optional summaries: add a free NVIDIA key in Settings (or"
echo "     echo 'NVIDIA_API_KEY=nvapi-...' > ~/.config/meetingbot/.env)."
echo "  3. First Start prompts for Microphone + Screen Recording — grant, then reopen the app."
echo
echo "  The Chrome extension is optional and NOT always-on: start its local server"
echo "  only when you want it, with 'mbot serve', then record from the extension."
