"""Freeze validation-only selection before opening the final gold test set."""
import argparse,hashlib,json,shutil,time,signal
from pathlib import Path
import numpy as np
from stage_d_prime_data import ROOT,OUT,PREREG,read_jsonl,write_jsonl,LABELS,view,sha
from stage_d_prime_model import predict,metrics
from train_stage_d import hashes

def budget():
    start=json.loads((OUT/'training-evaluation-clock.json').read_text())['started_unix']
    if time.time()-start>=5400:raise TimeoutError('Training + evaluation 90-minute stop loss')

def select():
    trained=[json.loads((OUT/(b+'-training.json')).read_text()) for b in ('english','multilingual')]
    if any(x['status']!='completed' for x in trained):raise ValueError('Both fits must complete without overfit stop')
    chosen=max(trained,key=lambda x:(x['validation']['to_agent']['f1'],-x['best_validation_loss']))
    record={'base':chosen['base'],'selection_inputs':{x['base']:{'validation':x['validation'],'best_validation_loss':x['best_validation_loss'],'sha256':x['sha256']} for x in trained},
            'chosen_weight_sha256':chosen['sha256']['model.safetensors'],'selection_rule':PREREG['selection'],
            'selected_unix':time.time(),'threshold':chosen['threshold'],'temperature':chosen['temperature']}
    with (OUT/'selected.json').open('x') as f:json.dump(record,f,indent=2)
    print(json.dumps({'selected':chosen['base'],'validation':chosen['validation']}),flush=True)

def groups(rows,ps,threshold,predicted_labels=None):
    subsets={'C+C2':[i for i,r in enumerate(rows) if r['evaluation_set'] in ('c','c2')],
             **{name:[i for i,r in enumerate(rows) if r['evaluation_set']==name] for name in ('c','c2','heldout')}}
    output={}
    for name,idx in subsets.items():
        if not idx:continue
        output[name]=metrics([rows[i] for i in idx],ps[idx],threshold,[predicted_labels[i] for i in idx] if predicted_labels is not None else None)
        output[name]['languages']={lang:metrics([rows[i] for i in idx if rows[i]['language']==lang],ps[[i for i in idx if rows[i]['language']==lang]],threshold,
             [predicted_labels[i] for i in idx if rows[i]['language']==lang] if predicted_labels is not None else None)
             for lang in sorted({rows[i]['language'] for i in idx})}
    return output

def eval_models():
    import torch
    from laya.train import load_checkpoint
    chosen=json.loads((OUT/'selected.json').read_text()) # must exist BEFORE gold opens
    rows=read_jsonl(OUT/'gold.jsonl')+[{**r,'evaluation_set':'heldout'} for r in read_jsonl(OUT/'admitted.jsonl') if r['split']=='heldout']
    assert sum(r['evaluation_set']!='heldout' for r in rows)==1014
    write_jsonl(OUT/'evaluation-input.jsonl',rows)
    configs=[('original_english',ROOT/'.local/models/laya-english',1,None),
             ('original_multilingual',Path('/home/roots/d2guard-v4-lab/models/verified-laya-e4e9ddf'),1,None),
             ('finetuned_'+chosen['base'],OUT/('D2Guard-Laya-'+chosen['base']),chosen['temperature'],chosen['threshold'])]
    torch.set_num_threads(4);device=torch.device('cuda:0');results={};predictions=[]
    for name,path,temp,threshold in configs:
        budget();before=hashes(path);work=OUT/('eval-copy-'+name)
        if not work.exists():shutil.copytree(path,work)
        model,tok,cfg=load_checkpoint(str(work));model.to(device).eval()
        # One batched pass covers every window; repeated gold observations remain
        # separate evaluation units, matching the preregistered denominators.
        ps,z,lat,windows=predict(model,tok,rows,device,temp)
        results[name]={'metrics':groups(rows,ps,threshold),'latency_ms_per_fragment':lat,'latency_basis':'batch wall time including tokenization / fragments',
                       'window_n':sum(windows),'sha256':before,'checkpoint_unchanged':hashes(path)==before,'temperature':temp,'threshold':threshold}
        predictions.extend({'id':r['id'],'model':name,'probabilities':dict(zip(LABELS,map(float,p))),'windows':n} for r,p,n in zip(rows,ps,windows))
        del model;torch.cuda.empty_cache();budget()
        (OUT/'model-evaluation.json').write_text(json.dumps(results,ensure_ascii=False,indent=2),encoding='utf8')
        write_jsonl(OUT/'model-predictions.jsonl',predictions)
        print(json.dumps({'model':name,'C+C2':results[name]['metrics']['C+C2'],'latency_ms':lat}),flush=True)

def eval_judge():
    from stage_d_prime_teacher import call,RUBRIC,MODEL
    rows=read_jsonl(OUT/'evaluation-input.jsonl');unique={};mapping={}
    for r in rows:
        key=sha(json.dumps(view(r),sort_keys=True,ensure_ascii=False));unique.setdefault(key,r);mapping[r['id']]=unique[key]['id']
    source=list(unique.values());votes=[]
    with (OUT/'judge-predictions.jsonl').open('x',encoding='utf8') as stream:
        for start in range(0,len(source),16):
            budget();batch,audit=call(source[start:start+16],probabilities=True)
            for r in batch:
                if r['probabilities'][r['label']]<max(r['probabilities'].values())-1e-8:raise ValueError('Judge class disagrees with probability maximum')
                stream.write(json.dumps(r,ensure_ascii=False)+'\n')
            stream.flush();votes.extend(batch)
            print(json.dumps({'judge_done':len(votes),'total':len(source)}),flush=True)
    lookup={r['id']:r for r in votes};ps=np.asarray([[lookup[mapping[r['id']]]['probabilities'][label] for label in LABELS] for r in rows])
    predicted=[lookup[mapping[r['id']]]['label'] for r in rows]
    result={'model':MODEL,'rubric_sha256':sha(RUBRIC),'metrics':groups(rows,ps,None,predicted),'unique_requests':len(source),
            'tie_rule':'declared class must attain maximum probability; retain declared class on ties',
            'latency_ms_per_fragment':float(np.mean([r['latency_ms'] for r in votes])),
            'latency_basis':'batch request wall time divided by unique input count; includes transport and decoding'}
    (OUT/'judge-evaluation.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf8')
    print(json.dumps(result,ensure_ascii=False),flush=True)

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('action',choices=['select','models','judge']);a=p.parse_args()
    {'select':select,'models':eval_models,'judge':eval_judge}[a.action]()
