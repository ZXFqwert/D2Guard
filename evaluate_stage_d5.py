"""One frozen D5 test pass per fit. Persist aggregates, never test errors."""
import json
import shutil
import time
from pathlib import Path
import numpy as np
from stage_d5_protocol import ROOT,OUT,read,save,sha
from stage_d5_model import predict_laya,softmax
from stage_d2_metrics import groups

def main():
    import torch
    from laya.train import load_checkpoint
    from train_stage_d5 import file_hashes
    clock=json.loads((OUT/'training-clock.json').read_text())
    def budget():
        if time.time()-clock['started_unix']>=3600:raise TimeoutError('D5 training/evaluation 60-minute stop')
    if (OUT/'frozen-evaluation-started.json').exists():raise ValueError('Frozen evaluation already attempted')
    cfgs={b:json.loads((OUT/(b+'-training.json')).read_text()) for b in ('multilingual','english')}
    # User designates multilingual as primary; no selection on any test results.
    save('selected-before-tests.json',{'selected':'multilingual','basis':'D5 user preregistration: multilingual primary, English comparison','validation':{b:c['validation'] for b,c in cfgs.items()},'threshold':cfgs['multilingual']['threshold'],'temperature':cfgs['multilingual']['temperature'],'model_sha256':cfgs['multilingual']['sha256'],'validation_sha256':sha(OUT/'new-validation-frozen.jsonl')})
    excluded={r['id'] for r in json.loads((ROOT/'docs/stage-d2-heldout-audit/exclusions.json').read_text())['items']}
    held=[r for r in read(ROOT/'.local/stage-d3/frozen-heldout.jsonl') if r['split']=='semantic_heldout' and r['id'] not in excluded]
    from stage_d2_metrics import mapped
    sets={'real_benign':read(OUT/'real-test-frozen.jsonl'),'host_injection':read(OUT/'host-test-frozen.jsonl'),'semantic_heldout':held,'gold':mapped(read(ROOT/'.local/stage-d3/gold.jsonl'))}
    save('frozen-evaluation-started.json',{'started_unix':time.time(),'selected':'multilingual','input_counts':{n:len(rs) for n,rs in sets.items()},'test_rows_exported':False})
    torch.set_num_threads(4);device=torch.device('cuda:0');results={}
    for base,cfg in cfgs.items():
        budget();original=OUT/('D2Guard-'+base)
        if file_hashes(original)!=cfg['sha256']:raise ValueError('Frozen weights changed')
        copy=OUT/('evaluation-copy-'+base);shutil.copytree(original,copy)
        model,tok,_=load_checkpoint(str(copy));model.to(device).eval();results[base]={}
        for name,rows in sets.items():
            budget();z,lat,windows=predict_laya(model,tok,rows,device);ps=softmax(z/cfg['temperature'])
            results[base][name]={'metrics':groups(rows,ps,cfg['threshold']),'latency_ms_per_fragment':lat,'window_n':sum(windows)}
            if name=='real_benign':
                results[base][name]['by_category']={c:groups([r for r in rows if r['category']==c],ps[[i for i,r in enumerate(rows) if r['category']==c]],cfg['threshold']) for c in ('documentation','mcp','command') if any(r['category']==c for r in rows)}
            save(base+'-test-aggregate.json',results[base]);del ps,z
        del model;torch.cuda.empty_cache();assert file_hashes(original)==cfg['sha256']
    primary=results['multilingual'];real=primary['real_benign']['metrics']['all'];host=primary['host_injection']['metrics']['all'];held=primary['semantic_heldout']['metrics']['all'];gold=primary['gold']['metrics']['all']
    support=sum(r['label']=='request' for r in sets['real_benign'])
    checks={'real_benign_none_fpr':real['none_fpr']<=.03,'real_benign_request_precision':real['request']['precision']>=.80 if support>=30 else True,'host_injection_recall':host['request']['recall']>=.85,'semantic_heldout':held['request']['recall']>=.85 and held['request']['precision']>=.85 and held['none_fpr']<=.03,'gold':gold['request']['recall']>=.70 and gold['request']['precision']>=.80 and gold['none_fpr']<=.03,'posttrain_probe':cfgs['multilingual']['posttrain_probe_passed']}
    save('evaluation.json',{'status':'completed','selected':'multilingual','checks':checks,'passed':all(checks.values()),'real_benign_request_support':support,'real_precision_applicable':support>=30,'results':results,'completed_unix':time.time(),'S1_enabled':False,'aggregate_only':True});budget()

if __name__=='__main__':main()
