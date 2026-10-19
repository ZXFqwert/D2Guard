"""Real Pi paired evaluation, two repeats; no scripted model actions or recovery."""
import argparse
import concurrent.futures
import json
import secrets
import shutil
import signal
import threading
import time
from pathlib import Path
from types import SimpleNamespace
import lab
from verify_v2 import verify


def infrastructure_failure(result,gateway,audit):
    child_cancelled=any(e.get('type')=='tool_outcome' and e.get('is_error') and
                        'Subagent failed or timed out' in e.get('text','') for e in audit)
    for e in gateway:
        if e.get('type')!='proxy_error':continue
        bounded_cancel=(e.get('stage')=='write_downstream' and e.get('status')==200 and
                        (result.get('timed_out') or child_cancelled))
        if not bounded_cancel:return True
    return False


def run_scenario(sid, suite, repeats, stop, condition_workers=1):
    scenario=lab.load(lab.ROOT/'scenarios'/(sid+'.json'))
    batch_id=suite+'-'+sid
    batch={'batch_id':batch_id,'scenario':sid,'repeat_count':repeats,'results':[],
           'setup_runs':[],'verification':[],'pairing':[],'status':'running',
           'condition_workers':1 if scenario.get('setup_task') else condition_workers}
    batch_lock=threading.RLock()
    path=lab.ROOT/'runs'/(batch_id+'.json')
    lab.save(path,batch)
    def execute(environment,protect,repeat,task=None,memory=None,phase='evaluation'):
        args=SimpleNamespace(scenario=sid,environment=environment,protect=protect,engine='d2v2',
                             timeout=1800,model_request_limit=20,tool_call_limit=40,task=task,memory_root=str(memory) if memory else None,phase=phase)
        result=lab.run(args,canary,batch_id)
        bucket='setup_runs' if phase=='setup' else 'results'
        with batch_lock:
            batch[bucket].append({**result,'repeat':repeat,'environment':environment,'protection':protect,'phase':phase})
            lab.save(path,batch)
        check=verify(lab.ROOT/'runs'/result['run_id'])
        with batch_lock:
            batch['verification'].append(check);lab.save(path,batch)
        # Model refusals, bounded timeouts and tool-budget failures are evaluation
        # outcomes. Transport/configuration failures are infrastructure blockers.
        gateway=lab.jsonl(lab.ROOT/'runs'/result['run_id']/'gateway.jsonl')
        audit=lab.jsonl(lab.ROOT/'runs'/result['run_id']/'audit.jsonl')
        if infrastructure_failure(result,gateway,audit):
            stop.set();raise RuntimeError('Upstream transport failed; retained '+result['run_id'])
        return result
    try:
        for repeat in range(repeats):
            if stop.is_set():break
            canary='d2-test-'+secrets.token_hex(16)
            group=[]
            parallel=condition_workers>1 and not scenario.get('setup_task')
            if parallel:
                with concurrent.futures.ThreadPoolExecutor(max_workers=condition_workers) as conditions:
                    futures=[conditions.submit(execute,environment,protect,repeat)
                             for environment in ('clean','attack') for protect in ('off','on')]
                    for future in futures:
                        r=future.result();group.append(lab.load(lab.ROOT/'runs'/r['run_id']/'manifest.json'))
            for environment in (() if parallel else ('clean','attack')):
                seed=None
                if scenario.get('setup_task'):
                    seed=lab.ROOT/'.local'/batch_id/str(repeat)/environment/'seed'
                    execute(environment,'off',repeat,scenario['setup_task'],seed,'setup')
                    if not (seed/'handoff.json').exists():
                        batch['memory_setup_missing']=True
                for protect in ('off','on'):
                    if stop.is_set():break
                    memory=None
                    if seed:
                        memory=seed.parent/protect
                        shutil.copytree(seed,memory)
                    r=execute(environment,protect,repeat,memory=memory)
                    group.append(lab.load(lab.ROOT/'runs'/r['run_id']/'manifest.json'))
                if stop.is_set():break
            fields=['task_sha256','scenario_sha256','source_sha256','model','pi_cli_sha256','fast_model','conversation_sha256']
            pairing={'repeat':repeat,'four_conditions':len(group)==4,
                     **{'same_'+k:len(group)==4 and all(m[k]==group[0][k] for m in group) for k in fields}}
            for env in ('clean','attack'):
                pair=[m for m in group if m['environment']==env]
                pairing[env+'_identical_inputs']=len(pair)==2 and all(pair[0][k]==pair[1][k] for k in
                    ['initial_files','memory_initial_sha256','fixture_sha256','user_input_sha256'])
            batch['pairing'].append(pairing);lab.save(path,batch)
        batch['status']='complete' if len(batch['results'])==repeats*4 else 'interrupted'
    except Exception as exc:
        stop.set();batch['status']='blocked';batch['error_type']=type(exc).__name__
        # Error strings may contain private endpoints; keep public record typed.
    lab.save(path,batch)
    return {'scenario':sid,'batch_id':batch_id,'status':batch['status'],
            'runs':[r['run_id'] for r in batch['results']], 'setup_runs':[r['run_id'] for r in batch['setup_runs']]}


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--scenarios',nargs='*');p.add_argument('--repeats',type=int,default=2)
    p.add_argument('--workers',type=int,default=4)
    p.add_argument('--condition-workers',type=int,choices=range(1,5),default=1,
                   help='Parallel independent conditions within a repeat; memory setup scenarios remain serial')
    p.add_argument('--suite-prefix',default='stage-c')
    p.add_argument('--continue-suite',type=Path,help='Reuse only full paired batches; partial batches remain as separate evidence')
    a=p.parse_args()
    ids=a.scenarios or [p.stem for p in sorted((lab.ROOT/'scenarios').glob('c*.json'))]
    suite=a.suite_prefix+'-'+time.strftime('%Y%m%d-%H%M%S')
    stop=threading.Event();report={'suite':suite,'evaluation_only':True,'batches':[]}
    if a.continue_suite:
        previous=lab.load(a.continue_suite)
        for item in previous['batches']:
            batch=lab.load(a.continue_suite.parent/(item['batch_id']+'.json'))
            complete=(len(batch['results'])==a.repeats*4 and len(batch['pairing'])==a.repeats and
                      all(all(v for k,v in pair.items() if k!='repeat') for pair in batch['pairing']))
            if complete and item['scenario'] in ids:
                report['batches'].append(item);ids.remove(item['scenario'])
        report['continued_from']=previous['suite']
        report['reused_complete_batches']=[x['batch_id'] for x in report['batches']]
    signal.signal(signal.SIGTERM,lambda *_:stop.set())
    print('SUITE '+suite,flush=True)
    with concurrent.futures.ThreadPoolExecutor(max_workers=a.workers) as pool:
        futures={pool.submit(run_scenario,sid,suite,a.repeats,stop,a.condition_workers):sid for sid in ids}
        for future in concurrent.futures.as_completed(futures):
            report['batches'].append(future.result());lab.save(lab.ROOT/'runs'/(suite+'.json'),report)
            print('SCENARIO '+json.dumps(report['batches'][-1]),flush=True)
    if stop.is_set():raise SystemExit(2)


if __name__=='__main__':main()
