"""Validation-only selection, independent aggregate evaluation, one final gold lock."""
import argparse,hashlib,json,shutil,signal,time
from pathlib import Path
import numpy as np
from stage_d2_data import ROOT,OUT,read
from stage_d2_metrics import LABELS,mapped,groups
from stage_d2_model import predict_laya,predict_baseline,softmax
from train_stage_d2 import file_hashes


def setup_budget(folder):
    deadline=json.loads((folder/'training-evaluation-clock.json').read_text())['started_unix']+5400
    if time.time()>=deadline:raise TimeoutError('Training/evaluation budget exhausted')
    signal.signal(signal.SIGALRM,lambda *args:(_ for _ in ()).throw(TimeoutError('Training/evaluation 90-minute stop')))
    signal.alarm(max(1,int(deadline-time.time())))


def evaluate(name,path,rows,temperature=1.,threshold=.5,existing=False):
    import torch
    torch.set_num_threads(4);device=torch.device('cuda:0');before=file_hashes(path)
    if name in ('modernbert','existing_classifier'):
        from transformers import AutoModelForSequenceClassification,AutoTokenizer
        tok=AutoTokenizer.from_pretrained(path,local_files_only=True)
        model=AutoModelForSequenceClassification.from_pretrained(path,local_files_only=True).to(device).eval()
        z,lat,windows=predict_baseline(model,tok,rows,device,existing=existing)
        if existing:
            labels={int(k):str(v).lower() for k,v in model.config.id2label.items()}
            ids=[i for i,label in labels.items() if 'injection' in label]
            if len(ids)!=1:raise ValueError('Cannot resolve classifier injection label without guessing')
            p=softmax(z)[:,ids[0]];ps=np.column_stack([p,np.zeros(len(p)),1-p])
        else:ps=softmax(z/temperature)
    else:
        from laya.train import load_checkpoint
        copy=path.parent/('evaluation-copy-'+path.name)
        if not copy.exists():shutil.copytree(path,copy)
        model,tok,cfg=load_checkpoint(str(copy));model.to(device).eval();z,lat,windows=predict_laya(model,tok,rows,device);ps=softmax(z/temperature)
    result={'metrics':groups(rows,ps,threshold),'latency_ms_per_fragment':lat,'latency_basis':'one batched pass including tokenization divided by all fragments',
            'window_n':sum(windows),'sha256':before,'original_unchanged':before==file_hashes(path),'temperature':temperature,'threshold':threshold}
    if not result['original_unchanged']:raise ValueError('Evaluation mutated published model')
    del model;torch.cuda.empty_cache();return result,ps


def passes(value):
    m=value['all'];return m['request']['recall']>=.85 and m['request']['precision']>=.85 and m['none_fpr'] is not None and m['none_fpr']<=.03 and m['ece_request_10_bins']<=.10


