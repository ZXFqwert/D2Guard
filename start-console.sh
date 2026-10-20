#!/bin/sh
# D2Guard security console (Linux): http://127.0.0.1:8768/
# After setup-linux.sh, live Agent runs are enabled; without it, only the bundled run evidence can be browsed.
cd "$(dirname "$0")" || exit 1
PORT="${PORT:-8768}"
if [ -x .venv/bin/python ] && [ -f .local/s1.json ]; then
  echo "Open http://127.0.0.1:$PORT/ in a browser (Ctrl+C to stop)"
  exec .venv/bin/python tools/console_launcher.py --port "$PORT" --no-browser
fi
if [ ! -x .venv/bin/python ]; then
  echo "Full setup not found (run: sh setup-linux.sh). Starting in history-only mode ..."
  python3 -m venv .venv && .venv/bin/python -m pip install -r requirements-core.txt || exit 1
fi
echo "Open http://127.0.0.1:$PORT/ in a browser (Ctrl+C to stop)"
exec .venv/bin/python console/server.py --repo "$PWD" --port "$PORT"
