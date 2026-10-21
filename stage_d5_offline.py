"""D5 offline trajectory recomputation after all model gates; aggregate only."""
import json
import sqlite3
import tarfile
import time
from collections import defaultdict
from contextlib import closing
from stage_d5_protocol import OUT,ROOT,read,sha,save,budget as stage_budget

def budget(reserve=60):return stage_budget(reserve,phase="stage")

def main():
    import torch
    from laya.train import load_checkpoint
    from train_stage_d5 import file_hashes
    from stage_d5_model import predict_laya,softmax
    from d2v2.compression import clauses
    from evaluate_stage_d import reclassify
    budget(reserve=180)
    evaluation=json.loads((OUT/'evaluation.json').read_text())
    if not evaluation.get('passed'):raise ValueError('D5 model acceptance has not passed')
    marker=OUT/'offline-inference-started.json'
    if marker.exists():raise ValueError('D5 offline inference already attempted')
    restored=ROOT/'.local/stage-d4/offline-root'
    if not (restored/'runs').exists():raise ValueError('Prior read-only trajectory snapshots missing')
    cfg=json.loads((OUT/'multilingual-training.json').read_text())
    assert file_hashes(OUT/'D2Guard-multilingual')==cfg['sha256']
    frozen_metrics=sha(OUT/'evaluation.json')
    sources=[];unique={}
    for folder in sorted((restored/'runs').iterdir()):
        with closing(sqlite3.connect((folder/'state.sqlite3').resolve().as_uri()+'?mode=ro',uri=True)) as db:
            for sid,kind,raw in db.execute('SELECT DISTINCT s.id,s.type,e.raw FROM sources s JOIN source_events se ON se.source_id=s.id JOIN events e ON e.id=se.event_id'):
                if kind=='HOST_TOOL_ERROR':continue
                key=(kind,raw);sources.append((folder.name,sid,key));unique.setdefault(key,{'source_type':kind,'raw_text':raw,'label':'none'})
    off_results={stage:reclassify(restored,stage) for stage in ('c','c2')}
    save('offline-inference-started.json',{'started_unix':time.time(),'unique_sources':len(unique),'offline_baseline_completed':True})
    torch.set_num_threads(4);device=torch.device('cuda:0');model,tok,_=load_checkpoint(str(OUT/'evaluation-copy-multilingual'));model.to(device).eval()
    budget(reserve=100)
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
    save('offline-aggregate.json',{'stages':offline,'passed':passed,'scope':'D5 full-source inference on preexisting read-only C/C2 trajectory snapshots; completed benchmark metrics not rerun','source_count':len(sources),'unique_full_source_inputs':len(unique),'s1_eligible_sources':sum(map(len,s1.values())),'latency_ms_per_source':lat})
    assert sha(OUT/'evaluation.json')==frozen_metrics
    assert file_hashes(OUT/'D2Guard-multilingual')==cfg['sha256']
    print(json.dumps({'offline_passed':passed,'stages':offline}),flush=True)

if __name__=='__main__':main()
