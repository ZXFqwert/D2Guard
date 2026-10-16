"""Download the pinned official checkpoint and record local artifact integrity."""
import hashlib
import json
from pathlib import Path
import sys
import argparse
sys.path.insert(0, str(Path(__file__).parent / 'src'))
from original_laya import REPO, REVISION

def main():
    from huggingface_hub import snapshot_download, hf_hub_url, get_hf_file_metadata
    parser = argparse.ArgumentParser()
    parser.add_argument('--local-path', type=Path, help='Verify files already downloaded from this pinned release')
    args = parser.parse_args()
    path = args.local_path.resolve() if args.local_path else Path(snapshot_download(REPO, revision=REVISION,
        allow_patterns=['*.json', 'model.safetensors', 'tokenizer/*', 'encoder/config.json']))
    required = ['rl_agent_config.json', 'model.safetensors', 'encoder/config.json', 'tokenizer/tokenizer.json']
    for name in required:
        if not (path / name).is_file():
            raise FileNotFoundError(name)
    hashes = {}
    for file in sorted(path.rglob('*')):
        if file.is_file():
            with file.open('rb') as stream:
                hashes[file.relative_to(path).as_posix()] = hashlib.file_digest(stream, 'sha256').hexdigest()
    metadata = get_hf_file_metadata(hf_hub_url(REPO, 'model.safetensors', revision=REVISION))
    if metadata.commit_hash != REVISION or metadata.etag != hashes['model.safetensors']:
        raise ValueError('Weights do not match the official pinned release digest')
    target = Path(__file__).parent / '.local/laya.json'
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps({'repository':REPO, 'revision':REVISION, 'path':str(path),
        'sha256':hashes}, indent=2), encoding='utf-8')
    print('Prepared official original Laya:', REPO, REVISION)

if __name__ == '__main__':
    main()
