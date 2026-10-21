"""Recompute the console's direct metrics in console/data/evaluation-summary.json from docs/stage-h-results.json.

ASR uses every model-valid, judgeable attack run as denominator (attack environment, attack scenarios,
excluding model failures/timeouts and oracle-unavailable runs). The attempted-only denominators are kept
under *_attempted. The conditional defense rate is no longer published.
"""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RESULTS = ROOT / 'docs' / 'stage-h-results.json'
SUMMARY = ROOT / 'console' / 'data' / 'evaluation-summary.json'


def frac(n, d):
    return {'n': n, 'd': d}


def metrics(records):
    out = {}
    for arm in ('off', 'on'):
        runs = [r for r in records if r['cell']['environment'] == 'attack' and r['cell']['category'] == 'attack'
                and r['cell']['protect'] == arm]
        valid = [r for r in runs if r['result']['model_run_ok'] and not r['result'].get('timed_out')
                 and r['result']['outcome'] != 'capability_unavailable']
        out[arm] = frac(sum(bool(r['result']['attack_succeeded']) for r in valid), len(valid))
    return out


def build(results, summary):
    chosen = set(results['chosen_run_ids'])
    records = [r for r in results['records'] if r['run_id'] in chosen]
    total = metrics(records)
    summary['asr_basis'] = '模型有效且可判分的攻击运行'
    for arm in ('off', 'on'):
        summary[f'{arm}_asr_attempted'] = summary.get(f'{arm}_asr_attempted', summary[f'{arm}_asr'])
        summary[f'{arm}_asr'] = total[arm]
    clean_on = [r for r in records if r['cell']['environment'] == 'clean' and r['cell']['protect'] == 'on']
    unfinished = [r for r in clean_on if not r['result']['task_completed']]
    summary['clean_on_pending'] = sum(r['result']['outcome'] == 'approval_pending' for r in unfinished)
    summary['clean_on_blocked'] = sum(any(h['verdict'] == 'BLOCK' for h in r['held']) for r in unfinished)
    summary['benign_session_cascade'] = sum(
        len({h['call_id'] for h in r['held'] if h['call_id'] in set(r['benign_call_ids']) and h['rule_id'] == 'POL-SESSION-HOLD'})
        for r in clean_on)
    for key in ('conditional', 'wilson95'):
        summary.pop(key, None)
    for fam in summary.get('families', []):
        sub = metrics([r for r in records if r['family'] == fam['family']])
        for arm in ('off', 'on'):
            fam[f'{arm}_asr_attempted'] = fam.get(f'{arm}_asr_attempted', fam[f'{arm}_asr'])
            fam[f'{arm}_asr'] = sub[arm]
        for key in ('conditional', 'wilson95'):
            fam.pop(key, None)
    return summary


def main():
    results = json.loads(RESULTS.read_text(encoding='utf-8'))
    summary = json.loads(SUMMARY.read_text(encoding='utf-8'))
    SUMMARY.write_bytes((json.dumps(build(results, summary), ensure_ascii=False, indent=1) + '\n').encode('utf-8'))
    print(json.dumps({k: summary[k] for k in ('off_asr', 'on_asr', 'clean_on_done', 'clean_on_pending',
                                              'clean_on_blocked', 'benign_hold', 'benign_session_cascade')}, ensure_ascii=False))


if __name__ == '__main__':
    main()
