#!/usr/bin/env bash
# Install Meeting Bot on macOS: build, deps, `mbot` on PATH, and LaunchAgents
# that auto-start the capture server + menu bar app at login.
#
# Idempotent — safe to re-run after pulling changes. Uninstall: scripts/uninstall-macos.sh
set -euo pipefail

PROJECT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
UID_NUM="$(id -u)"
AGENTS="$HOME/Library/LaunchAgents"
LOGS="$HOME/Library/Logs/meetingbot"
BIN="$HOME/.local/bin"
UV="$(command -v uv || echo /opt/homebrew/bin/uv)"

echo "▸ Meeting Bot install — project: $PROJECT"
[ -x "$UV" ] || { echo "✗ uv not found. Install: brew install uv"; exit 1; }

echo "▸ Building native capture + app (Swift)…"
( cd "$PROJECT/mac" && swift build -c release >/dev/null )

echo "▸ Syncing Python environment…"
( cd "$PROJECT" && "$UV" sync >/dev/null )

mkdir -p "$BIN" "$LOGS" "$AGENTS"

echo "▸ Installing mbot CLI to $BIN/mbot"
cat > "$BIN/mbot" <<EOF
#!/bin/sh
exec "$PROJECT/.venv/bin/mbot" "\$@"
EOF
chmod +x "$BIN/mbot"

# Ensure ~/.local/bin is on PATH for interactive zsh shells.
if ! grep -q 'meetingbot CLI' "$HOME/.zshrc" 2>/dev/null; then
  printf '\n# Meeting Bot CLI\nexport PATH="$HOME/.local/bin:$PATH"\n' >> "$HOME/.zshrc"
  echo "  added ~/.local/bin to PATH in ~/.zshrc (open a new terminal to pick it up)"
fi

write_agent() {
  local label="$1"; shift
  local plist="$AGENTS/$label.plist"
  local keepalive="$1"; shift
  local args_xml=""
  for a in "$@"; do args_xml="$args_xml        <string>$a</string>\n"; done
  printf '%b' "<?xml version=\"1.0\" encoding=\"UTF-8\"?>
<!DOCTYPE plist PUBLIC \"-//Apple//DTD PLIST 1.0//EN\" \"http://www.apple.com/DTDs/PropertyList-1.0.dtd\">
<plist version=\"1.0\">
<dict>
    <key>Label</key>
    <string>$label</string>
    <key>ProgramArguments</key>
    <array>
$args_xml    </array>
    <key>WorkingDirectory</key>
    <string>$PROJECT</string>
    <key>RunAtLoad</key>
    <true/>
    <key>KeepAlive</key>
    <$keepalive/>
    <key>StandardOutPath</key>
    <string>$LOGS/${label##*.}.log</string>
    <key>StandardErrorPath</key>
    <string>$LOGS/${label##*.}.log</string>
</dict>
</plist>
" > "$plist"
  launchctl bootout "gui/$UID_NUM/$label" 2>/dev/null || true
  launchctl bootstrap "gui/$UID_NUM" "$plist"
  echo "  loaded $label"
}

echo "▸ Installing LaunchAgents…"
write_agent com.meetingbot.serve   true  "$PROJECT/.venv/bin/mbot" serve
write_agent com.meetingbot.menubar false "$PROJECT/.venv/bin/mbot-menubar"

sleep 3
echo "▸ Verifying…"
if lsof -nP -iTCP:8765 -sTCP:LISTEN >/dev/null 2>&1; then
  echo "  ✓ capture server listening on 127.0.0.1:8765"
else
  echo "  ⚠ server not yet listening — check $LOGS/serve.log"
fi
echo
echo "✓ Installed. Next:"
echo "  1. Add your free NVIDIA key:  mkdir -p ~/.config/meetingbot && echo 'NVIDIA_API_KEY=nvapi-...' > ~/.config/meetingbot/.env"
echo "  2. Load the Chrome extension (chrome://extensions → Load unpacked → chrome-extension/)"
echo "  3. First recording will prompt for Microphone + Screen Recording permission."
echo "  Run 'mbot doctor' (in a new terminal) to check everything."
