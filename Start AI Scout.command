#!/bin/zsh
# Double-click to start AI Scout. It opens http://localhost:8765 in your browser.
# Keep this window open while it scouts; close it (or press Ctrl+C) to stop.
cd "$(dirname "$0")/ai-scout" || exit 1
# claude (Claude Code), ffmpeg and python live here
export PATH="$HOME/.local/bin:/opt/homebrew/bin:/usr/local/bin:$PATH"

if [ ! -x .venv/bin/python ]; then
  echo "Setting up AI Scout for the first time…"
  python3 -m venv .venv && .venv/bin/pip install -q pillow "yt-dlp[default]" || { echo "Setup failed."; read -k1; exit 1; }
fi

# If it's already running, just open the page.
if lsof -iTCP:8765 -sTCP:LISTEN >/dev/null 2>&1; then
  echo "AI Scout is already running."
  open http://localhost:8765
  exit 0
fi

# YouTube changes often; keep yt-dlp current (quietly, and skip if offline).
.venv/bin/pip install -q -U "yt-dlp[default]" >/dev/null 2>&1

.venv/bin/python server.py
