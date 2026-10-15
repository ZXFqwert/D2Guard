"""Use a unique project-owned test temp directory on this Windows workstation."""
from pathlib import Path
from uuid import uuid4


def pytest_configure(config):
    if not config.option.basetemp:
        root = Path(__file__).parent / '.test-runs'
        root.mkdir(exist_ok=True)
        config.option.basetemp = str(root / ('run-' + uuid4().hex))
