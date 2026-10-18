"""One authorized D5 data supplement; reuse D5 algorithms in a separate output directory."""
import collections
import importlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time
import stage_d5_protocol as protocol

ROOT=protocol.ROOT
PRIOR=ROOT/'.local/stage-d5'
OUT=ROOT/'.local/stage-d5-supplement'
read,save,sha,write_rows=protocol.read,protocol.save,protocol.sha,protocol.write_rows

def initialize():
    OUT.mkdir(exist_ok=True)
    if (OUT/'protocol.json').exists():return
    now=time.time()
    p=json.loads((PRIOR/'protocol.json').read_text())
    p.update(started_unix=now,data_deadline_unix=now+9000,stage_deadline_unix=now+16200,
             supplement=True,checkpoint='59b12a3',threshold=0.5,trained_bases=['multilingual'])
    save('protocol.json',p)
    for name in ('pilot-review.json','host-test-frozen.jsonl','real-test-frozen.jsonl','base-isolation-vectors.npy','base-isolation-vectors.json'):
        if (PRIOR/name).exists():shutil.copy2(PRIOR/name,OUT/name)
    frozen=[PRIOR/'admitted.jsonl',PRIOR/'synthetic-request.jsonl',PRIOR/'host-test-frozen.jsonl',PRIOR/'real-test-frozen.jsonl',ROOT/'.local/stage-d3/frozen-heldout.jsonl',ROOT/'.local/stage-d3/gold.jsonl']
    save('original-manifest.json',{str(p.relative_to(ROOT)):sha(p) for p in frozen})

def decisions_for(rows,decisions):
    expected={r['id'] for r in rows};by={}
    for d in decisions:
        if d['id'] in by:raise ValueError('Duplicate decision')
        if protocol.KINDS.get(d.get('kind'))!=d.get('label') or not d.get('reason'):raise ValueError('Invalid semantic decision')
        if d.get('reviewer')!='gpt-6.1-sol' or d.get('reasoning_effort')!='low':raise ValueError('Wrong adjudicator')
        by[d['id']]=d
    if set(by)!=expected:raise ValueError('Incomplete or extraneous decision coverage')
    return by

def assemble():
    original=read(PRIOR/'synthetic-request.jsonl')
    decisions=[d for i in range(3) for d in read(OUT/f'decisions-{i}.jsonl')]
    by=decisions_for(original,decisions)
    existing=read(PRIOR/'admitted.jsonl');oldids={r['id'] for r in original}
    rows=[r for r in existing if r['id'] not in oldids]
    from d2v2.semantic_view import semantic_view
    for r in original:
        d=by[r['id']]
        rows.append({**r,'original_label':r['label'],'label':d['label'],'kind':d['kind'],
                     'origin':'synthetic_restored','adjudication':d,'text':semantic_view(r['raw_text'])})
    if len({r['id'] for r in rows})!=len(rows):raise ValueError('Duplicate candidate IDs')
    write_rows('candidate-admitted.jsonl',rows)
    save('assembly.json',{'original_request_n':len(original),'replaced_existing_n':sum(r['id'] in oldids for r in existing),
        'adjudicated':dict(collections.Counter(r['split']+':'+by[r['id']]['label'] for r in original)),
        'kind':dict(collections.Counter(d['kind'] for d in decisions)),'candidate_n':len(rows),
        'decision_sha256':{str(i):sha(OUT/f'decisions-{i}.jsonl') for i in range(3)},'test_access_by_judges':False})

def fixed_calibrate(rows,z):
    from laya.calibrate import fit_one_temperature
    from stage_d5_model import softmax
    from stage_d2_metrics import LABELS,metrics
    targets=[[float(label==r['label']) for label in LABELS] for r in rows]
    temperature=float(fit_one_temperature(list(zip(z,targets)),min_n=900))
    return temperature,0.5,metrics(rows,softmax(z/temperature),0.5)

