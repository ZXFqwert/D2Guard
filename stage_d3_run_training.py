"""Run the three pre-registered fits once, with one shared wall-clock budget."""
import argparse
import hashlib
import importlib.metadata
import json
import os
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent
OUT = ROOT / '.local/stage-d3'


def main(round_number):
    if round_number != 1:
        raise ValueError('Exactly one registered round')
    folder = OUT
    if (OUT / 'selected-before-heldout.json').exists():
        raise ValueError('Model selection is already frozen')
    admission=json.loads((OUT/'admission.json').read_text())
    probe=json.loads((OUT/'probe.json').read_text())
    if not admission['passed'] or not probe['pretrain_passed']:
        raise ValueError('Admission and shortcut gates must pass before starting the clock')
    clock=folder/'training-clock.json'
    if not clock.exists():
        with clock.open('x') as stream:json.dump({'started_unix':time.time()},stream)
    files = sorted(ROOT.glob('stage_d*.py')) + sorted(ROOT.glob('train_stage_d*.py')) + [ROOT / 'evaluate_stage_d3.py']
    files += sorted((ROOT / 'src').rglob('*.py'))
    files += [OUT / 'protocol.json', OUT / 'teacher-amendment.json',
              OUT / 'adjudication-policy.json', OUT / 'data-cutoff-policy.json',
              OUT / 'data-preparation-amendment.json', OUT / 'semantic-view.json',
              OUT / 'isolation.json', OUT / 'collection.json',
              folder / 'admission.json', folder / 'probe.json', folder / 'admitted.jsonl',
              OUT / 'frozen-heldout.jsonl',OUT / 'new-validation-frozen.jsonl']
    files += [p for p in (OUT/'continuation-authorization.json',OUT/'continuation-inputs.json',
                         OUT/'gapfill-authorization.json',OUT/'gapfill/brief-amendment.json') if p.exists()]
    manifest = {'started_unix': time.time(), 'round': round_number,
                'python_version': sys.version,
                'package_versions': {name: importlib.metadata.version(name) for name in ('torch','transformers','laya','tokenizers','numpy')},
                'sha256': {str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest() for p in files}}
    with (folder / 'training-source-manifest.json').open('x', encoding='utf-8') as stream:
        json.dump(manifest, stream, indent=2)
    env = {**os.environ, 'CUDA_VISIBLE_DEVICES': '0', 'OMP_NUM_THREADS': '4', 'PYTHONPATH': 'src'}
    status = {'status': 'running', 'completed': []}
    status_path = folder / 'training-runner.json'
    def record():
        status_path.write_text(json.dumps(status, indent=2), encoding='utf-8')
    def run(name, args):
        for relative,expected in manifest['sha256'].items():
            if hashlib.sha256((ROOT/relative).read_bytes()).hexdigest()!=expected:
                raise ValueError('Source or frozen input changed during training/evaluation')
        status['active'] = name
        record()
        clock = folder / 'training-clock.json'
        remaining = 3600 if not clock.exists() else 3600 - (time.time() - json.loads(clock.read_text())['started_unix'])
        remaining=min(remaining,json.loads((OUT/'protocol.json').read_text())['started_unix']+14400-time.time())
        if remaining <= 0:
            raise TimeoutError('Shared training/evaluation 60-minute stop')
        with (folder / (name + '.log')).open('x', encoding='utf-8') as log:
            subprocess.run([sys.executable, '-u', *args], cwd=ROOT, env=env, stdout=log,
                           stderr=subprocess.STDOUT, timeout=remaining, check=True)
        status['completed'].append(name)
        record()
    try:
        for base in ('english', 'multilingual', 'modernbert'):
            run(base + '-smoke', ['train_stage_d3.py', base, '--round', str(round_number), '--smoke'])
            smoke = json.loads((folder / (base + '-smoke.json')).read_text())
            if not smoke['passed'] or not smoke['original_unchanged']:
                raise RuntimeError('Forward/backward smoke failed')
        for base in ('english', 'multilingual', 'modernbert'):
            run(base + '-fit', ['train_stage_d3.py', base, '--round', str(round_number)])
        run('round-evaluation', ['evaluate_stage_d3.py'])
        status['status'] = 'completed'
    except Exception as error:
        status.update(status='stopped', error_type=type(error).__name__, error=str(error))
        raise
    finally:
        status['finished_unix'] = time.time()
        record()


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--round', type=int, default=1)
    parser.add_argument('--launch', action='store_true')
    args=parser.parse_args()
    if args.launch:
        if sys.platform!='linux' or args.round != 1:
            raise ValueError('Launch only on the Linux compute host, for a registered round')
        folder=OUT
        with (folder/'runner-launch.json').open('x') as marker:
            with (folder/'runner.log').open('x',encoding='utf-8') as log:
                process=subprocess.Popen([sys.executable,'-u',str(Path(__file__).resolve()),'--round',str(args.round)],
                    cwd=ROOT,stdin=subprocess.DEVNULL,stdout=log,stderr=subprocess.STDOUT,start_new_session=True)
            json.dump({'pid':process.pid,'launched_unix':time.time()},marker)
        print(json.dumps({'pid':process.pid,'round':args.round}),flush=True)
    else:
        main(args.round)
