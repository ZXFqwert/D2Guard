"""Evaluate immutable checkpoints with fixed S1 metrics, never fit on gold."""
import argparse
import hashlib
import json
import shutil
import time
from pathlib import Path
from stage_d_data import ROOT,read_jsonl,write_jsonl,view,sha,LABELS
from stage_d_metrics import stratified_metrics
from train_stage_d import hashes


def evaluate(a):
    import numpy as np
    import torch
    from laya.train import load_checkpoint
    from d2v2.content_model import probabilities
    if a.output.exists():raise ValueError('Do not replace an existing evaluation result')
    torch.set_num_threads(4)
    rows=read_jsonl(a.data);manifest=json.loads(a.manifest.read_text(encoding='utf8'))
    if not rows:raise ValueError('Empty evaluation data')
    results={'data_sha256':hashlib.sha256(a.data.read_bytes()).hexdigest(),'models':{},
             'latency_basis':'one fragment at a time, synchronized GPU; unique input cache, one warmup per device',
             'view_budget':'each window <=256 tokenizer tokens; all windows included; fragment latency includes all windows'}
    predictions=[]
    for spec in manifest:
        base=Path(spec['path']);original=hashes(base)
        if spec.get('sha256')!=original:raise ValueError('Checkpoint manifest mismatch: '+spec['name'])
        work=ROOT/'.local/stage-d'/('eval-work-'+original['model.safetensors'][:16])
        if not work.exists():shutil.copytree(base,work)
        for name,expected in original.items():
            if name.endswith('.safetensors') and hashlib.file_digest((work/name).open('rb'),'sha256').hexdigest()!=expected:
                raise ValueError('Evaluation working weight mismatch')
        model,tok,cfg=load_checkpoint(str(work))
        if spec['kind']=='original':temperature=1.0
        elif spec['kind']=='finetuned':temperature=cfg['d2guard_calibration']['S1:4']['temperature']
        else:raise ValueError('Unknown checkpoint kind')
        summary={'sha256':original,'temperature':temperature,'devices':{}}
        for device_name in a.devices:
            device=torch.device(device_name);model.to(device).eval()
            with torch.no_grad():probabilities(model,tok,'Ordinary observation.','LOCAL_FILE',device,temperature)
            cache={};records=[]
            for row in rows:
                key=sha(json.dumps(view(row),sort_keys=True,ensure_ascii=False))
                if key not in cache:
                    if device.type=='cuda':torch.cuda.synchronize(device)
                    started=time.perf_counter()
                    with torch.no_grad():p,n=probabilities(model,tok,row['text'],row['source_type'],device,temperature)
                    if device.type=='cuda':torch.cuda.synchronize(device)
                    cache[key]={'probabilities':dict(zip(LABELS,map(float,p))),'windows':n,
                                'latency_ms':(time.perf_counter()-started)*1000}
                records.append({**{k:row[k] for k in ('id','label','language')},
                    'evaluation_set':row.get('evaluation_set','heldout'),**cache[key],
                    'model':spec['name'],'device':device_name,'input_sha256':key})
            latencies=[v['latency_ms'] for v in cache.values()]
            summary['devices'][device_name]={'unique_inputs':len(cache),'latency_ms':{
                'mean':float(np.mean(latencies)),'median':float(np.median(latencies)),'p95':float(np.percentile(latencies,95))},
                'sets':{s:stratified_metrics([r for r in records if r['evaluation_set']==s]) for s in sorted({r['evaluation_set'] for r in records})}}
            predictions.extend(records)
            # Preserve each completed device result if the wall-clock gate or a
            # later device fails. No rerun is silently substituted.
            results['models'][spec['name']]=summary
            write_jsonl(Path(str(a.output)+'.predictions.jsonl'),predictions)
            a.output.write_text(json.dumps(results,ensure_ascii=False,indent=2),encoding='utf8')
            print(json.dumps({'model':spec['name'],'device':device_name,'rows':len(records),'unique_inputs':len(cache)}),flush=True)
        if hashes(base)!=original:raise RuntimeError('Original checkpoint changed during evaluation')
        results['models'][spec['name']]=summary
        model.to('cpu');del model
        if torch.cuda.is_available():torch.cuda.empty_cache()
    write_jsonl(Path(str(a.output)+'.predictions.jsonl'),predictions)
    a.output.write_text(json.dumps(results,ensure_ascii=False,indent=2),encoding='utf8')


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--data',type=Path,required=True)
    p.add_argument('--manifest',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
    p.add_argument('--devices',nargs='+',default=['cuda:0','cpu']);evaluate(p.parse_args())
