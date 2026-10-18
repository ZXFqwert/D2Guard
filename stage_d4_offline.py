"""Offline-only recovery; never reruns completed benign/heldout/gold metrics."""
import json
import sqlite3
import tarfile
import time
from collections import defaultdict
from contextlib import closing
from stage_d4_protocol import OUT,D3,ROOT,read,sha,save,budget

def main():
    import torch
    from laya.train import load_checkpoint
    from train_stage_d3 import file_hashes
    from stage_d3_model import predict_laya,softmax
    from d2v2.compression import clauses
    from evaluate_stage_d import reclassify
    budget(reserve=180)
    marker=OUT/'offline-recovery-started.json'
    if marker.exists():
        if (OUT/'offline-inference-started.json').exists():raise ValueError('Offline inference already attempted')
    else:
        with marker.open('x') as f:json.dump({'started_unix':time.time(),'frozen_metric_hashes':{n:sha(OUT/(n+'-aggregate.json')) for n in ('benign','heldout','gold')}},f)
    restored=OUT/'offline-root';restored.mkdir(exist_ok=True)
    with tarfile.open(OUT/'offline-evidence.tar.gz') as tar:tar.extractall(restored,filter='data')
    if not (restored/'docs').exists():(restored/'docs').symlink_to(ROOT/'docs',target_is_directory=True)
    cfg=json.loads((OUT/'threshold.json').read_text());assert file_hashes(D3/'D2Guard-multilingual')==cfg['model_sha256']
    sources=[];unique={}
    for folder in sorted((restored/'runs').iterdir()):
        with closing(sqlite3.connect((folder/'state.sqlite3').resolve().as_uri()+'?mode=ro',uri=True)) as db:
            for sid,kind,raw in db.execute('SELECT DISTINCT s.id,s.type,e.raw FROM sources s JOIN source_events se ON se.source_id=s.id JOIN events e ON e.id=se.event_id'):
                if kind=='HOST_TOOL_ERROR':continue
                key=(kind,raw);sources.append((folder.name,sid,key));unique.setdefault(key,{'source_type':kind,'raw_text':raw,'label':'none'})
    off_results={stage:reclassify(restored,stage) for stage in ('c','c2')}
    save('offline-inference-started.json',{'started_unix':time.time(),'unique_sources':len(unique),'offline_baseline_completed':True})
    torch.set_num_threads(4);device=torch.device('cuda:0');model,tok,_=load_checkpoint(str(OUT/'evaluation-model-copy'));model.to(device).eval()
    z,lat,windows=predict_laya(model,tok,list(unique.values()),device);ps=softmax(z/cfg['temperature']);cache=dict(zip(unique,ps));s1=defaultdict(set)
    for rid,sid,key in sources:
        if cache[key][0]<cfg['threshold']:continue
        raw=key[1];ds,incomplete=clauses(raw,{'event_id':'offline','char_span':[0,len(raw)]})
        if incomplete or not any(r['stance']=='requested' for d in ds for r in d['action_relations']):s1[rid].add(sid)
    offline={}
    for stage in ('c','c2'):
        off=off_results[stage];on=reclassify(restored,stage,s1_sources=s1)
        pairs=list(zip(off['actions'],on['actions']))
        offline[stage]={'s1_off':off['after'],'s1_on':on['after'],'recall_not_decreased':on['after']['interception_recall']>=off['after']['interception_recall'],
                       'new_ask_n':sum(a['after']!='ASK' and b['after']=='ASK' for a,b in pairs),'new_block_n':sum(a['after']!='BLOCK' and b['after']=='BLOCK' for a,b in pairs)}
    passed=all(v['recall_not_decreased'] for v in offline.values())
    save('offline-aggregate.json',{'stages':offline,'passed':passed,'scope':'Offline-only full-source inference after restoring missing historical evidence into an isolated local root; completed benchmark metrics were not rerun','source_count':len(sources),'unique_full_source_inputs':len(unique),'s1_eligible_sources':sum(map(len,s1.values())),'latency_ms_per_source':lat})
    prior=json.loads(marker.read_text())
    assert all(sha(OUT/(n+'-aggregate.json'))==h for n,h in prior['frozen_metric_hashes'].items())
    assert file_hashes(D3/'D2Guard-multilingual')==cfg['model_sha256']
    flags={k:json.loads((OUT/(k+'-aggregate.json')).read_text())['passed'] for k in ('benign','heldout','gold')}
    result={'status':'completed','selected':'multilingual','threshold':cfg['threshold'],'temperature':cfg['temperature'],**{k+'_passed':v for k,v in flags.items()},'offline_passed':passed,'model_unchanged':True,'aggregate_only':True,'regression_eligible':all(flags.values()) and passed,'enable_s1':False,'completed_unix':time.time(),'offline_recovery_without_metric_rerun':True}
    save('evaluation.json',result);print(json.dumps(result),flush=True)

if __name__=='__main__':main()
