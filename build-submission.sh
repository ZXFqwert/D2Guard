#!/bin/sh
# Package sources, frozen weights and the listed demo evidence into ../D2Guard-submission.zip
cd "$(dirname "$0")" || exit 1
PY=python3
[ -x .venv/bin/python ] && PY=.venv/bin/python
exec "$PY" tools/package_delivery.py --output ../D2Guard-submission.zip
