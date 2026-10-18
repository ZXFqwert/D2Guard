"""S1/S2 domain checkpoint. A1/A2 retain their independent original backend."""
import hashlib
import json
import time
import shutil
from pathlib import Path
import numpy as np
from .content_schema import LABELS,S1,QUESTIONS,S2_TYPES
from .normalization import normalize


def windows(tok,text,source_type):
    """All content is covered by <=256-token views; no silent tail truncation."""
    encoded=tok(text,add_special_tokens=False,return_offsets_mapping=True)
    offsets=encoded['offset_mapping']
    if not offsets:return [{'source_type':source_type,'fragment':text}]
    result=[]
    # Reserve room for JSON keys/source type; validate the actual serialized view.
    start=0
    while start<len(offsets):
        end=min(start+220,len(offsets))
        while True:
            part=text[offsets[start][0]:offsets[end-1][1]]
            v={'source_type':source_type,'fragment':part}
            if len(tok(json.dumps(v,ensure_ascii=False),add_special_tokens=False)['input_ids'])<=256:break
            end-=1
            if end<=start:raise ValueError('Source type alone exceeds S1 view budget')
        result.append(v)
        if end==len(offsets):break
        start=max(start+1,end-32)
    return result


def model_items(tok,text,source_type,max_len=512,question_id='S1',question=None):
    from laya.train import items_from_rows
    from laya.common import build_sequence
    vs=windows(tok,normalize(text)[0],source_type)
    items,skipped=items_from_rows(tok,[{'state':v,'questions':{question_id:question or QUESTIONS[question_id]},'expected':{question_id:'A'}} for v in vs],max_len,192)
    if skipped or len(items)!=len(vs):raise ValueError('S1 items skipped: '+str(skipped))
    for it in items:
        stats=build_sequence(tok,{},it['q'],max_len,192,state_ids=it['state_ids'],return_truncation_stats=True)[-1]
        if stats['truncated']:raise ValueError('S1 sequence truncated')
    return items


def probabilities(model,tok,text,source_type,device,temperature=1.0,max_len=512,question_id='S1',question=None):
    from laya.train import calibration_records
    items=model_items(tok,text,source_type,max_len,question_id,question)
    records=calibration_records(model,tok,items,device,max_len,192,batch_size=8)
    ps=[]
    for _,z,_,k in records:
        z=np.asarray(z,dtype=float);z-=z.max();p=np.exp(z);ps.append(p/p.sum())
    # Fixed before any evaluation: arithmetic mean over every overlapping window.
    z=np.log(np.maximum(np.mean(ps,axis=0),1e-12))/temperature
    p=np.exp(z-z.max());return p/p.sum(),len(items)


class ContentModel:
    def __init__(self,config_path):
        import torch
        from laya.train import load_checkpoint
        cfg=json.loads(Path(config_path).read_text(encoding='utf8'))
        folder=Path(cfg['path']);self.metadata=cfg
        for name,expected in cfg['sha256'].items():
            if hashlib.file_digest((folder/name).open('rb'),'sha256').hexdigest()!=expected:raise ValueError('D2Guard-Laya hash mismatch')
        # Laya load_checkpoint repairs tokenizer configuration in-place. Keep the
        # published checkpoint immutable, including during repeated real runs.
        work=Path(config_path).resolve().parent/('serve-work-'+cfg['sha256']['model.safetensors'][:16])
        if not work.exists():shutil.copytree(folder,work)
        for name,expected in cfg['sha256'].items():
            if name.endswith('.safetensors') and hashlib.file_digest((work/name).open('rb'),'sha256').hexdigest()!=expected:
                raise ValueError('D2Guard-Laya serving copy weight mismatch')
        self.model,self.tok,self.cfg=load_checkpoint(str(work))
        self.device=torch.device(cfg.get('device','cuda:0'))
        self.model.to(self.device).eval()
        self.calibration=self.cfg['d2guard_calibration']['S1:4']

    def classify(self,text,source_type):
        import torch
        start=time.perf_counter()
        with torch.no_grad():
            p,n=probabilities(self.model,self.tok,text,source_type,self.device,self.calibration['temperature'],question=self.cfg.get('d2guard_s1_question'))
            tactics={}
            for key in S2_TYPES:
                calibration=self.cfg['d2guard_calibration'].get('S2:'+key+':2')
                if calibration is None:continue
                sp,_=probabilities(self.model,self.tok,text,source_type,self.device,calibration['temperature'],question_id=key)
                tactics[key]={'present':bool(sp.argmax()==0),'probability':float(sp[0]),
                             'threshold_passed':bool(sp.max()>=calibration['threshold']),'calibrated':True}
        binary=self.calibration.get('threshold_kind')=='to_agent_probability'
        i=(0 if p[0]>=self.calibration['threshold'] else 1+int(p[1:].argmax())) if binary else int(p.argmax())
        confidence=float(p[i])
        return {'label':LABELS[i],'probabilities':dict(zip(LABELS,map(float,p))),
                'calibrated':True,'threshold_passed':bool(p[0]>=self.calibration['threshold']) if binary else confidence>=self.calibration['threshold'],
                'windows':n,'latency_ms':(time.perf_counter()-start)*1000,
                's2':tactics,
                'model':'D²Guard-Laya','checkpoint_sha256':self.metadata['sha256']['model.safetensors']}
