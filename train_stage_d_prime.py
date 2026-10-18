"""One fit for each immutable base; validation loss selects epochs and models."""
import argparse,dataclasses,hashlib,json,shutil,time,signal
from pathlib import Path
from stage_d_prime_data import ROOT,OUT,PREREG,read_jsonl,LABELS
from stage_d_prime_model import items_for,predict,metrics,select_threshold,softmax,QUESTION
from train_stage_d import hashes

class EarlyStop(Exception):pass
class OverfitStop(Exception):pass

def validate_corpus(rows,isolated):
    import collections
    from stage_d_prime_teacher import surface_check
    if not surface_check(rows)['passed']:raise ValueError('Surface feature admission gate failed')
    source={r['id']:r for r in isolated}
    if len({r['id'] for r in rows})!=len(rows):raise ValueError('Duplicate admitted id')
    if any(source.get(r['id'])!=r for r in rows):raise ValueError('Admitted corpus differs from isolated rows')
    for split,minimum in PREREG['minimum_sizes'].items():
        subset=[r for r in rows if r['split']==split]
        if len(subset)<minimum:raise ValueError('Insufficient split size: '+split)
        if not .15<=sum(r['label']=='to_agent' for r in subset)/len(subset)<=.30:raise ValueError('Invalid positive prior')
        if {r['source_kind'] for r in subset}!=set(PREREG['source_types']):raise ValueError('Missing source type')
        if not set(PREREG['obfuscations']).issubset({r['transform'] for r in subset}):raise ValueError('Missing obfuscation family')
        for label in LABELS:
            if {r['language'] for r in subset if r['label']==label}!={'en','zh','ja','ru'}:raise ValueError('Missing language/class support')
    for field in ('family','domain','source_dataset'):
        groups=collections.defaultdict(set)
        for r in rows:groups[r[field]].add(r['split'])
        if any(len(s)>1 for s in groups.values()):raise ValueError('Cross-split group leakage')

