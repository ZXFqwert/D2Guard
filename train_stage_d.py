"""One authorized Stage D training run, immutable bases, explicit validation."""
import argparse
import dataclasses
import hashlib
import json
import shutil
import signal
import sys
import time
from pathlib import Path
from stage_d_data import ROOT,read_jsonl,typed,LABELS,S2,LANGS
sys.path.insert(0,str(ROOT/'src'))


def hashes(folder):
    return {str(p.relative_to(folder)):hashlib.file_digest(p.open('rb'),'sha256').hexdigest()
            for p in sorted(folder.rglob('*')) if p.is_file()}


def validate_admission(leak,data):
    if not leak.get('passed'):raise ValueError('Leakage gate not passed')
    identities=leak.get('teacher_actual_models',[])
    if len(set(identities))<2:raise ValueError('Two independent actual teacher identities are required')
    if leak.get('approved_input_sha256')!=hashlib.sha256(data.read_bytes()).hexdigest():
        raise ValueError('Training file is not the admitted corpus')
    if leak.get('family_provenance_reviewed') is not True:raise ValueError('Semantic template provenance review pending')
    if leak.get('annotation_review_completed') is not True or leak.get('unresolved_rows_in_admitted')!=0:
        raise ValueError('Annotation disputes in the admitted corpus require human review')


def validate_support(rows):
    for split in ('train','validation'):
        subset=[r for r in rows if r['split']==split]
        if len(subset)<32 or {r['label'] for r in subset}!=set(LABELS):
            raise ValueError('Insufficient four-class support: '+split)
        for key in S2:
            if {r['s2'][key] for r in subset}!={True,False}:
                raise ValueError('Missing positive/negative S2 support: '+split+'/'+key)
        for label in LABELS:
            if {r.get('language') for r in subset if r['label']==label}!=set(LANGS):
                raise ValueError('Missing language/class support: '+split+'/'+label)


