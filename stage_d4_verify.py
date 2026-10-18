"""Read-only final evidence and credential hygiene checks; never prints secrets."""
import hashlib
import json
import os
import subprocess
from pathlib import Path
from stage_d4_protocol import ROOT,OUT,D3,sha,save

def main():
    from stage_d2_cloud import credentials
    _,key=credentials();secrets=[key]
    provider=ROOT/'.local/provider.json'
    if provider.exists():
        value=json.loads(provider.read_text()).get('api_key')
        if value:secrets.append(value)
    paths=[*ROOT.glob('stage_d4_*.py'),ROOT/'evaluate_stage_d4.py',ROOT/'tests/test_stage_d4.py',ROOT/'src/d2v2/request_model.py',ROOT/'src/d2v2/core.py',
           ROOT/'docs/23-stage-d4-report.md',ROOT/'docs/stage-d4-results.json',ROOT/'docs/stage-d4-verification.md']
    hits=[str(p.relative_to(ROOT)) for p in paths if p.exists() and any(s in p.read_text(encoding='utf-8',errors='replace') for s in secrets)]
    fields=[];log=OUT/'cloud-requests.jsonl'
    if log.exists():
        for i,line in enumerate(log.read_text().splitlines()):
            if set(json.loads(line))!={'model','seconds','tokens'}:fields.append(i)
            if any(s in line for s in secrets):hits.append('private request log')
    tracked=subprocess.check_output(['git','ls-files','.local'],cwd=ROOT,text=True,encoding='utf-8',errors='replace').strip()
    ignored=subprocess.run(['git','check-ignore','-q','.local/teacher.env'],cwd=ROOT).returncode==0
    frozen=json.loads((OUT/'threshold.json').read_text());validation=sha(D3/'new-validation-frozen.jsonl')==frozen['validation_sha256']
    prior=json.loads((D3/'frozen-evaluation-started.json').read_text())
    held=sha(D3/'frozen-heldout.jsonl')==prior['heldout_sha256'];gold=sha(D3/'gold.jsonl')==prior['gold_sha256']
    blind=OUT/'reviewer-blind.jsonl';blind_ok=None
    if blind.exists():blind_ok=all(set(json.loads(line))=={'id','text'} for line in blind.read_text(encoding='utf-8').splitlines())
    result={'passed':not hits and not fields and not tracked and ignored and validation and held and gold and blind_ok is not False,
      'known_secret_hits':hits,'request_log_invalid_fields':fields,'local_tracked':bool(tracked),'teacher_env_ignored':ignored,
      'validation_unchanged':validation,'heldout_unchanged':held,'gold_unchanged':gold,'blind_has_only_id_text':blind_ok,
      'process_s1_environment_set':bool(os.environ.get('D2_S1_CONFIG')),'production_config_created':(OUT/'s1-enabled-config.json').exists()}
    save('security-verification.json',result);print(json.dumps(result))

if __name__=='__main__':main()
