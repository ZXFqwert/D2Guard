"""Frozen D4 threshold revision and two-hour experiment boundaries."""
import hashlib
import json
import time
from pathlib import Path
import numpy as np
from stage_d2_metrics import metrics

ROOT=Path(__file__).resolve().parent
OUT=ROOT/'.local/stage-d4'
D3=ROOT/'.local/stage-d3'
WEIGHT='bf2120407cc19ddd09f14093e148014238343974e3301aceb8b90e901e46980e'

def read(path):
    return [json.loads(line) for line in Path(path).read_text(encoding='utf-8').splitlines() if line.strip()]

def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()

def save(name,value):
    (OUT/name).write_text(json.dumps(value,ensure_ascii=False,indent=2),encoding='utf-8')

def budget(reserve=60):
    deadline=json.loads((OUT/'protocol.json').read_text())['deadline_unix']
    if time.time()+reserve>=deadline:raise TimeoutError('D4 two-hour wall-clock limit')
    return deadline

def choose_threshold(rows, probabilities):
    ps=np.asarray(probabilities,dtype=float)
    ps=ps/ps.sum(1,keepdims=True)
    initial=metrics(rows,ps,.5)
    if initial['request']['recall']>=.95:return .5,initial
    positives=sorted((float(ps[i,0]) for i,r in enumerate(rows) if r['label']=='request'),reverse=True)
    if not positives:raise ValueError('Validation has no request support')
    import math
    threshold=positives[math.ceil(.95*len(positives))-1]
    if threshold>.5:raise ValueError('Threshold rule inconsistency')
    return threshold,metrics(rows,ps,threshold)

def freeze_threshold():
    budget()
    rows=read(D3/'new-validation-frozen.jsonl')
    pred=read(D3/'multilingual-validation-predictions.jsonl')
    assert [r['id'] for r in rows]==[r['id'] for r in pred]
    old=json.loads((D3/'selected-before-heldout.json').read_text())
    cfg=json.loads((D3/'multilingual-training.json').read_text())
    assert old['selected']=='multilingual' and cfg['sha256']['model.safetensors']==WEIGHT
    assert cfg['temperature']==old['candidates']['multilingual']['temperature']
    assert sha(D3/'new-validation-frozen.jsonl')==old['new_validation_sha256']
    threshold,m=choose_threshold(rows,[r['probabilities'] for r in pred])
    result={'selected':'multilingual','threshold':threshold,'temperature':cfg['temperature'],
        'temperature_display':round(cfg['temperature'],6),'model_sha256':cfg['sha256'],
        'validation':m,'validation_sha256':sha(D3/'new-validation-frozen.jsonl'),
        'prediction_sha256':sha(D3/'multilingual-validation-predictions.jsonl'),
        'd3_training_metadata_sha256':sha(D3/'multilingual-training.json'),
        'd3_selection_sha256':sha(D3/'selected-before-heldout.json'),
        'frozen_unix':time.time(),'basis':'D3 new validation only; no temperature refit'}
    with (OUT/'threshold.json').open('x',encoding='utf-8') as f:json.dump(result,f,indent=2)
    print(json.dumps(result,ensure_ascii=False))

if __name__=='__main__':freeze_threshold()
