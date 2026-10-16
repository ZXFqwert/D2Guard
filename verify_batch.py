"""Verify paired evidence independently of the runtime's result labels."""
import argparse
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent


def read(path):
    return json.loads(path.read_text(encoding='utf-8'))


def lines(path):
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding='utf-8').splitlines() if line.strip()]


def verify(matrix):
    batch = read(matrix)
    rows = []
    manifests = []
    for result in batch['results']:
        folder = ROOT / 'runs' / result['run_id']
        manifest = read(folder / 'manifest.json')
        manifests.append(manifest)
        native = lines(folder / 'pi-events.jsonl')
        audit = lines(folder / 'audit.jsonl')
        receipts = lines(folder / 'receipts.jsonl')
        model_calls = {c['id'] for e in native if e.get('type') == 'message_end'
            and e.get('message', {}).get('role') == 'assistant'
            for c in e['message'].get('content', []) if c.get('type') == 'toolCall'}
        observed = [e for e in audit if e['type'] == 'tool_proposed' and e['agent_id'] == 'main']
        native_results = [e['message'] for e in native if e.get('type') == 'message_end'
            and e.get('message', {}).get('role') == 'toolResult']
        blocked = [e for e in audit if e['type'] == 'guard_decision' and e['verdict'] == 'BLOCK']
        receipt_calls = {r['call_id'] for r in receipts}
        checks = {
            'all_main_tools_originated_in_model_response': bool(observed) and all(e['call_id'] in model_calls for e in observed),
            'no_receipt_for_blocked_call': all(e['call_id'] not in receipt_calls for e in blocked),
            # Pi short-circuits tool_result extension handlers when a preflight hook blocks.
            # The native transcript still contains the authoritative failed toolResult.
            'blocked_network_call_has_native_error_result': all(any(r['toolCallId'] == e['call_id'] and r.get('isError') for r in native_results) for e in blocked if e['tool'] == 'net_fetch'),
            'model_http_response_observed': any(e['type'] == 'model_response' and e['status'] == 200 for e in audit),
            'initial_readme_matches_manifest': hashlib.sha256((folder/'workspace'/'README.md').read_bytes()).hexdigest() == manifest['initial_files']['README.md'],
        }
        rows.append({'run_id': result['run_id'], 'environment': manifest['environment'],
            'protection': manifest['protection'], 'checks': checks,
            'result': {key:result[key] for key in ('model_run_ok','task_completed','attack_succeeded','defense_blocked','received_bytes')}})
    paired = []
    for index in range(0, len(manifests), 4):
        group = manifests[index:index+4]
        if len(group) != 4:
            paired.append(False)
            continue
        invariant = lambda key: all(m[key] == group[0][key] for m in group)
        paired.append(all(invariant(k) for k in ['task_sha256','scenario_sha256','source_sha256','pi_cli_sha256','model','api_style'])
            and group[0]['initial_files'] == group[1]['initial_files']
            and group[2]['initial_files'] == group[3]['initial_files']
            and len({m['initial_files']['.env'] for m in group}) == 1)
    report = {'matrix':matrix.name, 'evidence_invariants_pass': all(paired) and all(all(r['checks'].values()) for r in rows),
        'paired_environment_and_configuration_match': paired, 'runs':rows,
        'scope':'Evidence integrity only; not a claim of general attack success or defense accuracy.'}
    target = matrix.with_name(matrix.stem + '-verification.json')
    target.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return report['evidence_invariants_pass']


if __name__ == '__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('matrix', type=Path)
    args=parser.parse_args()
    raise SystemExit(0 if verify(args.matrix) else 1)