def main(name,smoke=False):
    import numpy as np,torch
    from laya.train import load_checkpoint,TrainConfig,train_model,save_checkpoint,encode_item,_forward,soft_ce_loss
    from laya.common import collate_items
    from laya.calibrate import fit_one_temperature
    base=ROOT/'.local/models/laya-english' if name=='english' else Path('/home/roots/d2guard-v4-lab/models/verified-laya-e4e9ddf')
    out=OUT/('D2Guard-Laya-'+name);marker=OUT/(name+'-fit-started.json')
    if not smoke and marker.exists():raise ValueError('A fit for this base already started; no retraining')
    gate=json.loads((OUT/'admission.json').read_text());audit=json.loads((OUT/'audit.json').read_text())
    if not gate['passed'] or not audit['passed']:raise ValueError('Admission/audit failed')
    if hashlib.sha256((OUT/'admitted.jsonl').read_bytes()).hexdigest()!=gate['admitted_sha256']:raise ValueError('Corpus hash changed')
    isolation=json.loads((OUT/'isolation.json').read_text())
    if not isolation['passed']:raise ValueError('Isolation failed')
    if hashlib.sha256((OUT/'isolated.jsonl').read_bytes()).hexdigest()!=isolation['admitted_sha256']:raise ValueError('Isolated corpus hash changed')
    if out.exists() or out.is_symlink() or out==base or base in out.parents:raise ValueError('Output must be new and independent')
    clock=OUT/'training-evaluation-clock.json'
    if not smoke and not clock.exists():
        with clock.open('x') as f:json.dump({'started_unix':time.time()},f)
    def budget(*args):
        if clock.exists() and time.time()-json.loads(clock.read_text())['started_unix']>=5400:raise TimeoutError('Training + evaluation 90-minute stop loss')
    if clock.exists():
        signal.signal(signal.SIGALRM,lambda *args:(_ for _ in ()).throw(TimeoutError('90-minute stop loss')))
        signal.alarm(max(1,int(5400-time.time()+json.loads(clock.read_text())['started_unix'])))
    budget();start=time.time();original=hashes(base)
    work=OUT/('base-work-'+name)
    if not work.exists():shutil.copytree(base,work)
    if hashes(work)['model.safetensors']!=original['model.safetensors']:raise ValueError('Working base weight mismatch')
    model,tok,cfg=load_checkpoint(str(work));torch.set_num_threads(4);torch.manual_seed(PREREG['seed'])
    if not torch.cuda.is_available() or 'A100' not in torch.cuda.get_device_name(0):raise RuntimeError('Allocated A100 required')
    device=torch.device('cuda:0');model.to(device)
    rows=read_jsonl(OUT/'admitted.jsonl');validate_corpus(rows,read_jsonl(OUT/'isolated.jsonl'))
    train=[r for r in rows if r['split']=='train'];val=[r for r in rows if r['split']=='validation']
    items,mapping=items_for(tok,train)
    if any(b-a!=1 for a,b in mapping):raise ValueError('Training fragment exceeds whole-view budget')
    config=TrainConfig(epochs=8,micro_batch=16,grad_accum=1,encoder_lr=1e-5,head_lr=5e-5,loss='soft-ce',
        shuffle_options=('choice',),seed=PREREG['seed'],max_len=512,head_max_len=192,log_every=50,amp=True,gradient_checkpointing=True,calib_frac=0)
    if smoke:
        model.train();batch=collate_items([[encode_item(tok,it,512,192) for it in items[:4]]],tok.pad_token_id)
        z=_forward(model,batch,device,True,False);loss=soft_ce_loss(z,batch['target'].to(device),batch['marker_mask'].to(device));loss.backward()
        result={'kind':'GPU forward/backward smoke; no optimizer step','passed':bool(torch.isfinite(loss)) and all(p.grad is None or torch.isfinite(p.grad).all() for p in model.parameters()),
                'loss':float(loss.detach()),'base_unchanged':hashes(base)==original,'seconds':time.time()-start}
        (OUT/(name+'-smoke.json')).write_text(json.dumps(result));print(json.dumps(result));return
    with marker.open('x') as f:json.dump({'started_unix':time.time(),'config':dataclasses.asdict(config),'base_sha256':original},f)
    history=[];best=float('inf');best_epoch=None;stale=0;best_path=OUT/(name+'-best-work');stop='epochs_max'
    def epoch_end(epoch,loss):
        nonlocal best,best_epoch,stale
        budget();ps,z,lat,windows=predict(model,tok,val,device)
        truth=np.asarray([LABELS.index(r['label']) for r in val]);val_loss=float(-np.log(np.maximum(ps[np.arange(len(ps)),truth],1e-12)).mean())
        accuracy=float((ps.argmax(axis=1)==truth).mean())
        if not np.isfinite(loss) or not np.isfinite(val_loss):raise RuntimeError('Nonfinite loss')
        entry={'epoch':epoch+1,'train_loss':float(loss),'validation_loss':val_loss,'validation_accuracy':accuracy,'seconds':time.time()-start}
        history.append(entry);print(json.dumps(entry),flush=True)
        (OUT/(name+'-epochs.json')).write_text(json.dumps(history,indent=2))
        if loss<.01 and len(history)>=3 and accuracy<=max(x['validation_accuracy'] for x in history[-3:-1])+.005:
            raise OverfitStop('Training loss below .01 without validation accuracy improvement')
        if val_loss<best-.002:
            best=val_loss;best_epoch=epoch+1;stale=0;save_checkpoint(model,tok,cfg,str(best_path))
        else:stale+=1
        if stale>=2:raise EarlyStop('Validation loss patience exhausted')
        model.train()  # calibration_records switches to eval; preserve optimizer state.
    try:train_model(model,tok,items,config,device,512,192,on_epoch_end=epoch_end)
    except EarlyStop:stop='validation_loss_early_stop'
    except OverfitStop as exc:
        result={'status':'stop_overfit','base':name,'reason':str(exc),'history':history,'base_unchanged':hashes(base)==original,'seconds':time.time()-start,
                'config':dataclasses.asdict(config),'original_sha256':original,'best_epoch':best_epoch,
                'unpublished_best_work_sha256':hashes(best_path) if best_path.exists() else {},'published':False}
        (OUT/(name+'-training.json')).write_text(json.dumps(result,indent=2));print(json.dumps(result),flush=True);raise SystemExit(3)
    del model;torch.cuda.empty_cache();model,tok,cfg=load_checkpoint(str(best_path));model.to(device)
    ps,z,lat,windows=predict(model,tok,val,device)
    targets=[[float(k==r['label']) for k in LABELS] for r in val]
    temperature=fit_one_temperature(list(zip(z,targets)),min_n=600);ps=softmax(z/temperature)
    threshold=select_threshold(val,ps);validation=metrics(val,ps,threshold)
    cfg.update(model_name='D2Guard-Laya-D-prime',fine_tuned=True,max_len=512,head_max_len=192,
        d2guard_s1_question=QUESTION,
        d2guard_scope='S1 only; observation mode pending acceptance',
        d2guard_calibration={'S1:4':{'temperature':temperature,'threshold':threshold,'threshold_kind':'to_agent_probability','source':'validation_only'}},
        d2guard_training=dataclasses.asdict(config))
    save_checkpoint(model,tok,cfg,str(out));budget()
    if hashes(base)!=original:raise RuntimeError('Immutable base modified')
    result={'status':'completed','base':name,'config':dataclasses.asdict(config),'history':history,'stop_reason':stop,'best_epoch':best_epoch,
            'temperature':temperature,'threshold':threshold,'validation':validation,'best_validation_loss':best,'model_path':str(out),
            'original_sha256':original,'original_unchanged':True,'sha256':hashes(out),'seconds':time.time()-start}
    (OUT/(name+'-training.json')).write_text(json.dumps(result,indent=2));print(json.dumps(result),flush=True)

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('base',choices=['english','multilingual']);p.add_argument('--smoke',action='store_true');a=p.parse_args();main(a.base,a.smoke)
