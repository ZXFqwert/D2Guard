"""Verify the common runtime source bytes on Windows, Linux or in the delivery."""
import argparse
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def verify(root):
    root = Path(root).resolve()
    manifest = json.loads((root/'runtime-source-manifest.json').read_text(encoding='utf-8'))
    mismatches = []
    for name, expected in manifest['files'].items():
        path = (root/name).resolve()
        if not path.is_relative_to(root) or not path.is_file():
            mismatches.append(name)
        elif hashlib.sha256(path.read_bytes()).hexdigest() != expected:
            mismatches.append(name)
    return {'files':len(manifest['files']), 'mismatches':mismatches, 'passed':not mismatches}


if __name__ == '__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root',type=Path,default=ROOT)
    args=parser.parse_args()
    result=verify(args.root)
    print(json.dumps(result,ensure_ascii=False))
    raise SystemExit(0 if result['passed'] else 1)
