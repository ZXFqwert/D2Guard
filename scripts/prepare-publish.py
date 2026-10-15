"""Copy only distributable source into an existing checkout root."""
from pathlib import Path
import argparse
import shutil
import os
import sqlite3
import json

root = Path(__file__).resolve().parents[1]
parser = argparse.ArgumentParser()
parser.add_argument('checkout', type=Path)
args = parser.parse_args()
checkout = args.checkout.resolve()
if not (checkout / '.git').is_dir():
    raise SystemExit('Destination must be an existing Git checkout')
destination = checkout
if (checkout / 'unified' / 'D2guard_core').exists():
    raise SystemExit('Update the checkout to the current root layout before publishing')
excluded = {'node_modules', '.venv', '.venv-server', '__pycache__', '.pytest_cache', 'data', 'dist', 'dist-web', '.node_modules.external-link'}
files = []
for directory in ['D2guard_core', 'D2guard_desk', 'tests', 'scripts', 'deployment', 'docs']:
    for base, dirs, names in os.walk(root / directory):
        dirs[:] = [d for d in dirs if d not in excluded and not d.startswith('.') and not d.endswith('.egg-info')]
        for name in names:
            if name not in excluded and (not name.startswith('.') or name == '.gitignore') and not name.endswith(('.sqlite3', '.log', '.pyc')):
                files.append(Path(base) / name)

for filename in ['README.md', '.gitignore', 'D2guard_contract.json', 'pytest.ini', 'conftest.py', 'start_all.py', 'start_all.bat', '启动D2Guard-Desk.bat']:
    files.append(root / filename)
secret = None
db = root / 'D2guard_core/data/d2guard.sqlite3'
if db.exists():
    with sqlite3.connect(db) as conn:
        row = conn.execute('SELECT payload FROM desktop_config WHERE id=1').fetchone()
        if row:
            secret = json.loads(row[0]).get('api_key')
for source in files:
    data = source.read_bytes()
    if secret and secret.encode() in data:
        raise SystemExit(f'Secret found in {source.relative_to(root)}')
    if b'ghp_' in data or b'-----BEGIN OPENSSH PRIVATE KEY-----' in data:
        # This scanner itself contains the signatures, not credentials.
        if source != Path(__file__).resolve():
            raise SystemExit(f'Potential credential in {source.relative_to(root)}')
    target = destination / source.relative_to(root)
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, target)
print(f'Prepared {len(files)} source files; private runtime data excluded.')
