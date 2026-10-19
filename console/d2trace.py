"""Compatibility entry point; the evidence projection now lives in the core."""
import os
import sys
from pathlib import Path
root = Path(os.environ.get('D2_REPO', Path(__file__).resolve().parent.parent / 'd2guard-next'))
if '--repo' in sys.argv:
    root = Path(sys.argv[sys.argv.index('--repo') + 1])
sys.path.insert(0, str(root / 'src'))
from d2v2.trace import *  # preserve existing console/test API
