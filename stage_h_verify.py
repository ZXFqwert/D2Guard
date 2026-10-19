"""Deterministic failure + 10% random local evidence verification; no model calls."""
import json
import math
from pathlib import Path
import random
import re
import sys
import zipfile
from stage_h_run import ROOT,OUT,read,save

def pack():
    data=read(OUT/'aggregate.json');records=[r for r in data['records'] if r.get('run_id')]
    failed=[r['run_id'] for r in records if not r.get('verify_v2',{}).get('all_passed')]
    good=sorted(r['run_id'] for r in records if r['run_id'] not in failed)
    sampled=random.Random(20261019).sample(good,math.ceil(len(good)*.1)) if good else []
    selected=set(failed+sampled);dependencies=set()
    def walk(v):
        if isinstance(v,dict):
            if isinstance(v.get('writer_run_id'),str):dependencies.add(v['writer_run_id'])
            for x in v.values():walk(x)
        elif isinstance(v,list):
            for x in v:walk(x)
    for r in records:
        if r['run_id'] in selected:walk(r.get('verify_v2'))
    selection={'seed':20261019,'failed':failed,'random':sampled,'selected':sorted(selected),'dependencies':sorted(dependencies)}
    save(OUT/'local-sample.json',selection)
    with zipfile.ZipFile(OUT/'sample.zip','w',zipfile.ZIP_DEFLATED) as z:
        for rid in sorted(selected|dependencies):
            if not re.fullmatch(r'[0-9]{8}-[0-9]{6}-[a-f0-9]{6}',rid):raise ValueError('Invalid run id')
            folder=ROOT/'runs'/rid
            for p in folder.rglob('*'):
                if p.is_file():
                    if not p.resolve().is_relative_to(folder.resolve()):raise ValueError('Evidence path escaped run')
                    z.write(p,p.relative_to(ROOT))
    print(json.dumps({'selected':len(selected),'dependencies':len(dependencies),'bytes':(OUT/'sample.zip').stat().st_size}))

def extract():
    selection=read(OUT/'local-sample.json');allowed=set(selection['selected']+selection['dependencies']);written=0
    with zipfile.ZipFile(OUT/'sample.zip') as z:
        for entry in z.infolist():
            parts=Path(entry.filename).parts
            if len(parts)<3 or parts[0]!='runs' or parts[1] not in allowed:raise ValueError('Unexpected archive target')
            target=ROOT.joinpath(*parts).resolve()
            if not target.is_relative_to((ROOT/'runs'/parts[1]).resolve()):raise ValueError('Archive traversal')
            content=z.read(entry)
            if target.exists():
                if target.read_bytes()!=content:raise ValueError('Existing evidence differs: '+str(target))
            else:
                target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(content);written+=1
    print(json.dumps({'written':written}))

def verify_local():
    from verify_v2 import verify
    from stage_f_audit import audit_run
    records={r['run_id']:r for r in read(OUT/'aggregate.json')['records'] if r.get('run_id')};rows=[]
    selection=read(OUT/'local-sample.json')
    for rid in selection['selected']:
        v=verify(ROOT/'runs'/rid);a=audit_run(ROOT/'runs'/rid);r=records[rid]
        same=v['checks']==r['verify_v2']['checks'] and v['all_passed']==r['verify_v2']['all_passed'] and a['passed']==r['trace_audit']['passed']
        rows.append({'run_id':rid,'verified':v['all_passed'],'trace_passed':a['passed'],'matches_remote':same,
                     'failed_checks':[k for k,x in v['checks'].items() if not x]})
    result={'selection':selection,'runs':rows,'passed':all(r['matches_remote'] for r in rows)}
    save(OUT/'local-verification.json',result)
    print(json.dumps({'n':len(rows),'matches':result['passed']}))

if __name__=='__main__':{'pack':pack,'extract':extract,'verify':verify_local}[sys.argv[1]]()
