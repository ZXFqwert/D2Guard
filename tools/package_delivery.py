"""Package portable sources, frozen weights and the selected demo evidence."""
import argparse
import json
from pathlib import Path
import zipfile

ROOT = Path(__file__).resolve().parents[1]
DIRECTORIES = ('acceptance','console','deploy','extensions','scenarios','src','tests','tools','training')
ROOT_FILES = ('README.md','AGENTS.md','使用说明.md','WINDOWS-使用说明.md','lab.py','verify_v2.py','run_evaluation.py',
              'package.json','runtime-lock.json','policies.yaml','laya-config.example.json',
              's1-config.example.json','requirements-core.txt','requirements-gpu.txt',
              'requirements-laya.txt','setup-windows.bat','setup-linux.sh','start-console.bat',
              'start-console.sh','build-submission.bat','build-submission.sh','demo-runs.json',
              'supplemental-runs.json','runtime-source-manifest.json')
DOC_FILES = ('DELIVERY.md', '37-cve-and-split-injection-20261020.md',
             '38-multi-mcp-and-direct-metrics-20261021.md',
             '39-runtime-and-compute-handoff.md', '40-multiturn-final-20261021.md',
             '41-final-acceptance-20261021.md', 'stage-h-results.json',
             'stage-c2-scenario-inventory.json')
BATCH_FILES = ('evaluation-20261020-211149.json', 'evaluation-20261021-080202.json',
               'evaluation-20261021-091932.json')


def files(root):
    # Training and evaluation helpers are needed by the complete unit-test suite.
    for path in sorted(root.glob('*.py')):
        if path.name not in ROOT_FILES:
            yield path
    for name in BATCH_FILES:
        path = root / 'runs' / name
        if not path.is_file():
            raise FileNotFoundError('Missing evaluation batch: ' + name)
        yield path
    for name in DOC_FILES:
        path = root / 'docs' / name
        if not path.is_file():
            raise FileNotFoundError('Missing current delivery documentation: ' + name)
        yield path
    for path in sorted((root/'docs/figures').glob('console-arena-direct-metrics.png')):
        yield path
    for name in ROOT_FILES:
        path = root / name
        if path.is_file():
            yield path
    for name in [*DIRECTORIES, 'weights/D2Guard-multilingual', 'weights/Laya-original-english']:
        for path in sorted((root / name).rglob('*')):
            relative = path.relative_to(root)
            if path.is_file() and not any(part in ('.local','.cache','__pycache__') or part.startswith('.venv') for part in relative.parts) and path.suffix != '.pyc':
                yield path
    run_ids = json.loads((root/'demo-runs.json').read_text(encoding='utf-8'))
    supplement = root / 'supplemental-runs.json'
    if supplement.exists():
        run_ids += json.loads(supplement.read_text(encoding='utf-8'))
    for rid in dict.fromkeys(run_ids):
        if not isinstance(rid, str) or Path(rid).name != rid or rid in ('.', '..'):
            raise ValueError('Invalid run ID in delivery evidence list')
        if not (root/'runs'/rid/'manifest.json').is_file():
            raise FileNotFoundError('Missing selected evidence: ' + rid)
        for path in sorted((root/'runs'/rid).rglob('*')):
            if path.is_file() and '.local' not in path.parts and path.name != 'fingerprint.key':
                yield path


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    if (ROOT/'runtime-source-manifest.json').exists():
        from verify_delivery_sources import verify
        result = verify(ROOT)
        if not result['passed']:
            raise RuntimeError('Runtime sources differ from delivery manifest: '+', '.join(result['mismatches']))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    # Exclusive create: an earlier submitted archive is never overwritten.
    with zipfile.ZipFile(args.output, 'x', compression=zipfile.ZIP_DEFLATED, compresslevel=1) as archive:
        for path in files(ROOT):
            archive.write(path, 'D2Guard/' + path.relative_to(ROOT).as_posix())
    with zipfile.ZipFile(args.output) as archive:
        bad = archive.testzip()
        if bad:
            raise RuntimeError('ZIP integrity check failed: ' + bad)
        print(f'Packaged and checked {len(archive.infolist())} files: {args.output}')


if __name__ == '__main__':
    main()
