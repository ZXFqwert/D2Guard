"""One fit/base/round; early stop restores best epoch and continues calibration."""
import argparse,dataclasses,hashlib,json,random,shutil,signal,time
from pathlib import Path
import numpy as np
from stage_d2_data import ROOT,OUT,read
from stage_d2_model import items_for,predict_laya,predict_baseline,baseline_text,calibrate,QUESTION,softmax
from stage_d2_metrics import LABELS
from train_stage_d import hashes


class StopFit(Exception):pass


def file_hashes(folder):
    return {str(p.relative_to(folder)):hashlib.file_digest(p.open('rb'),'sha256').hexdigest() for p in folder.rglob('*') if p.is_file() and '.cache' not in p.parts}


def main(name,round_number,smoke=False):
    import torch
    folder=OUT/f'round-{round_number}';gate=json.loads((folder/'admission.json').read_text());probe=json.loads((folder/'probe.json').read_text())
    if not gate['passed'] or not probe['pretrain_passed']:raise ValueError('Data admission/probe gate failed')
    if hashlib.sha256((folder/'admitted.jsonl').read_bytes()).hexdigest()!=gate['admitted_sha256']:raise ValueError('Admitted corpus changed')
    rows=read(folder/'admitted.jsonl');train=[r for r in rows if r['split']=='train'];val=[r for r in rows if r['split']=='validation']
    if len(train)<3000 or len(val)<600:raise ValueError('Insufficient data')
    clock=folder/'training-evaluation-clock.json'
    if not clock.exists():
        with clock.open('x') as f:json.dump({'started_unix':time.time()},f)
    started=time.time();deadline=json.loads(clock.read_text())['started_unix']+5400
    def budget(*args):
        if time.time()>=deadline:raise TimeoutError('Training/evaluation 90-minute wall-clock limit')
    signal.signal(signal.SIGALRM,lambda *args:(_ for _ in ()).throw(TimeoutError('Training/evaluation 90-minute stop')))
    signal.alarm(max(1,int(deadline-time.time())));budget()
    torch.set_num_threads(4);torch.manual_seed(20261017);random.seed(20261017);np.random.seed(20261017)
    if not torch.cuda.is_available() or 'A100' not in torch.cuda.get_device_name(0):raise RuntimeError('Allocated A100 required')
    device=torch.device('cuda:0')
    base={'english':ROOT/'.local/models/laya-english','multilingual':Path('/home/roots/d2guard-v4-lab/models/verified-laya-e4e9ddf'),'modernbert':OUT/'pretrained-modernbert'}[name]
    original=file_hashes(base);copy=folder/('base-work-'+name)
    if not copy.exists():shutil.copytree(base,copy)
    output=folder/('D2Guard-'+name);best_path=folder/(name+'-best');marker=folder/(name+'-fit-started.json')
    if output.exists() or (not smoke and marker.exists()):raise ValueError('Do not repeat a fit or overwrite a checkpoint')
    if name=='modernbert':
        from transformers import AutoTokenizer,AutoModelForSequenceClassification
        tok=AutoTokenizer.from_pretrained(copy,local_files_only=True)
        model=AutoModelForSequenceClassification.from_pretrained(copy,local_files_only=True,num_labels=3,id2label=dict(enumerate(LABELS)),label2id={v:k for k,v in enumerate(LABELS)})
        predictor=lambda rs:predict_baseline(model,tok,rs,device)
        save=lambda path:(model.save_pretrained(path,safe_serialization=True),tok.save_pretrained(path))
        config={'epochs':8,'batch_size':16,'learning_rate':1e-5,'weight_decay':.01,'amp':'bfloat16','patience':2,'min_delta':.002,'seed':20261017}
    else:
        from laya.train import load_checkpoint,TrainConfig,train_model,save_checkpoint,encode_item,_forward,soft_ce_loss
        from laya.common import collate_items
        model,tok,cfg=load_checkpoint(str(copy));predictor=lambda rs:predict_laya(model,tok,rs,device)
        save=lambda path:save_checkpoint(model,tok,cfg,str(path))
        items,mapping=items_for(tok,train)
        if any(b-a!=1 for a,b in mapping):raise ValueError('Training labels require a whole fragment view')
        config_obj=TrainConfig(epochs=8,micro_batch=16,grad_accum=1,encoder_lr=1e-5,head_lr=5e-5,loss='soft-ce',shuffle_options=('choice',),seed=20261017,max_len=512,head_max_len=192,log_every=100,amp=True,gradient_checkpointing=True,calib_frac=0)
        config=dataclasses.asdict(config_obj)
    model.to(device)
    if smoke:
        model.train()
        if name=='modernbert':
            batch=tok([baseline_text(r) for r in train[:4]],padding=True,truncation=False,return_tensors='pt').to(device)
            if batch['input_ids'].shape[1]>512:raise ValueError('Baseline training input too long')
            with torch.autocast('cuda',dtype=torch.bfloat16):loss=model(**batch,labels=torch.tensor([LABELS.index(r['label']) for r in train[:4]],device=device)).loss
        else:
            batch=collate_items([[encode_item(tok,it,512,192) for it in items[:4]]],tok.pad_token_id)
            logits=_forward(model,batch,device,True,False);loss=soft_ce_loss(logits,batch['target'].to(device),batch['marker_mask'].to(device))
        loss.backward();passed=bool(torch.isfinite(loss)) and all(p.grad is None or torch.isfinite(p.grad).all() for p in model.parameters())
        result={'passed':passed,'loss':float(loss.detach()),'optimizer_steps':0,'original_unchanged':original==file_hashes(base),'seconds':time.time()-started}
        with (folder/(name+'-smoke.json')).open('x') as f:json.dump(result,f)
        print(json.dumps(result),flush=True);return
    with marker.open('x') as f:json.dump({'started_unix':time.time(),'config':config,'original_sha256':original},f,indent=2)
    history=[];best=float('inf');early_best=float('inf');best_epoch=None;stale=0;stop='epochs_max';steps={'optimizer_updates':0,'amp_attempts':0}
    def epoch_end(epoch,loss):
        nonlocal best,early_best,best_epoch,stale
        budget();z,lat,windows=predictor(val);ps=softmax(z);truth=np.array([LABELS.index(r['label']) for r in val])
        val_loss=float(-np.log(np.maximum(ps[np.arange(len(ps)),truth],1e-12)).mean());accuracy=float((ps.argmax(1)==truth).mean())
        if not np.isfinite(loss+val_loss):raise RuntimeError('Nonfinite training/validation loss')
        history.append({'epoch':epoch+1,'train_loss':float(loss),'validation_loss':val_loss,'validation_accuracy':accuracy,
           'optimizer_updates_cumulative':steps['optimizer_updates'],'amp_skipped_cumulative':max(0,steps['amp_attempts']-steps['optimizer_updates']),'seconds':time.time()-started})
        (folder/(name+'-epochs.json')).write_text(json.dumps(history,indent=2));print(json.dumps(history[-1]),flush=True)
        # min_delta controls patience, not which checkpoint is actually best.
        if val_loss<best:best=val_loss;best_epoch=epoch+1;save(best_path)
        if val_loss<early_best-.002:early_best=val_loss;stale=0
        else:stale+=1
        if loss<.01 and len(history)>=3 and accuracy<=max(x['validation_accuracy'] for x in history[-3:-1])+.005:raise StopFit('overfit_restore_best')
        if stale>=2:raise StopFit('validation_loss_early_stop')
        model.train()
    try:
        if name=='modernbert':
            model.gradient_checkpointing_enable(gradient_checkpointing_kwargs={'use_reentrant':False})
            optimizer=torch.optim.AdamW(model.parameters(),lr=1e-5,weight_decay=.01)
            scheduler=torch.optim.lr_scheduler.CosineAnnealingLR(optimizer,T_max=((len(train)+15)//16)*8,eta_min=1e-6)
            for epoch in range(8):
                indices=list(range(len(train)));random.Random(20261017+epoch).shuffle(indices);total=0.;n=0;model.train()
                for start in range(0,len(indices),16):
                    budget();part=[train[i] for i in indices[start:start+16]];batch=tok([baseline_text(r) for r in part],padding=True,truncation=False,return_tensors='pt').to(device)
                    if batch['input_ids'].shape[1]>512:raise ValueError('Baseline input exceeds 512')
                    optimizer.zero_grad(set_to_none=True)
                    with torch.autocast('cuda',dtype=torch.bfloat16):loss=model(**batch,labels=torch.tensor([LABELS.index(r['label']) for r in part],device=device)).loss
                    if not torch.isfinite(loss):raise RuntimeError('Nonfinite baseline loss')
                    loss.backward();torch.nn.utils.clip_grad_norm_(model.parameters(),1.0);optimizer.step();scheduler.step();steps['optimizer_updates']+=1
                    total+=float(loss.detach());n+=1
                epoch_end(epoch,total/n)
        else:
            from unittest.mock import patch
            from torch.optim.optimizer import register_optimizer_step_post_hook
            old_scaler_step=torch.amp.GradScaler.step
            def scaled_step(self,*args,**kwargs):
                steps['amp_attempts']+=1;return old_scaler_step(self,*args,**kwargs)
            def actual_step(*args):steps['optimizer_updates']+=1
            hook=register_optimizer_step_post_hook(actual_step)
            try:
                with patch.object(torch.amp.GradScaler,'step',scaled_step):train_model(model,tok,items,config_obj,device,512,192,on_epoch_end=epoch_end)
            finally:hook.remove()
    except StopFit as error:stop=str(error)
    if best_epoch is None:raise RuntimeError('No valid best epoch')
    if best_epoch!=min(history,key=lambda record:record['validation_loss'])['epoch']:raise RuntimeError('Restoration did not select the minimum validation loss')
    del model;torch.cuda.empty_cache()
    if name=='modernbert':model=AutoModelForSequenceClassification.from_pretrained(best_path,local_files_only=True).to(device)
    else:model,tok,cfg=load_checkpoint(str(best_path));model.to(device)
    # Lambdas deliberately capture the restored model binding.
    z,lat,windows=predictor(val);temperature,threshold,validation=calibrate(val,z);ps=softmax(z/temperature)
    if name!='modernbert':cfg.update(model_name='D2Guard-Laya-D-double-prime',d2guard_s1_question=QUESTION,d2guard_calibration={'S1:3':{'temperature':temperature,'threshold':threshold,'threshold_kind':'request_probability','source':'validation_only'}},d2guard_scope='S1 only; observation until acceptance')
    save(output);unchanged=original==file_hashes(base)
    if not unchanged:raise RuntimeError('Original weights changed')
    result={'status':'completed','base':name,'round':round_number,'config':config,'history':history,'stop_reason':stop,'best_epoch':best_epoch,'best_validation_loss':best,
            'temperature':temperature,'threshold':threshold,'validation':validation,'sha256':file_hashes(output),'original_sha256':original,'original_unchanged':unchanged,
            'steps':{**steps,'amp_skipped':max(0,steps['amp_attempts']-steps['optimizer_updates'])},'seconds':time.time()-started}
    result['probe_gain']=validation['request']['f1']-probe['full']['validation']['all']['request']['f1'];result['posttrain_probe_passed']=result['probe_gain']>=.03
    (folder/(name+'-training.json')).write_text(json.dumps(result,indent=2))
    with (folder/(name+'-validation-predictions.jsonl')).open('x',encoding='utf-8') as f:
        for row,p in zip(val,ps):f.write(json.dumps({'id':row['id'],'probabilities':list(map(float,p))})+'\n')
    print(json.dumps({'base':name,'best_epoch':best_epoch,'stop_reason':stop,'validation':validation,'probe_gain':result['probe_gain']}),flush=True);budget()


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('base',choices=['english','multilingual','modernbert']);p.add_argument('--round',type=int,default=1);p.add_argument('--smoke',action='store_true');a=p.parse_args();main(a.base,a.round,a.smoke)
