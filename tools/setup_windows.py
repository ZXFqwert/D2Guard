"""Compatibility entry point for the shared project runtime installer."""
import runpy
from pathlib import Path

if __name__ == "__main__":
    runpy.run_path(str(Path(__file__).with_name("setup_runtime.py")), run_name="__main__")
