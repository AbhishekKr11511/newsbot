#!/bin/bash
# Install (or reinstall) the every-4-hours schedule on this Mac.
# Uninstall: launchctl bootout gui/$(id -u)/com.newsbot.run && rm ~/Library/LaunchAgents/com.newsbot.run.plist
set -euo pipefail
REPO="$(cd "$(dirname "$0")/.." && pwd)"
DEST="$HOME/Library/LaunchAgents/com.newsbot.run.plist"
mkdir -p "$HOME/Library/LaunchAgents" "$REPO/logs"
python3 - "$REPO" "$DEST" <<'PY'
import sys, pathlib, html
repo, dest = sys.argv[1], sys.argv[2]
tpl = pathlib.Path(repo, "scripts", "com.newsbot.run.plist.template").read_text()
pathlib.Path(dest).write_text(tpl.replace("__REPO__", html.escape(repo)))
PY
plutil -lint "$DEST"
launchctl bootout "gui/$(id -u)/com.newsbot.run" 2>/dev/null || true
launchctl bootstrap "gui/$(id -u)" "$DEST"
echo "Installed. Runs at 00:00, 04:00, 08:00, 12:00, 16:00, 20:00. Log: $REPO/logs/run.log"
echo "Run once now:  launchctl kickstart gui/$(id -u)/com.newsbot.run"
