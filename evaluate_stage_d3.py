"""Validation-only choice; one aggregate-only heldout and gold regression pass."""
import hashlib
import json
import shutil
import signal
import time
from pathlib import Path
import numpy as np
from stage_d3_protocol import ROOT,OUT,read,sha,budget
from stage_d3_model import predict_laya,predict_baseline,softmax,threshold_for,ensemble,nll,select_candidate,route_base
from stage_d2_metrics import mapped,metrics,groups
from train_stage_d3 import file_hashes


def grouped(rows,ps,threshold):
    result=groups(rows,ps,threshold)
    result['style']={}
    for style in sorted({r.get('family','unspecified') for r in rows}):
        idx=[i for i,r in enumerate(rows) if r.get('family','unspecified')==style]
        result['style'][style]=metrics([rows[i] for i in idx],ps[idx],threshold)
    return result


def infer(name,rows,config):
    import torch
    budget('training');torch.set_num_threads(4);device=torch.device('cuda:0')
    path=OUT/('D2Guard-'+name);before=file_hashes(path)
    if before!=config['sha256']:raise ValueError('Published candidate changed')
    if name=='modernbert':
        from transformers import AutoTokenizer,AutoModelForSequenceClassification
        tok=AutoTokenizer.from_pretrained(path,local_files_only=True)
        model=AutoModelForSequenceClassification.from_pretrained(path,local_files_only=True).to(device).eval()
        z,lat,windows=predict_baseline(model,tok,rows,device)
    else:
        from laya.train import load_checkpoint
        copy=OUT/('evaluation-copy-'+name)
        if not copy.exists():shutil.copytree(path,copy)
        model,tok,_=load_checkpoint(str(copy));model.to(device).eval()
        z,lat,windows=predict_laya(model,tok,rows,device)
    ps=softmax(z/config['temperature'])
    if before!=file_hashes(path):raise ValueError('Evaluation mutated published candidate')
    del model;torch.cuda.empty_cache()
    return ps,{'latency_ms_per_fragment':lat,'window_n':sum(windows),'original_unchanged':True}


def selected_infer(name,rows,trained):
    if name!='ensemble':return infer(name,rows,trained[name])
    modern,meta=infer('modernbert',rows,trained['modernbert'])
    routed=np.empty_like(modern);latency=meta['latency_ms_per_fragment']*len(rows);windows=meta['window_n']
    for base in ('english','multilingual'):
        idx=[i for i,r in enumerate(rows) if route_base(r['raw_text'])==base]
        if not idx:continue
        ps,m=infer(base,[rows[i] for i in idx],trained[base]);routed[idx]=ps
        latency+=m['latency_ms_per_fragment']*len(idx);windows+=m['window_n']
    return (routed+modern)/2,{'latency_ms_per_fragment':latency/len(rows),'window_n':windows,'original_unchanged':True}


def passes(m):
    return m['request']['recall']>=.85 and m['request']['precision']>=.85 and m['none_fpr'] is not None and m['none_fpr']<=.03 and m['ece_request_10_bins']<=.10


