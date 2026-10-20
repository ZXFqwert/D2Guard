#!/bin/sh
# D2Guard full runtime setup (Linux): .venv, Python deps, pinned Pi 0.85.1, provider and fast-mirror config.
cd "$(dirname "$0")" || exit 1
command -v python3 >/dev/null || { echo "Install Python 3.11+ first"; exit 1; }
python3 tools/setup_runtime.py
