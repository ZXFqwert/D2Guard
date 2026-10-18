"""Predeclared sixteen-cell real Pi regression, conditional on frozen acceptance."""
import argparse
import json
import os
import secrets
import time
from stage_d3_protocol import ROOT,OUT,sha,plan


def main():
    from d2v2.request_model import accepted
    from lab import run,save
    from verify_v2 import verify
    evaluation=json.loads((OUT/'final-evaluation.json').read_text())
    if evaluation.get('enable_s1') is not True:raise ValueError('Frozen acceptance did not pass')
    selection=json.loads((OUT/'selected-before-heldout.json').read_text())
    config={'schema':'d3-request-v1','decision_mode':'add_risk','selected':selection['selected'],
            'threshold':evaluation['threshold'],'device':'cuda:0','models':{}}
    for key,name in [('evaluation','final-evaluation.json'),('selection','selected-before-heldout.json'),
                     ('admission','admission.json'),('probe','probe.json')]:
        config[key]={'path':str(OUT/name),'sha256':sha(OUT/name)}
    for name in ('english','multilingual','modernbert'):
        record=json.loads((OUT/(name+'-training.json')).read_text())
        config['models'][name]={'path':str(OUT/('D2Guard-'+name)),'sha256':record['sha256'],'temperature':record['temperature']}
    accepted(config)
    marker=OUT/'regression-started.json'
    if marker.exists():raise ValueError('Real regression already attempted; never repeat automatically')
    cells=[]
    for scenario in ('readme-setup-registration','c2-language-ja','c2-variant-comment'):
        cells.extend((scenario,environment,protect) for environment in ('clean','attack') for protect in ('off','on'))
    for scenario in ('c2-normal-quoted','c2-normal-mcp'):
        cells.extend((scenario,'clean',protect) for protect in ('off','on'))
    started=time.time();stage=plan();deadline=min(started+5400,stage['started_unix']+stage['stage_budget_seconds'])
    with marker.open('x',encoding='utf-8') as f:json.dump({'started_unix':started,'cells':cells,'deadline_unix':deadline},f,indent=2)
    path=OUT/'s1-enabled-config.json'
    with path.open('x',encoding='utf-8') as f:json.dump(config,f,indent=2)
    os.environ['D2_S1_CONFIG']=str(path)
    batch='stage-d3-regression-'+time.strftime('%Y%m%d-%H%M%S')
    results=[];checks=[];canaries={s:'D2-CANARY-'+secrets.token_hex(16) for s,_,_ in cells}
    status={'batch_id':batch,'status':'running','results':checks,'planned_n':16,'s1_enabled_for_batch':True}
    try:
        for scenario,environment,protect in cells:
            if time.time()+240>deadline:raise TimeoutError('No budget for a complete 180-second real cell plus evidence finalization')
            args=argparse.Namespace(scenario=scenario,timeout=180,engine='d2v2',memory_root=None,task=None,
                                    environment=environment,protect=protect,phase='stage-d3-regression')
            result=run(args,canaries[scenario],batch);results.append(result)
            save(ROOT/'runs'/(batch+'.json'),{'repeat_count':1,'results':results})
            check=verify(ROOT/'runs'/result['run_id']);checks.append(check)
            status.update(seconds=time.time()-started,run_ids=[x['run_id'] for x in results],all_passed=all(x['all_passed'] for x in checks))
            save(OUT/'regression.json',status)
            print(json.dumps({'run_id':result['run_id'],'verify_v2':check['all_passed']}),flush=True)
            if not check['evidence_checks_passed']:raise RuntimeError('Evidence validation failed; stop remaining real cells')
        status['status']='completed'
    except Exception as error:
        status.update(status='stopped',error_type=type(error).__name__,error=str(error));raise
    finally:
        status.update(seconds=time.time()-started,completed_n=len(checks),run_ids=[x['run_id'] for x in results])
        save(OUT/'regression.json',status)


if __name__=='__main__':main()
