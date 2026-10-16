"""Download the pinned official checkpoint and record local artifact integrity."""
import hashlib
import json
from pathlib import Path
import sys
import argparse
sys.path.insert(0, str(Path(__file__).parent / 'src'))
from original_laya import CHECKPOINTS

def main():
    from huggingface_hub import snapshot_download, hf_hub_url, get_hf_file_metadata
    parser = argparse.ArgumentParser()
    parser.add_argument('--local-path', type=Path, help='Verify files already downloaded from this pinned release')
    parser.add_argument('--checkpoint', choices=CHECKPOINTS, default='english')
    parser.add_argument('--output', type=Path, default=Path(__file__).parent / '.local/laya.json')
    parser.add_argument('--download-dir', type=Path)
    parser.add_argument('--device', choices=['cpu','cuda:0'], default='cpu')
    args = parser.parse_args()
    repo, revision = CHECKPOINTS[args.checkpoint]
    required = ['rl_agent_config.json', 'model.safetensors', 'encoder/config.json',
                'tokenizer/tokenizer.json', 'tokenizer/tokenizer_config.json']
    path = args.local_path.resolve() if args.local_path else Path(snapshot_download(repo, revision=revision,
        local_dir=str(args.download_dir) if args.download_dir else None, allow_patterns=required)).resolve()
    for name in required:
        if not (path / name).is_file():
            raise FileNotFoundError(name)
    hashes = {}
    for name in required:
        with (path/name).open('rb') as stream:
            hashes[name] = hashlib.file_digest(stream, 'sha256').hexdigest()
    metadata = get_hf_file_metadata(hf_hub_url(repo, 'model.safetensors', revision=revision))
    if metadata.commit_hash != revision or metadata.etag != hashes['model.safetensors']:
        raise ValueError('Weights do not match the official pinned release digest')
    target = args.output
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps({'repository':repo, 'revision':revision, 'path':str(path),'device':args.device,
        'sha256':hashes}, indent=2), encoding='utf-8')
    print('Prepared official original Laya:', repo, revision)

if __name__ == '__main__':
    main()
