"""Read-only evidence checks; never print credentials or test fragments."""
import json
import subprocess
from pathlib import Path
from stage_d5_protocol import ROOT,OUT,read,sha,save,blocked_sources

def main():
    from stage_d2_cloud import credentials
    keys={credentials()[1],credentials('glm-5.3-flash')[1]}
    paths=[*ROOT.glob('stage_d5_*.py'),ROOT/'train_stage_d5.py',ROOT/'evaluate_stage_d5.py',ROOT/'stage_d2_cloud.py',ROOT/'src/d2v2/request_model.py',ROOT/'src/d2v2/core.py',ROOT/'lab.py',ROOT/'tests/test_stage_d5.py',ROOT/'docs/24-stage-d5-report.md',ROOT/'docs/stage-d5-results.json',ROOT/'docs/stage-d5-verification.md',ROOT/'docs/03-status.md',ROOT/'docs/整体设计文档.md',ROOT/'docs/12-codex-execution-plan.md']
    hits=[str(p.relative_to(ROOT)) for p in paths if p.exists() and any(key in p.read_text(encoding='utf-8',errors='replace') for key in keys)]
    logs=read(OUT/'cloud-requests.jsonl');fields=all(set(r)=={'model','seconds','tokens'} for r in logs)
    if any(key in (OUT/'cloud-requests.jsonl').read_text(encoding='utf-8') for key in keys):hits.append('private cloud request log')
    snapshot_path=OUT/'pre-flash-switch/stop-snapshot.json'
    snapshot=json.loads(snapshot_path.read_text());unchanged=all(sha(ROOT/path)==expected for path,expected in snapshot['frozen_sha256'].items())
    d3=json.loads((ROOT/'.local/stage-d3/admission.json').read_text());retained=sha(ROOT/'.local/stage-d3/admitted.jsonl')==d3['admitted_sha256']
    d4=json.loads((ROOT/'.local/stage-d4/threshold.json').read_text());validation=sha(ROOT/'.local/stage-d3/new-validation-frozen.jsonl')==d4['validation_sha256']
    prior=json.loads((ROOT/'.local/stage-d3/frozen-evaluation-started.json').read_text());held=sha(ROOT/'.local/stage-d3/frozen-heldout.jsonl')==prior['heldout_sha256'];gold=sha(ROOT/'.local/stage-d3/gold.jsonl')==prior['gold_sha256']
    real=sha(ROOT/'.local/stage-d4/benign-frozen.jsonl')=='876214466918df991c8878772c008961dc6d51a4150c27fc0a63431a8bfde521'
    blocked,_=blocked_sources();inventory=json.loads((OUT/'inventory.json').read_text());overlap=sorted(blocked&{r['repository'].lower() for r in inventory})
    tracked=subprocess.check_output(['git','ls-files','.local'],cwd=ROOT,text=True,encoding='utf-8',errors='replace').strip();ignored=subprocess.run(['git','check-ignore','-q','.local/teacher.env'],cwd=ROOT).returncode==0
    default_off=not any((ROOT/p).exists() for p in ('.local/stage-d5/s1-enabled-config.json','.local/stage-d4/s1-enabled-config.json'))
    result={'passed':not hits and fields and unchanged and retained and validation and held and gold and real and not overlap and not tracked and ignored and default_off,'secret_hits':hits,'request_log_fields_valid':fields,'snapshot_files_unchanged':unchanged,'D3_training_unchanged':retained,'D3_validation_unchanged':validation,'heldout_unchanged':held,'gold_unchanged':gold,'D4_real_test_unchanged':real,'test_repository_overlap':overlap,'local_tracked':bool(tracked),'teacher_env_ignored':ignored,'production_config_absent':default_off,'training_clock_absent':not (OUT/'training-clock.json').exists()}
    save('security-verification.json',result);print(json.dumps(result))

if __name__=='__main__':main()
