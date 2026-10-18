"""Time-box an unfinished local candidate run; preserve outputs and honest counts."""
import hashlib
import json
import os
import signal
import sys
import time
from pathlib import Path

ROOT=Path(__file__).resolve().parent
OUT=ROOT/'.local/stage-d3'


def main():
    if sys.platform!='linux':raise ValueError('Compute host only')
    policy=json.loads((OUT/'data-cutoff-policy.json').read_text())
    if time.time()<policy['candidate_cutoff_unix']:raise ValueError('Registered cutoff has not arrived')
    folder=OUT/'cutoff';folder.mkdir(exist_ok=False)
    matches=[]
    for entry in Path('/proc').iterdir():
        if not entry.name.isdigit():continue
        try:
            args=(entry/'cmdline').read_bytes().split(b'\0')
            if (entry/'cwd').resolve()!=ROOT:continue
            if len(args)>=3 and Path(args[1].decode()).name=='stage_d3_data.py' and args[2]==b'local' and b'--smoke' not in args:
                matches.append(int(entry.name))
        except (OSError,UnicodeError):continue
    if len(matches)>1:raise ValueError('Ambiguous candidate process; no process stopped')
    for pid in matches:os.kill(pid,signal.SIGTERM)
    if matches:time.sleep(1)
    source=OUT/'generated-local.jsonl';raw=source.read_bytes();raw=raw[:raw.rfind(b'\n')+1]
    (folder/'generated-local.jsonl').write_bytes(raw)
    state=json.loads((OUT/'generation-local.json').read_text())
    record={'frozen_unix':time.time(),'reason':'Pre-registered time cutoff, independent of labels and evaluation results',
            'stopped_owned_pids':matches,'last_generator_progress':state,
            'complete_generated_rows':len(raw.splitlines()),'generated_sha256':hashlib.sha256(raw).hexdigest(),
            'inflight_outputs_not_recovered':bool(matches),'planned_work_may_be_incomplete':state['attempted']!=state['planned']}
    (folder/'cutoff.json').write_text(json.dumps(record,indent=2))
    print(json.dumps(record),flush=True)


if __name__=='__main__':main()
