"""Sequential preparation with immutable outputs and the shared generation budget."""
import argparse
import hashlib
import json
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent


def main(number, after_supplement=False):
    if number not in (1, 2, 3):
        raise ValueError('At most three rounds')
    relative = f'.local/stage-d2/round-{number}'
    folder = ROOT / relative
    started = json.loads((folder / 'generation-clock.json').read_text())['started_unix']
    if after_supplement:
        while not (folder/'supplement-summary.json').exists():
            if time.time()-started >= 10800:
                raise TimeoutError('Original generation/review clock expires')
            time.sleep(2)
        if any(folder.glob('*-fit-started.json')) or (folder/'teacher-votes.jsonl').exists():
            raise ValueError('This supplement path only precedes teacher review and fitting')
        initial=folder/'generated-initial.jsonl'
        if initial.exists():
            raise ValueError('Supplement composition already attempted')
        original=folder/'generated.jsonl';supplement=folder/'generated-supplement.jsonl'
        initial_bytes=original.read_bytes();added_bytes=supplement.read_bytes()
        combined=initial_bytes+added_bytes
        rows=[json.loads(line) for line in combined.decode('utf-8').splitlines() if line.strip()]
        if len({row['id'] for row in rows})!=len(rows):
            raise ValueError('Supplement reused an existing candidate')
        original.rename(initial)
        with original.open('xb') as f:f.write(combined)
        (folder/'candidate-composition.json').write_text(json.dumps({
            'initial_sha256':hashlib.sha256(initial_bytes).hexdigest(),
            'supplement_sha256':hashlib.sha256(added_bytes).hexdigest(),
            'combined_sha256':hashlib.sha256(combined).hexdigest(),'candidate_n':len(rows),
            'clock_reset':False,'recorded_unix':time.time()},indent=2))
        names=['isolated.jsonl','isolation.json','preparation-status.json','upload-for-isolation.log',
               'full-isolation.log','fetch-isolated.jsonl.log','fetch-isolation.json.log','teacher-admission.log']
        for name in names:
            old=folder/name
            if old.exists():
                destination=folder/('before-supplement-'+name)
                if destination.exists():raise ValueError('Do not overwrite initial preparation evidence')
                old.rename(destination)
        command=(f'test ! -e {relative}/before-supplement-isolated.jsonl && '
                 f'mv {relative}/isolated.jsonl {relative}/before-supplement-isolated.jsonl && '
                 f'mv {relative}/isolation.json {relative}/before-supplement-isolation.json')
        subprocess.run([sys.executable,'.local/stage_d2_remote.py','exec',command],cwd=ROOT,check=True,
                       timeout=max(1,10800-(time.time()-started)))
    status = {'status': 'waiting_for_generation'}
    status_path = folder / 'preparation-status.json'
    if status_path.exists():
        raise ValueError('Preparation already attempted; preserve its outputs')
    def record():
        status['seconds'] = time.time() - started
        status_path.write_text(json.dumps(status, indent=2), encoding='utf-8')
    def budget():
        remaining = 10800 - (time.time() - started)
        if remaining <= 0:
            raise TimeoutError('Generation/review three-hour wall-clock stop')
        return remaining
    def run(phase, args):
        status['status'] = phase
        record()
        with (folder / (phase + '.log')).open('x', encoding='utf-8') as log:
            subprocess.run([sys.executable, *args], cwd=ROOT, stdout=log, stderr=subprocess.STDOUT,
                           timeout=budget(), check=True)
    remote = '.local/stage_d2_remote.py'
    try:
        record()
        while not (folder / 'generation-summary.json').exists():
            budget()
            time.sleep(2)
        run('upload-for-isolation', [remote, 'upload', 'stage_d2_isolation.py',
                                    relative + '/generated.jsonl', relative + '/generation-clock.json',
                                    relative + '/public-candidates.jsonl'])
        run('full-isolation', [remote, 'exec', 'CUDA_VISIBLE_DEVICES=0 OMP_NUM_THREADS=4 PYTHONPATH=src '
                              f'.venv/bin/python -u stage_d2_isolation.py --round {number}'])
        for name in ('isolated.jsonl', 'isolation.json'):
            run('fetch-' + name, [remote, 'get-fast', relative + '/' + name, relative + '/' + name])
        run('teacher-admission', ['-u', 'stage_d2_admit.py', '--round', str(number)])
        admission = json.loads((folder / 'admission.json').read_text())
        if not admission['passed']:
            status['status'] = 'admission_failed'
            return
        run('shortcut-probe', ['-u', 'stage_d2_probe.py', '--round', str(number)])
        probe = json.loads((folder / 'probe.json').read_text())
        status['status'] = 'ready_for_training' if probe['pretrain_passed'] else 'shortcut_probe_failed'
    except Exception as error:
        status.update(status='stopped', error_type=type(error).__name__, error=str(error))
        raise
    finally:
        record()


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--round', type=int, default=1)
    parser.add_argument('--after-supplement', action='store_true')
    args=parser.parse_args()
    main(args.round,args.after_supplement)
