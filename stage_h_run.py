"""Stage H frozen real-Pi matrix; retained one-shot retries, no kernel mutation."""
import argparse
import concurrent.futures as futures
import hashlib
import json
import os
from pathlib import Path
import secrets
import shutil
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parent
OUT = ROOT / '.local/stage-h'

def read(p):
    return json.loads(Path(p).read_text(encoding='utf-8'))

def save(p, value):
    p = Path(p)
    p.parent.mkdir(parents=True, exist_ok=True)
    temp = p.with_suffix('.tmp')
    temp.write_text(json.dumps(value, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
    temp.replace(p)

def worker(index, attempt):
    from lab import run
    from verify_v2 import verify
    plan = read(OUT/'plan.json')
    cell = plan['cells'][index]
    scheduler_workers = read(OUT/'protocol.json')['workers']
    os.environ.pop('D2_S1_CONFIG', None)
    os.environ.pop('D2_S1_DISABLE', None)
    if cell['scenario'].startswith('g-'):
        os.environ['D2_HOST_EXEC'] = '1'
    else:
        os.environ.pop('D2_HOST_EXEC', None)
    scenario = read(ROOT/'scenarios'/(cell['scenario']+'.json'))
    memory = None
    if scenario.get('source_channel') == 'memory':
        memory = OUT/'memory-cells'/f'{index}-{attempt}'
        shutil.copytree(ROOT/'.local/stage-e/memory'/(cell['scenario']+'-'+cell['environment']), memory)
    args = argparse.Namespace(scenario=cell['scenario'], environment=cell['environment'],
        protect=cell['protect'], timeout=cell['timeout'], model_request_limit=cell.get('model_request_limit',20),
        tool_call_limit=40, engine='d2v2', memory_root=str(memory) if memory else None,
        task=None, phase='stage-h')
    result = run(args, plan['canary'], plan['batch_id'])
    record = dict(index=index, attempt=attempt, cell=cell, scheduler_workers=scheduler_workers, run_id=result['run_id'], result=result)
    save(OUT/f'cell-{index}-{attempt}.json', record)
    record['verify_v2'] = verify(ROOT/'runs'/result['run_id'])
    save(OUT/f'cell-{index}-{attempt}.json', record)

def launch(index, attempt):
    path = OUT/f'cell-{index}-{attempt}.json'
    if path.exists():
        record=read(path)
        if record.get('run_id') and 'verify_v2' not in record:
            from verify_v2 import verify
            record['verify_v2']=verify(ROOT/'runs'/record['run_id'])
            save(path,record)
        return record
    with (OUT/f'cell-{index}-{attempt}.log').open('w') as log:
        proc = subprocess.run([sys.executable, __file__, 'worker', str(index), str(attempt)],
            stdout=log, stderr=subprocess.STDOUT, timeout=1200)
    if path.exists():
        return read(path)
    record = dict(index=index, attempt=attempt, cell=read(OUT/'plan.json')['cells'][index],
                  startup_failure=True, returncode=proc.returncode)
    save(OUT/f'cell-{index}-{attempt}.json', record)
    return record

def retryable(record):
    result = record.get('result', {})
    return bool(result.get('timed_out') or result.get('model_errors') or
                result.get('runtime_diagnostics', {}).get('gateway_errors')) and not result.get('model_run_ok', False)

def evidence_failures(record):
    check=record.get('verify_v2') or {}
    failed=[k for k,v in check.get('checks',{}).items() if not v]
    # Coverage of 51 user turns is a completion condition, not a hash/trace
    # integrity condition. Retain its false value when a model timeout caused it.
    if retryable(record):
        failed=[k for k in failed if k!='stage_c2_real_conversation_covered']
    return failed

def main():
    OUT.mkdir(parents=True, exist_ok=True)
    protocol = read(OUT/'protocol.json')
    if not (OUT/'plan.json').exists():
        cells = []
        for p in sorted((ROOT/'scenarios').glob('*.json')):
            if p.stem.split('-')[0] not in ('c', 'c2', 'e', 'g'):
                continue
            s = read(p)
            for repeat in (1, 2, 3):
                for environment in ('clean', 'attack'):
                    for protect in ('off', 'on'):
                        cells.append(dict(scenario=p.stem, family=s.get('family'), category=s.get('category'),
                            repeat=repeat, environment=environment, protect=protect,
                            timeout=540 if p.stem in ('g-attack-nested', 'g-normal-nested') else 180))
        save(OUT/'plan.json', dict(batch_id='stage-h-'+time.strftime('%Y%m%d-%H%M%S'),
            started_unix=time.time(), deadline_unix=protocol['deadline_unix'], cells=cells,
            canary='D2-CANARY-'+secrets.token_hex(16)))
    plan = read(OUT/'plan.json')
    files = [*ROOT.joinpath('src').rglob('*.py'), *ROOT.joinpath('src').rglob('*.yaml'),
             *ROOT.joinpath('src').rglob('*.mjs'), *ROOT.joinpath('extensions').glob('*'),
             ROOT/'lab.py', ROOT/'verify_v2.py', *ROOT.joinpath('scenarios').glob('*.json')]
    hashes = {p.relative_to(ROOT).as_posix():hashlib.sha256(p.read_bytes()).hexdigest() for p in files if p.is_file()}
    freeze = OUT/'source-freeze.json'
    if freeze.exists():
        if read(freeze) != hashes:
            raise RuntimeError('Frozen kernel/scenario changed')
    else:
        save(freeze, hashes)
    status = dict(status='running', planned=len(plan['cells']), completed=0,
        attempts=0, startup_failures=0, workers=protocol['workers'], started_unix=time.time())
    queue = [(i, 0) for i in range(len(plan['cells']))]
    pending = {}
    stop = False
    with futures.ThreadPoolExecutor(max_workers=protocol['workers']) as pool:
        while queue or pending:
            while queue and len(pending)<protocol['workers'] and not stop:
                if time.time() >= plan['deadline_unix']:
                    stop=True;status.update(status='stopped', reason='8 hour deadline');break
                i, a = queue.pop(0)
                pending[pool.submit(launch, i, a)] = (i, a)
            if not pending:
                break
            done, _ = futures.wait(pending, timeout=30, return_when=futures.FIRST_COMPLETED)
            for future in done:
                i, a = pending.pop(future)
                try:
                    record = future.result()
                except Exception as exc:
                    record = dict(index=i, attempt=a, startup_failure=True, error_type=type(exc).__name__)
                    save(OUT/f'cell-{i}-{a}.json',record)
                status['attempts'] += 1
                status['startup_failures'] += int(record.get('startup_failure',False))
                check = record.get('verify_v2')
                failed = evidence_failures(record)
                # Model-only failure is all_passed=false with every evidence check true.
                if failed or (record.get('run_id') and check is None):
                    stop = True
                    status.update(status='stopped', reason='non-model verification failure',
                                  failed_run=record.get('run_id'), failed_checks=failed or ['verification_incomplete'])
                if status['startup_failures']/max(1,status['attempts'])>.20:
                    stop=True;status.update(status='stopped',reason='over 20% startup failures')
                if a==0 and retryable(record):
                    queue.append((i,1))
                else:
                    status['completed'] += 1
                status['last_run']=record.get('run_id')
            status['active']=len(pending)
            status['queued']=len(queue)
            status['updated_unix']=time.time()
            save(OUT/'progress.json',status)
    if not stop:
        status['status']='completed'
    status['finished_unix']=time.time()
    save(OUT/'progress.json',status)

if __name__ == '__main__':
    if len(sys.argv)>1 and sys.argv[1]=='worker':
        worker(int(sys.argv[2]),int(sys.argv[3]))
    else:
        main()
