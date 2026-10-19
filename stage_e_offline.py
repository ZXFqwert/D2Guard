"""Frozen source inference and three-arm replay; no source text in exports."""
import hashlib,json,sqlite3,time
from pathlib import Path
from contextlib import closing
from evaluate_stage_d import reclassify
from d2v2.compression import clauses
from d2v2.request_taint import context_request_taint
from d2v2.request_model import RequestContentModel

ROOT=Path(__file__).resolve().parent
OUT=ROOT/'.local/stage-e'
def save(name,value):
    (OUT/name).write_text(json.dumps(value,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')

def main():
    root=ROOT/'.local/stage-d4/offline-root'
    config=json.loads((ROOT/'.local/stage-d5/s1-enabled-config.json').read_text())
    config['decision_mode']='taint_gate';save('s1-config.json',config)
    save('rules-config.json',{'schema':'e-rules-v1','decision_mode':'rules_gate'})
    model=RequestContentModel(OUT/'s1-config.json')
    cache_path=OUT/'source-predictions.json'
    predictions=json.loads(cache_path.read_text()) if cache_path.exists() else {}
    byrun={};stages={};flips=[];changed=set();unique=0
    for stage in ('c','c2'):
        rows=json.loads((root/f'docs/stage-{stage}-gold/system-vs-gold.json').read_text())
        for rid in sorted({r['item_id'].split(':',1)[0] for r in rows}):
            if rid in byrun:continue
            folder=root/'runs'/rid;byrun[rid]={}
            with closing(sqlite3.connect(folder/'state.sqlite3')) as db:
                records=db.execute('SELECT s.id,s.type,s.sha,e.raw FROM sources s JOIN source_events se ON se.source_id=s.id JOIN events e ON e.id=se.event_id').fetchall()
            for sid,kind,sha,raw in records:
                key=hashlib.sha256((kind+'\0'+raw).encode()).hexdigest()
                if key not in predictions:
                    try:predictions[key]=model.classify(raw,kind)
                    except Exception as e:predictions[key]={'error_type':type(e).__name__}
                    unique+=1
                    if unique%20==0:save('source-predictions.json',predictions);print(json.dumps({'sources':unique}),flush=True)
                directives,unknowns=clauses(raw,{'event_id':'offline','char_span':[0,len(raw)]})
                a={'directives':directives,'structural_gap':len(raw)>65536 or any(d.get('extraction_overflow') for d in directives),'s1':predictions[key]}
                byrun[rid][sid]=(sid,a,sha)
        results={}
        for arm,mode in [('A',None),('B','rules_gate'),('C','taint_gate')]:
            def transform(rid,ctx,facts):
                sources=[byrun[rid].get(sid,(sid,None,None)) for sid in ctx['integrity']]
                facts.update(decision_mode=mode,request_tainted=context_request_taint(sources,mode)[0])
            results[arm]=reclassify(root,stage,fact_transform=transform if mode else None)
        stages[stage]={arm:{**v['after'],'normal_ask':sum(r['gold']=='ALLOW' and r['after']=='ASK' for r in v['actions'])} for arm,v in results.items()}
        for a,c in zip(results['A']['actions'],results['C']['actions']):
            if a['after']!=c['after']:
                rid=a['item_id'].split(':',1)[0];manifest=json.loads((root/'runs'/rid/'manifest.json').read_text())
                scenario=manifest.get('scenario');scenario=scenario['id'] if isinstance(scenario,dict) else scenario
                changed.add(scenario)
                if a['after']!='ALLOW' and c['after']=='ALLOW':
                    flips.append({'scenario':scenario,'before_rule':a['after_rule_id'],'after_rule':c['after_rule_id'],'gold':c['gold']})
    save('source-predictions.json',predictions)
    result={'stages':stages,'relaxations':flips,'flipped_scenarios':sorted(changed),'gold_attack_relaxations':sum(f['gold']!='ALLOW' for f in flips),'model_sha256':config['models']['multilingual']['sha256'],'temperature':config['models']['multilingual']['temperature'],'threshold':config['threshold'],'unique_sources':len(predictions),'inference_failures':sum(bool(v.get('error_type')) for v in predictions.values())}
    save('offline.json',result);print(json.dumps(result),flush=True)

if __name__=='__main__':main()