def main(a):
    import numpy as np
    import torch
    from laya.train import load_checkpoint,items_from_rows,TrainConfig,train_model,calibration_records,save_checkpoint,encode_item,soft_ce_loss,_forward
    from laya.calibrate import fit_one_temperature,_select_abstention_threshold
    from laya.common import collate_items,build_sequence
    from d2v2.content_model import model_items,probabilities
    started=time.monotonic();base=a.base.resolve();out=a.output.resolve()
    marker=ROOT/'.local/stage-d/training-started.json'
    if not a.smoke and marker.exists():raise ValueError('A full fit was already attempted; stop for review before retraining')
    def deadline(signum,frame):raise TimeoutError('90-minute training wall-clock stop-loss')
    if hasattr(signal,'SIGALRM'):
        signal.signal(signal.SIGALRM,deadline);signal.alarm(5400)
    if out.exists() or out==base or base in out.parents or out.is_symlink():raise ValueError('Output must be a new, independent checkpoint directory')
    if not torch.cuda.is_available():raise RuntimeError('A100 required; no CPU training fallback')
    if 'A100' not in torch.cuda.get_device_name(0):raise RuntimeError('Expected explicitly allocated A100')
    torch.set_num_threads(4);torch.manual_seed(20261017)
    original=hashes(base)
    work=ROOT/'.local/stage-d'/('base-work-'+original['model.safetensors'][:12])
    if not work.exists():shutil.copytree(base,work)
    for name,expected in original.items():
        if name.endswith('.safetensors') and hashlib.file_digest((work/name).open('rb'),'sha256').hexdigest()!=expected:
            raise ValueError('Working base does not match immutable source weights')
    model,tok,cfg=load_checkpoint(str(work));device=torch.device('cuda:0')
    rows=read_jsonl(a.data)
    leak=json.loads(a.leakage.read_text(encoding='utf8'))
    validate_admission(leak,a.data)
    validate_support(rows)
    train=[r for r in rows if r['split']=='train'];validation=[r for r in rows if r['split']=='validation']
    if not train or not validation:raise ValueError('Empty train or validation split')
    items=[];excluded=[];retained=[]
    for r in train:
        its=model_items(tok,r['text'],r['source_type'])
        # Do not train every unrelated window on the full-fragment label.
        if len(its)!=1:excluded.append(r['id']);continue
        retained.append(r)
        its[0]['target']=[float(l==r['label']) for l in LABELS];items.extend(its)
        for key in S2:
            extra=model_items(tok,r['text'],r['source_type'],question_id=key)
            if len(extra)!=1:raise ValueError('S2 window mismatch')
            extra[0]['target']=[float(r['s2'][key]),float(not r['s2'][key])];items.extend(extra)
    validate_support(retained+validation)
    # Freeze the official notebook's four-epoch schedule before any evaluation.
    config=TrainConfig(epochs=4,micro_batch=8,grad_accum=1,encoder_lr=2.5e-5,head_lr=1e-4,
                       loss='soft-ce',shuffle_options=('choice',),seed=20261017,max_len=512,head_max_len=192,
                       log_every=20,amp=True,gradient_checkpointing=True,calib_frac=0)
    model.to(device)
    if a.smoke:
        # Forward/backward contract test only: no optimizer update or saved model.
        model.train();batch=collate_items([[encode_item(tok,it,512,192) for it in items[:4]]],tok.pad_token_id)
        z=_forward(model,batch,device,True,False)
        loss=soft_ce_loss(z,batch['target'].to(device),batch['marker_mask'].to(device));loss.backward()
        finite=bool(torch.isfinite(loss)) and all(p.grad is None or torch.isfinite(p.grad).all() for p in model.parameters())
        result={'kind':'training_interface_smoke_no_optimizer_step','passed':finite,'loss':float(loss.detach()),
                'items':len(items),'validation':len(validation),'multiwindow_training_excluded':excluded,
                'original_unchanged':hashes(base)==original,'seconds':time.monotonic()-started}
        a.result.write_text(json.dumps(result,indent=2),encoding='utf8');print(json.dumps(result),flush=True)
        if not finite:raise SystemExit(2)
        return
    # Refuse a second full fit even after a failed run; user must review first.
    with marker.open('x',encoding='utf8') as f:json.dump({'started_unix':time.time(),'config':dataclasses.asdict(config),'output':str(out)},f)
    def epoch_end(epoch,loss):
        if not np.isfinite(loss):raise RuntimeError('Non-finite training loss; stop before any retraining')
        if time.monotonic()-started>5400:raise TimeoutError('90-minute training stop-loss')
    history=train_model(model,tok,items,config,device,512,192,on_epoch_end=epoch_end)
    # Obtain fragment logits using log(mean window probabilities), preserving the
    # exact fixed serving aggregation used by the validation threshold.
    calibration={}
    for question in ('S1',*S2):
        vals=[]
        for r in validation:
            p,n=probabilities(model,tok,r['text'],r['source_type'],device,question_id=question)
            target=[float(x==r['label']) for x in LABELS] if question=='S1' else [float(r['s2'][question]),float(not r['s2'][question])]
            vals.append((np.log(np.maximum(p,1e-12)),target))
        temperature=fit_one_temperature(vals,min_n=32)
        pairs=[]
        for z,y in vals:
            z=z/temperature;p=np.exp(z-z.max());p/=p.sum()
            pairs.append((float(p.max()),int(p.argmax()==np.argmax(y))))
        threshold=_select_abstention_threshold(pairs,target_error=.10,conservative=True)
        key='S1:4' if question=='S1' else 'S2:'+question+':2'
        calibration[key]={'temperature':temperature,'threshold':threshold,'target_error':.10,
                          'validation_n':len(vals),'source':'validation_only','aggregation':'mean_window_probabilities_then_temperature',
                          'validation_accuracy':sum(ok for conf,ok in pairs)/len(pairs),
                          'validation_accepted_n':sum(conf>=threshold for conf,ok in pairs),
                          'validation_accepted_errors':sum(not ok for conf,ok in pairs if conf>=threshold)}
    cfg.update(model_name='D²Guard-Laya',fine_tuned=True,max_len=512,head_max_len=192,
               d2guard_calibration=calibration,d2guard_training=dataclasses.asdict(config),
               d2guard_scope='S1 and four binary S2 questions; rules remain authoritative; A1/A2 untrained')
    save_checkpoint(model,tok,cfg,str(out))
    after=hashes(base)
    if after!=original:raise RuntimeError('Original checkpoint modified')
    result={'kind':'real_A100_training','model':'D²Guard-Laya','base':str(base),
            'original_sha256':original,'original_unchanged':True,'output':str(out),'sha256':hashes(out),
            'config':dataclasses.asdict(config),'calibration':calibration,'history':history,
            'training_items':len(items),'training_multiwindow_exclusions':excluded,'validation_n':len(vals),
            'seconds':time.monotonic()-started,'gpu':torch.cuda.get_device_name(0)}
    a.result.write_text(json.dumps(result,indent=2),encoding='utf8');print(json.dumps(result),flush=True)


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--base',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
    p.add_argument('--data',type=Path,required=True);p.add_argument('--leakage',type=Path,required=True);p.add_argument('--result',type=Path,required=True)
    p.add_argument('--smoke',action='store_true');main(p.parse_args())
