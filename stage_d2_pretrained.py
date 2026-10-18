"""Download pinned public baselines, without touching existing model directories."""
import hashlib,json,time
from pathlib import Path
from huggingface_hub import snapshot_download
ROOT=Path(__file__).resolve().parent
OUT=ROOT/'.local/stage-d2'

def main():
    source=json.loads((OUT/'model-sources.json').read_text());results={}
    for repo,name in [('answerdotai/ModernBERT-large','modernbert'),('protectai/deberta-v3-base-prompt-injection-v2','classifier')]:
        if source[repo]['license']!='apache-2.0':raise ValueError('Expected permissive baseline license')
        start=time.time();path=OUT/('pretrained-'+name)
        snapshot_download(repo,revision=source[repo]['revision'],local_dir=path,token=False,
            allow_patterns=['*.json','*.safetensors','*.txt','*.model','LICENSE','README.md'],max_workers=4)
        files={str(p.relative_to(path)):hashlib.file_digest(p.open('rb'),'sha256').hexdigest() for p in path.rglob('*') if p.is_file() and '.cache' not in p.parts}
        results[name]={'repo':repo,'revision':source[repo]['revision'],'license':source[repo]['license'],'sha256':files,'seconds':time.time()-start}
        (OUT/'pretrained-download.json').write_text(json.dumps(results,indent=2));print(json.dumps({'downloaded':name,'revision':source[repo]['revision'],'seconds':time.time()-start}),flush=True)

if __name__=='__main__':main()
