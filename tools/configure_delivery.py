"""Create local provider configuration from environment without logging credentials."""
import json,os
from pathlib import Path
root=Path(__file__).resolve().parents[1]
c={'base_url':os.environ['D2_PROVIDER_BASE_URL'],'api_key':os.environ['D2_PROVIDER_API_KEY'],'main_model':os.environ['D2_PROVIDER_MODEL'],'api_style':os.environ.get('D2_PROVIDER_API_STYLE','chat_completions')}
(root/'.local').mkdir(exist_ok=True);(root/'.local/provider.json').write_text(json.dumps(c));os.chmod(root/'.local/provider.json',0o600)
l=json.loads((root/'laya-config.example.json').read_text());l['path']=str(root/l['path']);(root/'.local/laya.json').write_text(json.dumps(l))
print('Provider and original Laya configuration prepared; credentials not printed.')
