import json,os,time
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
OUT=Path(os.environ.get('D2_TRAIN_DIR',ROOT/'training/work')).resolve()
def read(p):return [json.loads(l) for l in Path(p).read_text(encoding='utf-8').splitlines() if l.strip()]
def training_deadline(clock,plan):return min(clock['started_unix']+3600,plan.get('stage_deadline_unix',float('inf')))