def main():
    deadline=budget('training')
    signal.signal(signal.SIGALRM,lambda *a:(_ for _ in ()).throw(TimeoutError('D3 evaluation deadline')))
    signal.alarm(max(1,int(deadline-time.time())))
    trained={name:json.loads((OUT/(name+'-training.json')).read_text()) for name in ('english','multilingual','modernbert')}
    val=read(OUT/'new-validation-frozen.jsonl');probabilities={};candidates={}
    for name,r in trained.items():
        saved=read(OUT/(name+'-validation-predictions.jsonl'))
        if [x['id'] for x in saved]!=[x['id'] for x in val]:raise ValueError('Validation order differs')
        probabilities[name]=np.asarray([x['probabilities'] for x in saved])
        candidates[name]={key:r[key] for key in ('threshold','temperature','validation','validation_nll','posttrain_probe_passed','probe_gain','best_epoch','sha256','validation_latency_ms_per_fragment')}
    combined=ensemble(val,probabilities);threshold,vm=threshold_for(val,combined)
    probe=json.loads((OUT/'probe.json').read_text());gain=vm['request']['f1']-probe['full']['validation']['all']['request']['f1'] if vm else None
    candidates['ensemble']={'threshold':threshold,'temperature':None,'validation':vm,'validation_nll':nll(val,combined),
                            'probe_gain':gain,'posttrain_probe_passed':gain is not None and gain>=.03,
                            'components':list(trained),'routing':'semantic text Cyrillic/Kana/Han alpha fraction >=0.15 -> multilingual; otherwise English; equal mean with ModernBERT'}
    selected=select_candidate(candidates)
    with (OUT/'selected-before-heldout.json').open('x',encoding='utf-8') as f:
        json.dump({'selected':selected,'selected_unix':time.time(),'basis':'new-validation constrained recall, F1, lower NLL',
                   'new_validation_sha256':sha(OUT/'new-validation-frozen.jsonl'),'candidates':candidates},f,indent=2)
    print(json.dumps({'selected':selected,'validation':{k:{'threshold':v['threshold'],'metrics':v['validation'],'probe_gain':v['probe_gain']} for k,v in candidates.items()}}),flush=True)
    if selected is None:
        (OUT/'final-evaluation.json').write_text(json.dumps({'status':'no_eligible_validation_candidate','enable_s1':False,'heldout':None,'gold':None},indent=2))
        return
    cfg=candidates[selected];threshold=cfg['threshold']
    marker={'started_unix':time.time(),'selection_sha256':sha(OUT/'selected-before-heldout.json'),
            'heldout_sha256':sha(OUT/'frozen-heldout.jsonl'),'gold_sha256':sha(OUT/'gold.jsonl'),
            'audit_exclusions_sha256':sha(ROOT/'docs/stage-d2-heldout-audit/exclusions.json')}
    with (OUT/'frozen-evaluation-started.json').open('x') as f:json.dump(marker,f,indent=2)
    # No per-fragment predictions, mistakes, text, or IDs are written for heldout.
    held=[{**r,'evaluation_set':r['split']} for r in read(OUT/'frozen-heldout.jsonl')]
    ps,lat=selected_infer(selected,held,trained)
    excluded={r['id'] for r in json.loads((ROOT/'docs/stage-d2-heldout-audit/exclusions.json').read_text())['items']}
    if len(excluded)!=5 or not excluded<={r['id'] for r in held}:raise ValueError('Audit exclusion mismatch')
    subsets={
        'full_combined':list(range(len(held))),
        'full_semantic':[i for i,r in enumerate(held) if r['split']=='semantic_heldout'],
        'adjusted_combined':[i for i,r in enumerate(held) if r['id'] not in excluded],
        'adjusted_semantic':[i for i,r in enumerate(held) if r['split']=='semantic_heldout' and r['id'] not in excluded],
        'public':[i for i,r in enumerate(held) if r['split']=='public_heldout'],
    }
    held_result={key:grouped([held[i] for i in ids],ps[ids],threshold) for key,ids in subsets.items()}
    held_pass=passes(held_result['adjusted_semantic']['all']) and passes(held_result['adjusted_combined']['all'])
    (OUT/'heldout-aggregate.json').write_text(json.dumps({'selected':selected,'metrics':held_result,'passed':held_pass,**lat},ensure_ascii=False,indent=2),encoding='utf-8')
    del ps
    gold=mapped(read(OUT/'gold.jsonl'));gp,glat=selected_infer(selected,gold,trained)
    gold_result=grouped(gold,gp,threshold);m=gold_result['all']
    gold_pass=m['request']['recall']>=.70 and m['request']['precision']>=.80 and m['none_fpr']<=.03
    oldval=read(OUT/'old-validation.jsonl');op,olat=selected_infer(selected,oldval,trained)
    value={'status':'completed','selected':selected,'threshold':threshold,'heldout':{'metrics':held_result,'passed':held_pass,**lat},
           'gold':{'metrics':gold_result,'passed':gold_pass,**glat},'old_validation':{'metrics':grouped(oldval,op,threshold),**olat},
           'enable_s1':held_pass and gold_pass,'training_evaluation_seconds':time.time()-json.loads((OUT/'training-clock.json').read_text())['started_unix'],
           'latency_basis':'batched forward/tokenization wall time per fragment; ensemble sums routed Laya and ModernBERT cost'}
    with (OUT/'final-evaluation.json').open('x',encoding='utf-8') as f:json.dump(value,f,ensure_ascii=False,indent=2)
    print(json.dumps({'selected':selected,'heldout_passed':held_pass,'gold_passed':gold_pass,'enable_s1':value['enable_s1']}),flush=True)


if __name__=='__main__':main()
