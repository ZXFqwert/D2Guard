"""Summarize blinded judge probabilities on frozen evaluation inputs; no fit."""
import argparse
import hashlib
import json
import statistics
from pathlib import Path
from stage_d_data import read_jsonl,view,sha
from stage_d_metrics import stratified_metrics
from stage_d_teacher import validate_teacher_identity


def evaluate(data,annotations,model):
    rows=read_jsonl(data);votes=read_jsonl(annotations)
    validate_teacher_identity(votes,[model])
    index={r['input_sha256']:r for r in votes if r['model']==model}
    if len(index)!=len(votes):raise ValueError('Duplicate or unexpected judge records')
    records=[]
    for row in rows:
        key=sha(json.dumps(view(row),ensure_ascii=False,sort_keys=True))
        if key not in index:raise ValueError('Incomplete frozen evaluation coverage')
        vote=index[key]
        records.append({**row,'probabilities':vote['probabilities'],'input_sha256':key})
    latencies=sorted(r['latency_ms_per_item'] for r in index.values())
    return {'model':model,'actual_model':votes[0]['response_model'],
            'data_sha256':hashlib.sha256(data.read_bytes()).hexdigest(),
            'annotations_sha256':hashlib.sha256(annotations.read_bytes()).hexdigest(),
            'sets':{s:stratified_metrics([r for r in records if r['evaluation_set']==s])
                    for s in sorted({r['evaluation_set'] for r in records})},
            'unique_inputs':len(index),'latency_ms':{'mean':statistics.mean(latencies),
                'median':statistics.median(latencies),'p95':latencies[min(len(latencies)-1,int(.95*len(latencies)))]},
            'latency_basis':'API batch wall time divided by batch items, reused exact-input blinded annotations included; not comparable to single-fragment model latency',
            'confidence_basis':'judge self-reported probability distribution, uncalibrated; ECE is descriptive',
            'evaluation_fitting_performed':False}


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('data',type=Path);p.add_argument('annotations',type=Path)
    p.add_argument('output',type=Path);p.add_argument('--model',required=True);a=p.parse_args()
    if a.output.exists():raise ValueError('Never replace an existing judge evaluation')
    result=evaluate(a.data,a.annotations,a.model)
    a.output.write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf8')
    print(json.dumps({k:result[k] for k in ('model','unique_inputs','latency_ms')},ensure_ascii=False))
