"""Stage D3 request classifier, enabled only by frozen acceptance evidence."""
import hashlib
import json
import shutil
import time
from pathlib import Path


def read_proof(config, name):
    reference=config[name];path=Path(reference['path'])
    if hashlib.sha256(path.read_bytes()).hexdigest()!=reference['sha256']:
        raise ValueError('S1 acceptance evidence changed')
    return json.loads(path.read_text(encoding='utf-8'))


def accepted(config):
    if config.get('schema')!='d3-request-v1' or config.get('decision_mode')!='add_risk':
        raise ValueError('S1 risk addition is not explicitly enabled')
    result=read_proof(config,'evaluation');selection=read_proof(config,'selection')
    admission=read_proof(config,'admission');probe=read_proof(config,'probe')
    if not admission.get('passed') or not probe.get('pretrain_passed'):
        raise ValueError('S1 data gates failed')
    name=config['selected'];candidate=selection['candidates'][name]
    if (result.get('status')!='completed' or result.get('enable_s1') is not True
        or name!=selection['selected'] or name!=result['selected']
        or config['threshold']!=result['threshold'] or config['threshold']!=candidate['threshold']
        or not candidate['posttrain_probe_passed']):
        raise ValueError('S1 frozen selection or acceptance failed')
    for subset in ('adjusted_semantic','adjusted_combined'):
        m=result['heldout']['metrics'][subset]['all']
        if not (m['request']['recall']>=.85 and m['request']['precision']>=.85
                and m['none_fpr']<=.03 and m['ece_request_10_bins']<=.10):
            raise ValueError('S1 heldout gate failed')
    m=result['gold']['metrics']['all']
    if not (m['request']['recall']>=.70 and m['request']['precision']>=.80 and m['none_fpr']<=.03):
        raise ValueError('S1 gold regression gate failed')
    return selection


class RequestContentModel:
    def __init__(self,config_path):
        import torch
        config_path=Path(config_path)
        self.metadata=json.loads(config_path.read_text(encoding='utf-8'))
        selection=accepted(self.metadata)
        self.selected=self.metadata['selected'];self.threshold=self.metadata['threshold']
        self.device=torch.device(self.metadata.get('device','cuda:0'));self.loaded={}
        needed=('english','multilingual','modernbert') if self.selected=='ensemble' else (self.selected,)
        for name in needed:
            cfg=self.metadata['models'][name];folder=Path(cfg['path'])
            if cfg['sha256']!=selection['candidates'][name]['sha256']:
                raise ValueError('S1 checkpoint differs from frozen selection')
            if cfg['temperature']!=selection['candidates'][name]['temperature']:
                raise ValueError('S1 calibration differs from frozen validation')
            for relative,expected in cfg['sha256'].items():
                if hashlib.sha256((folder/relative).read_bytes()).hexdigest()!=expected:
                    raise ValueError('S1 checkpoint hash mismatch')
            if name=='modernbert':
                from transformers import AutoTokenizer,AutoModelForSequenceClassification
                tok=AutoTokenizer.from_pretrained(folder,local_files_only=True)
                model=AutoModelForSequenceClassification.from_pretrained(folder,local_files_only=True)
            else:
                from laya.train import load_checkpoint
                work=config_path.parent/('serve-d3-'+name+'-'+cfg['sha256']['model.safetensors'][:16])
                if not work.exists():shutil.copytree(folder,work)
                for relative,expected in cfg['sha256'].items():
                    if relative.endswith('.safetensors') and hashlib.sha256((work/relative).read_bytes()).hexdigest()!=expected:
                        raise ValueError('S1 serving copy weight mismatch')
                model,tok,_=load_checkpoint(str(work))
            self.loaded[name]=(model.to(self.device).eval(),tok,cfg['temperature'])
        self.add_risk_enabled=True

    def classify(self,text,source_type):
        from stage_d3_model import predict_laya,predict_baseline,softmax,route_base
        start=time.perf_counter();row={'raw_text':text,'source_type':source_type,'label':'none'}
        # The placeholder label only satisfies Laya item construction; it is not
        # fed into the model sequence or used to select probabilities.
        names=(route_base(text),'modernbert') if self.selected=='ensemble' else (self.selected,)
        probabilities=[];windows=0
        for name in names:
            model,tok,temperature=self.loaded[name]
            predictor=predict_baseline if name=='modernbert' else predict_laya
            z,_,counts=predictor(model,tok,[row],self.device)
            probabilities.append(softmax(z/temperature)[0]);windows+=sum(counts)
        p=sum(probabilities)/len(probabilities);labels=('request','quoted','none')
        index=0 if p[0]>=self.threshold else 1+int(p[1:].argmax())
        return {'label':labels[index],'probabilities':dict(zip(labels,map(float,p))),
                'calibrated':True,'threshold_passed':bool(p[0]>=self.threshold),'windows':windows,
                'latency_ms':(time.perf_counter()-start)*1000,'model':'D3-'+self.selected,
                'checkpoint_sha256':{name:self.metadata['models'][name]['sha256'] for name in names},'s2':{}}