def per_round(round_number):
    folder=OUT/f'round-{round_number}';setup_budget(folder)
    manifest=json.loads((folder/'training-source-manifest.json').read_text())
    heldout_path=OUT/'semantic-heldout-frozen.jsonl'
    heldout_key=str(heldout_path.relative_to(ROOT))
    if hashlib.sha256(heldout_path.read_bytes()).hexdigest()!=manifest['sha256'][heldout_key]:raise ValueError('Frozen heldout changed after training started')
    trained={name:json.loads((folder/(name+'-training.json')).read_text()) for name in ('english','multilingual','modernbert')}
    if any(v['status']!='completed' for v in trained.values()):raise ValueError('All fits must restore and calibrate before evaluation')
    if any(file_hashes(folder/('D2Guard-'+name))!=value['sha256'] for name,value in trained.items()):raise ValueError('A trained checkpoint changed before evaluation')
    selected=max(('english','multilingual'),key=lambda name:(trained[name]['validation']['request']['f1'],-trained[name]['best_validation_loss']))
    selection={'base':selected,'round':round_number,'selected_unix':time.time(),'basis':'validation request F1 then lower validation NLL',
               'validation':{name:v['validation'] for name,v in trained.items()},'sha256':trained[selected]['sha256'],'threshold':trained[selected]['threshold'],'temperature':trained[selected]['temperature']}
    with (folder/'selected-before-heldout.json').open('x') as f:json.dump(selection,f,indent=2)
    rows=read(OUT/'semantic-heldout-frozen.jsonl')
    rows=[{**r,'evaluation_set':r['split']} for r in rows]
    results={};validation_rows=[r for r in read(folder/'admitted.jsonl') if r['split']=='validation']
    for name in ('english','multilingual','modernbert','existing_classifier'):
        path=OUT/'pretrained-classifier' if name=='existing_classifier' else folder/('D2Guard-'+name)
        config=trained.get(name,{'temperature':1.,'threshold':.5})
        if name=='existing_classifier' and round_number>1:
            first_folder=OUT/'round-1';first_manifest=json.loads((first_folder/'training-source-manifest.json').read_text())
            immutable_names=['.local/stage-d2/semantic-heldout-frozen.jsonl','.local/stage-d2/validation-frozen.jsonl','stage_d2_model.py','stage_d2_metrics.py']
            if all(hashlib.sha256((ROOT/key).read_bytes()).hexdigest()==first_manifest['sha256'][key] for key in immutable_names):
                result=json.loads((first_folder/'round-evaluation.json').read_text())['models'][name]
                if file_hashes(path)!=result['sha256']:raise ValueError('Published existing classifier changed')
                saved=read(first_folder/(name+'-heldout-predictions.jsonl'))
                if [r['id'] for r in saved]!=[r['id'] for r in rows]:raise ValueError('Cached baseline input order changed')
                result['reused_from_round']=1
                result['latency_basis']+='; immutable control reused from round 1'
                results[name]=result
                with (folder/(name+'-heldout-predictions.jsonl')).open('x') as f:
                    for record in saved:f.write(json.dumps(record)+'\n')
                print(json.dumps({'base':name,'heldout':result['metrics']['all'],'reused_from_round':1}),flush=True)
                continue
        result,ps=evaluate(name,path,rows,config['temperature'],config['threshold'],existing=name=='existing_classifier')
        if name=='existing_classifier':
            validation_result,_=evaluate(name,path,validation_rows,existing=True)
            result['validation_metrics']=validation_result['metrics']
            result['validation_latency_ms_per_fragment']=validation_result['latency_ms_per_fragment']
        else:
            saved={r['id']:r['probabilities'] for r in read(folder/(name+'-validation-predictions.jsonl'))}
            result['validation_metrics']=groups(validation_rows,[saved[r['id']] for r in validation_rows],config['threshold'])
        results[name]=result
        with (folder/(name+'-heldout-predictions.jsonl')).open('x') as f:
            for row,p in zip(rows,ps):f.write(json.dumps({'id':row['id'],'probabilities':list(map(float,p))})+'\n')
        print(json.dumps({'base':name,'heldout':result['metrics']['all']}),flush=True)
    selected_result=results[selected];semantic=selected_result['metrics']['evaluation_set']['semantic_heldout']
    result={'selected':selection,'models':results,'passed':passes(selected_result['metrics']) and passes({'all':semantic}) and trained[selected]['posttrain_probe_passed'],
            'gate':'semantic-only and combined semantic+public must both pass; posttrain probe gain >=.03',
            'training_evaluation_seconds':time.time()-json.loads((folder/'training-evaluation-clock.json').read_text())['started_unix']}
    with (folder/'round-evaluation.json').open('x',encoding='utf-8') as f:json.dump(result,f,ensure_ascii=False,indent=2)
    # Only validation mistakes may inform later generation improvements.
    val=[r for r in read(folder/'admitted.jsonl') if r['split']=='validation'];pred={r['id']:r['probabilities'] for r in read(folder/(selected+'-validation-predictions.jsonl'))}
    with (folder/'validation-errors.jsonl').open('x',encoding='utf-8') as f:
        for row in val:
            p=pred[row['id']];label='request' if p[0]>=selection['threshold'] else LABELS[1+int(np.argmax(p[1:]))]
            if label!=row['label']:f.write(json.dumps({**row,'predicted':label,'probabilities':p},ensure_ascii=False)+'\n')
    print(json.dumps({'round':round_number,'selected':selected,'passed':result['passed']}),flush=True)


