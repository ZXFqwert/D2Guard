"""Configure a delivery copy; credentials stay in .local, never in output."""
import argparse
import getpass
import json
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def save(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')


def configure(root=ROOT, device='auto', provider_from=None, interactive=False):
    import torch
    if device == 'auto':
        device = 'cuda:0' if torch.cuda.is_available() else 'cpu'
    if device == 'cuda:0' and not torch.cuda.is_available():
        raise RuntimeError('CUDA is unavailable; choose --device cpu')
    local = root / '.local'
    local.mkdir(exist_ok=True)
    provider_path = local / 'provider.json'
    if provider_from:
        provider = json.loads(Path(provider_from).read_text(encoding='utf-8-sig'))
    elif all(os.environ.get(k) for k in ('D2_PROVIDER_BASE_URL','D2_PROVIDER_API_KEY','D2_PROVIDER_MODEL')):
        provider = {k: os.environ[v] for k, v in [('base_url','D2_PROVIDER_BASE_URL'),
                    ('api_key','D2_PROVIDER_API_KEY'),('main_model','D2_PROVIDER_MODEL')]}
        provider['api_style'] = os.environ.get('D2_PROVIDER_API_STYLE','chat_completions')
    elif provider_path.is_file():
        provider = json.loads(provider_path.read_text(encoding='utf-8-sig'))
    elif interactive:
        provider = {'base_url':input('API base URL: ').strip(),
                    'api_key':getpass.getpass('API key (hidden): ').strip(),
                    'main_model':input('Model name: ').strip(),
                    'api_style':input('API style [chat_completions / responses] (default chat_completions): ').strip() or 'chat_completions'}
    else:
        raise ValueError('Set D2_PROVIDER_BASE_URL / D2_PROVIDER_API_KEY / D2_PROVIDER_MODEL, or use --interactive')
    if not all(provider.get(k) for k in ('base_url','api_key','main_model')):
        raise ValueError('Provider URL, API key and model are required')
    if provider.get('api_style') not in ('chat_completions','responses'):
        raise ValueError('API style must be chat_completions or responses')
    save(provider_path, provider)
    os.chmod(provider_path, 0o600)
    original = json.loads((root / 'laya-config.example.json').read_text(encoding='utf-8'))
    original.update(path=str(root / original['path']), device=device)
    save(local / 'laya.json', original)
    s1 = json.loads((root / 's1-config.example.json').read_text(encoding='utf-8'))
    s1['device'] = device
    for value in [*s1.values(), *s1['models'].values()]:
        if isinstance(value, dict) and 'path' in value:
            value['path'] = str(root / value['path'])
    save(local / 's1.json', s1)
    print(f'Configured original Laya + frozen S1 ({device}, taint_gate) and provider. Credentials not printed.')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--device', choices=['auto','cpu','cuda:0'], default='auto')
    parser.add_argument('--provider-from', type=Path)
    parser.add_argument('--interactive', action='store_true')
    args = parser.parse_args()
    configure(device=args.device, provider_from=args.provider_from, interactive=args.interactive)
