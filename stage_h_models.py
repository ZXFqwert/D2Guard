"""Read-only E0 rule/original comparison and batch=1 H1-view CPU timing."""
import hashlib
import json
import os
from pathlib import Path
import random
import shutil
import signal
import sqlite3
import sys
import time
from stage_h_run import ROOT, OUT, read, save

def e2():
    import numpy as np
    from d2v2.compression import clauses
    from stage_d2_metrics import mapped, groups
    path=ROOT/'.local/stage-d3/gold.jsonl'
    rows=mapped([json.loads(l) for l in path.read_text().splitlines() if l.strip()])
    ps=[]
    for r in rows:
        text=r['raw_text'];ds,gap=clauses(text,{'event_id':'h-e2','char_span':[0,len(text)]})
        requested=any(a.get('stance')=='requested' for d in ds for a in d.get('action_relations',[]))
        quoted=any(a.get('stance')=='quoted' for d in ds for a in d.get('action_relations',[]))
        ps.append([1.,0.,0.] if requested else [0.,1.,0.] if quoted else [0.,0.,1.])
    result={'gold_sha256':hashlib.sha256(path.read_bytes()).hexdigest(),'gold_n':len(rows),
        'rules':groups(rows,np.asarray(ps)),
        'mapping':'to_agent + for_reader -> request; data -> none; quoted unchanged',
        'rule_basis':'Any extracted requested action relation; quoted relation fallback; deterministic scores, not calibrated ECE.'}
    save(OUT/'e2.json',result)
    import torch
    from laya.train import load_checkpoint
    from stage_d5_model import predict_laya, softmax
    torch.set_num_threads(2);started=time.time()
    base=Path('/home/roots/d2guard-v4-lab/models/verified-laya-e4e9ddf')
    before=hashlib.sha256((base/'model.safetensors').read_bytes()).hexdigest()
    def expired(*args):raise TimeoutError('Original model loading exceeded 30 minutes')
    signal.signal(signal.SIGALRM,expired);signal.alarm(1800)
    try:
        copy=OUT/'original-multilingual'
        if not copy.exists():shutil.copytree(base,copy)
        model,tok,_=load_checkpoint(str(copy));model.to('cuda:0').eval()
    except Exception as exc:
        result['original']={'status':'skipped','reason':type(exc).__name__,'load_seconds':time.time()-started}
        save(OUT/'e2.json',result);return
    finally:signal.alarm(0)
    load_seconds=time.time()-started
    z,lat,counts=predict_laya(model,tok,rows,'cuda:0')
    result['original']={'status':'completed','metrics':groups(rows,softmax(z),.5),
        'temperature':1.,'threshold':.5,'prompt':'stage_d5_model.QUESTION; zero-shot, no calibration',
        'load_seconds':load_seconds,'latency_ms_per_fragment_batched':lat,'windows':sum(counts),
        'weight_sha256':before,'original_unchanged':before==hashlib.sha256((base/'model.safetensors').read_bytes()).hexdigest()}
    save(OUT/'e2.json',result)