def freeze(round_count):
    if round_count not in (1,2,3):raise ValueError('At most three registered rounds')
    records=[json.loads((OUT/f'round-{r}/round-evaluation.json').read_text()) for r in range(1,round_count+1)]
    if round_count<3 and not records[-1]['passed']:raise ValueError('No early stop before a passing round or three completed rounds')
    # Rank candidates using validation metrics only, never holdout or gold.
    candidates=[v['selected'] for v in records]
    def validation_rank(candidate):
        training=json.loads((OUT/f"round-{candidate['round']}"/(candidate['base']+'-training.json')).read_text())
        return candidate['validation'][candidate['base']]['request']['f1'],-training['best_validation_loss']
    chosen=max(candidates,key=validation_rank)
    value={'selected':chosen,'round_count':round_count,'frozen_unix':time.time(),'gold_use':'one final inference pass after immutable selection',
           'round_passes':[r['passed'] for r in records]}
    with (OUT/'final-selection.json').open('x') as f:json.dump(value,f,indent=2)
    print(json.dumps({'final_round':chosen['round'],'base':chosen['base']}),flush=True)


def final():
    locked=json.loads((OUT/'final-selection.json').read_text());selected=locked['selected'];folder=OUT/f"round-{locked['round_count']}";setup_budget(folder)
    # Teacher transport failures must not block the independent, single local-model pass.
    cloud_path=OUT/'final-cloud-teachers.json'
    cloud_teachers=json.loads(cloud_path.read_text()) if cloud_path.exists() else None
    selected_path=OUT/f"round-{selected['round']}"/('D2Guard-'+selected['base'])
    if file_hashes(selected_path)!=selected['sha256']:raise ValueError('Selected checkpoint changed after freezing')
    with (OUT/'gold-final-started.json').open('x') as f:json.dump({'started_unix':time.time(),'selection_sha256':hashlib.sha256((OUT/'final-selection.json').read_bytes()).hexdigest()},f)
    rows=mapped(read(ROOT/'.local/stage-d-prime/gold.jsonl'));trained_folder=OUT/f"round-{selected['round']}"
    baseline=json.loads((trained_folder/'modernbert-training.json').read_text());results={}
    configs=[('original_english',ROOT/'.local/models/laya-english',1.,.5),('original_multilingual',Path('/home/roots/d2guard-v4-lab/models/verified-laya-e4e9ddf'),1.,.5),
       ('finetuned_'+selected['base'],trained_folder/('D2Guard-'+selected['base']),selected['temperature'],selected['threshold']),
       ('modernbert',trained_folder/'D2Guard-modernbert',baseline['temperature'],baseline['threshold']),('existing_classifier',OUT/'pretrained-classifier',1.,.5)]
    for name,path,temp,threshold in configs:
        result,ps=evaluate(name,path,rows,temp,threshold,existing=name=='existing_classifier');results[name]=result
        with (OUT/('gold-final-'+name+'.jsonl')).open('x') as f:
            for row,p in zip(rows,ps):f.write(json.dumps({'id':row['id'],'probabilities':list(map(float,p))})+'\n')
        print(json.dumps({'model':name,'final_gold':result['metrics']['all']}),flush=True)
    # Final teachers use exactly the normalized S1 inputs, reusing diagnostic
    # votes only when the input hash and prompt match.
    results['cloud_teachers']=cloud_teachers
    m=results['finetuned_'+selected['base']]['metrics']['all'];f1=m['request']['f1']
    passed=m['request']['recall']>=.70 and m['request']['precision']>=.80 and m['none_fpr']<=.03 and all(f1>results[k]['metrics']['all']['request']['f1'] for k in ('original_english','original_multilingual','existing_classifier'))
    value={'models':results,'gold_passed':passed,'enable_s1':passed and locked['round_passes'][selected['round']-1],
           'cloud_teachers_complete_at_model_evaluation':cloud_teachers is not None,
           'cloud_teacher_artifact':'final-cloud-teachers.json'}
    with (OUT/'final-evaluation.json').open('x') as f:json.dump(value,f,indent=2)
    print(json.dumps({'gold_passed':passed,'enable_s1':value['enable_s1']}),flush=True)


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('action',choices=['round','freeze','final']);p.add_argument('--round',type=int,default=1);a=p.parse_args()
    {'round':lambda:per_round(a.round),'freeze':lambda:freeze(a.round),'final':final}[a.action]()
