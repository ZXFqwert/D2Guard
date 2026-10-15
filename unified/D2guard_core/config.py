"""Explicit local settings. No remote inference or weight downloads by default."""
from dataclasses import dataclass, field
from pathlib import Path
import json
import os
import sys

ROOT = Path(__file__).resolve().parent
ASSETS = ROOT if (ROOT / "D2guard_contract.json").is_file() else Path(sys.prefix) / "share" / "d2guard_core"
CONTRACT_PATH = ROOT.parent / "D2guard_contract.json"
if not CONTRACT_PATH.is_file():
    CONTRACT_PATH = ASSETS / "D2guard_contract.json"
CONTRACT = json.loads(CONTRACT_PATH.read_text(encoding="utf-8-sig"))


@dataclass
class Settings:
    db_path: Path = field(default_factory=lambda: Path(os.getenv("D2GUARD_DB", str(ROOT / "data" / "d2guard.sqlite3"))))
    policy_path: Path = field(default_factory=lambda: Path(os.getenv("D2GUARD_POLICIES", str(ASSETS / "policies.yaml"))))
    execution_root: Path = field(default_factory=lambda: Path(os.getenv("D2GUARD_EXEC_ROOT", str(ROOT))).resolve())
    signing_key: str | None = field(default_factory=lambda: os.getenv("D2GUARD_SIGNING_KEY"))
    fast_model_path: str | None = field(default_factory=lambda: os.getenv("D2GUARD_FAST_MODEL_PATH"))
    fast_backend: str = field(default_factory=lambda: os.getenv("D2GUARD_FAST_BACKEND", "laya"))
    slow_base_url: str | None = field(default_factory=lambda: os.getenv("D2GUARD_SLOW_BASE_URL"))
    slow_api_key: str | None = field(default_factory=lambda: os.getenv("D2GUARD_SLOW_API_KEY"))
    slow_model: str = field(default_factory=lambda: os.getenv("D2GUARD_SLOW_MODEL", "deepseek-chat"))
    slow_timeout: float = 5.0
