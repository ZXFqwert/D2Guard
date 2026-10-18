"""Time-only cutoff preserving completed rows and the original generation plan."""
import argparse
import collections
import json
import os
import shutil
import signal
import time
from pathlib import Path
from stage_d3_protocol import ROOT,OUT,sha

def complete_rows(path):
    raw=path.read_bytes();raw=raw[:raw.rfind(b'\n')+1]
    return [json.loads(line) for line in raw.splitlines() if line.strip()]


def main(generator):
    folder=OUT/'gapfill';policy=json.loads((folder/'cutoff-policy.json').read_text())
    if time.time()<policy['generation_cutoff_unix']:raise ValueError('Time cutoff has not arrived')
    if generator=='local':
        if os.name!='posix':raise ValueError('Local generator runs on the compute host')
        for proc in Path('/proc').iterdir():
            if not proc.name.isdigit():continue
            try:
                args=(proc/'cmdline').read_bytes().split(b'\0')
                if b'stage_d3_gapfill.py' not in args:continue
                index=args.index(b'stage_d3_gapfill.py')
                if args[index+1:index+2]!=[b'local'] or b'--smoke' in args:continue
                if (proc/'cwd').resolve()!=ROOT.resolve():raise ValueError('Unexpected generator working directory')
                os.kill(int(proc.name),signal.SIGTERM)
            except (FileNotFoundError,ProcessLookupError,PermissionError):continue
        time.sleep(1)
    statepath=folder/('generation-'+generator+'.json');state=json.loads(statepath.read_text())
    if state['attempted']==state['planned']:
        print(json.dumps({'generator':generator,'already_complete':True}));return
    archive=folder/'cutoff';archive.mkdir(exist_ok=True)
    for path in (statepath,folder/('generated-'+generator+'.jsonl')):
        target=archive/path.name
        if target.exists():raise ValueError('Cutoff already recorded')
        shutil.copy2(path,target)
    rows=complete_rows(folder/('generated-'+generator+'.jsonl'))
    generated_path=folder/('generated-'+generator+'.jsonl')
    raw=generated_path.read_bytes();complete=raw[:raw.rfind(b'\n')+1]
    if raw!=complete:generated_path.write_bytes(complete)
    observed_attempted=state['attempted']
    state['attempted']=max(observed_attempted,len(rows)+sum(state['errors'].values()))
    state['generated']=dict(collections.Counter(r['split'] for r in rows))
    # The streaming completion protocol uses planned==attempted. This derived
    # completed-work plan is explicit; the original attempt target is retained.
    state.update(original_planned=state['planned'],planned=state['attempted'],
                 stopped_by_time_cutoff=True,cutoff_unix=time.time(),
                 completed_valid_rows=len(rows),pending_attempts_abandoned=None,
                 observed_attempted_before_stop=observed_attempted,
                 attempted_count_basis='Lower bound from completed saved rows and recorded failures',
                 incomplete_tail_bytes=len(raw)-len(complete),
                 planned_scope='Completed attempts at time cutoff; initial target in original_planned')
    statepath.write_text(json.dumps(state,indent=2),encoding='utf-8')
    record={'generator':generator,'state':state,'original_state_sha256':sha(archive/statepath.name),
            'frozen_generated_sha256':sha(folder/('generated-'+generator+'.jsonl')),
            'policy_sha256':sha(folder/'cutoff-policy.json')}
    (archive/(generator+'-cutoff.json')).write_text(json.dumps(record,indent=2),encoding='utf-8')
    print(json.dumps({'generator':generator,'completed_attempts':state['attempted'],'original_planned':state['original_planned'],'valid_rows':len(rows)}))


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('generator',choices=['cloud','local']);main(p.parse_args().generator)