def cpu():
    import torch
    from laya.train import load_checkpoint,items_from_rows,calibration_records
    from stage_d5_model import views_for,QUESTION
    torch.set_num_threads(4)
    config=read(ROOT/'.local/stage-d5/s1-enabled-config.json')
    base=Path(config['models']['multilingual']['path']);copy=OUT/'cpu-model'
    if not copy.exists():shutil.copytree(base,copy)
    model,tok,_=load_checkpoint(str(copy));model.to('cpu').eval()
    candidates=[]
    # Fixed sampling of actual H1 views; never gold or fabricated benchmark text.
    for p in sorted(OUT.glob('cell-*-*.json')):
        record=read(p)
        if not record.get('run_id') or record['cell']['protect']!='on':continue
        folder=ROOT/'runs'/record['run_id']
        with sqlite3.connect((folder/'state.sqlite3').resolve().as_uri()+'?mode=ro',uri=True) as db:
            sources=db.execute('SELECT s.id,s.type,e.raw FROM sources s JOIN source_events se ON s.id=se.source_id JOIN events e ON e.id=se.event_id').fetchall()
        for sid,kind,raw in sources:
            for i,view in enumerate(views_for(tok,{'raw_text':raw,'source_type':kind})):
                candidates.append((record['run_id'],sid,i,view))
    if len(candidates)<200:raise ValueError('Not yet 200 H1 views; no replacement sampling')
    sample=random.Random(20261019).sample(candidates,200)
    timings=[];metadata=[]
    for j,(rid,sid,i,view) in enumerate(sample):
        items,skipped=items_from_rows(tok,[{'state':view,'questions':{'S1':QUESTION},'expected':{'S1':'C'}}],512,192)
        if skipped or len(items)!=1:raise ValueError('CPU input view conversion failed')
        if j==0:calibration_records(model,tok,items,'cpu',512,192,batch_size=1)
        start=time.perf_counter()
        calibration_records(model,tok,items,'cpu',512,192,batch_size=1)
        timings.append((time.perf_counter()-start)*1000)
        metadata.append({'run_id':rid,'source_id':sid,'window':i,
                         'view_sha256':hashlib.sha256(json.dumps(view,ensure_ascii=False,sort_keys=True).encode()).hexdigest()})
        if (j+1)%20==0:print(json.dumps({'cpu_views_completed':j+1}),flush=True)
    from stage_h_audit import quantiles
    modelname=next((line.split(':',1)[1].strip() for line in Path('/proc/cpuinfo').read_text().splitlines() if line.startswith('model name')),None)
    save(OUT/'cpu.json',{'cpu':modelname,'threads':4,'batch_size':1,'n':len(sample),'seed':20261019,
        'candidate_views':len(candidates),'latency_ms':quantiles(timings),'individual_ms':timings,'sample':metadata,
        'basis':'One warmup excluded; encoded item inference includes calibration_records encoding/forward/CPU extraction; view construction and checkpoint load excluded.',
        'weight_sha256':hashlib.sha256((base/'model.safetensors').read_bytes()).hexdigest()})

def e3():
    import numpy as np
    from stage_d2_metrics import metrics
    path=ROOT/'.local/stage-d2/semantic-heldout-frozen.jsonl'
    rows=[json.loads(l) for l in path.read_text().splitlines() if l.strip()]
    result={'basis':'Reaggregation of saved D2 probabilities; no inference, no errors/text exported; historical broad request definition, not current D5 model.',
            'dataset_path':str(path.relative_to(ROOT)),'dataset_sha256':hashlib.sha256(path.read_bytes()).hexdigest(),'rounds':{}}
    for number in (1,2,3):
        folder=ROOT/f'.local/stage-d2/round-{number}'
        predpath=folder/'multilingual-heldout-predictions.jsonl'
        preds={r['id']:r['probabilities'] for l in predpath.read_text().splitlines() if (r:=json.loads(l))}
        cfg=read(folder/'multilingual-training.json')
        if set(preds)!={r['id'] for r in rows}:raise ValueError('Historical prediction coverage mismatch')
        ps=np.asarray([preds[r['id']] for r in rows])
        result['rounds'][str(number)]={'prediction_path':str(predpath.relative_to(ROOT)),
            'prediction_sha256':hashlib.sha256(predpath.read_bytes()).hexdigest(),'threshold':cfg['threshold'],'temperature':cfg['temperature'],
            'transform':{t:metrics([r for r in rows if r['transform']==t],ps[[i for i,r in enumerate(rows) if r['transform']==t]],cfg['threshold']) for t in sorted({r['transform'] for r in rows})}}
    save(OUT/'e3.json',result)

if __name__=='__main__':
    {'e2':e2,'e3':e3,'cpu':cpu}[sys.argv[1]]()