def validation_groups():
    import numpy as np
    from stage_d2_metrics import groups
    rows=read(OUT/'new-validation-frozen.jsonl')
    pred=read(OUT/'multilingual-validation-predictions.jsonl')
    by={r['id']:r['probabilities'] for r in pred}
    result={}
    for name,origin in [('host_inserted','real_host_injection'),('old_synthetic','synthetic_restored')]:
        part=[r for r in rows if r.get('origin')==origin]
        if not any(r['label']=='request' for r in part):raise ValueError('Validation request source missing')
        result[name]=groups(part,np.asarray([by[r['id']] for r in part]),.5)
    save('validation-source-metrics.json',result)

def run_training():
    if (OUT/'training-clock.json').exists():raise ValueError('Supplement fit already started')
    if not json.loads((OUT/'admission.json').read_text())['passed'] or not json.loads((OUT/'probe.json').read_text())['pretrain_passed']:raise ValueError('Data/probe gate failed')
    save('training-clock.json',{'started_unix':time.time()})
    files=[*ROOT.glob('stage_d*.py'),*ROOT.glob('train_stage_d*.py'),ROOT/'evaluate_stage_d5.py',*(ROOT/'src').rglob('*.py')]
    files += [OUT/n for n in ('admitted.jsonl','new-validation-frozen.jsonl','host-test-frozen.jsonl','real-test-frozen.jsonl')]
    manifest={str(p.relative_to(ROOT)):sha(p) for p in files}
    save('training-source-manifest.json',manifest)
    state={'status':'running','completed':[]}
    try:
        for step in ('smoke','fit','evaluate'):
            if any(sha(ROOT/p)!=h for p,h in manifest.items()):raise ValueError('Frozen training inputs changed')
            state['active']=step;save('training-runner.json',state)
            remaining=protocol.training_deadline(json.loads((OUT/'training-clock.json').read_text()),json.loads((OUT/'protocol.json').read_text()))-time.time()
            if remaining<=0:raise TimeoutError('Shared 60-minute training/evaluation limit')
            with (OUT/(step+'.log')).open('x',encoding='utf-8') as log:
                subprocess.run([sys.executable,'-u',__file__,step],cwd=ROOT,env={**os.environ,'CUDA_VISIBLE_DEVICES':'0','OMP_NUM_THREADS':'4','PYTHONPATH':'src:.'},stdout=log,stderr=subprocess.STDOUT,timeout=remaining,check=True)
            state['completed'].append(step)
        state['status']='completed'
    except Exception as e:
        state.update(status='stopped',error_type=type(e).__name__,reason=str(e));raise
    finally:
        state['finished_unix']=time.time();save('training-runner.json',state)

def launch_regression_worker(index,smoke=False):
    name=('smoke-' if smoke else 'cell-')+str(index)
    with (OUT/(name+'.log')).open('x',encoding='utf-8') as log:
        subprocess.run([sys.executable,__file__,'regression-worker',str(index),*(['--smoke'] if smoke else [])],
                       stdout=log,stderr=subprocess.STDOUT,timeout=300,check=True,env=os.environ.copy())
    return json.loads((OUT/(name+'.json')).read_text())

def main(action):
    protocol.OUT=OUT
    if action=='init':initialize()
    elif action=='assemble':assemble()
    elif action=='isolate':importlib.import_module('stage_d5_isolation').main()
    elif action=='admit':importlib.import_module('stage_d5_admit').finalize()
    elif action=='probe':importlib.import_module('stage_d5_probe').main(1)
    elif action=='train':run_training()
    elif action in ('smoke','fit'):
        module=importlib.import_module('train_stage_d5');module.calibrate=fixed_calibrate
        module.main('multilingual',1,smoke=action=='smoke')
        if action=='fit':validation_groups()
    elif action=='evaluate':importlib.import_module('evaluate_stage_d5').main(('multilingual',))
    elif action=='offline':importlib.import_module('stage_d5_offline').main()
    elif action=='regression':
        module=importlib.import_module('stage_d5_regression');module.launch=launch_regression_worker;module.main()
    elif action=='regression-worker':importlib.import_module('stage_d5_regression').worker(int(sys.argv[2]),'--smoke' in sys.argv)
    else:raise ValueError(action)

if __name__=='__main__':main(sys.argv[1])
