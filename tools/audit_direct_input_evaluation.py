"""Summarize retained paired evidence without exposing prompts or credentials."""
import argparse
from collections import defaultdict
import hashlib
import json
from pathlib import Path
import statistics

ROOT = Path(__file__).resolve().parents[1]


def read(path):
    return json.loads(path.read_text(encoding='utf-8'))


def audit(report_path, runs):
    report = read(report_path)
    if report['status'] != 'completed' or len(report['records']) != report['expected_runs']:
        raise ValueError('Evaluation has not completed: ' + str(report_path))
    pairs, groups, records = defaultdict(list), {}, []
    for record in report['records']:
        if 'result' not in record:
            raise ValueError('Missing run result: ' + str(record))
        result = record['result']
        rid = result['run_id']
        folder = runs / rid
        manifest = read(folder / 'manifest.json')
        pairs[(record['scenario'], record['repeat'])].append(manifest)
        key = record['group'] + ':' + record['protect']
        group = groups.setdefault(key, {'runs': 0, 'model_run_ok': 0, 'task_completed': 0,
                                       'attack_succeeded': 0, 'held_runs': 0, 'asked_actions': 0,
                                       'blocked_actions': 0, 'tool_calls': 0, 'verify_passed': 0,
                                       'evidence_checks_passed': 0, 'received_bytes': 0})
        group['runs'] += 1
        for k in ('model_run_ok', 'task_completed', 'attack_succeeded'):
            group[k] += bool(result.get(k))
        group['held_runs'] += bool(result.get('asked_calls') or result.get('blocked_calls'))
        group['asked_actions'] += len(result.get('asked_calls', []))
        group['blocked_actions'] += len(result.get('blocked_calls', []))
        group['tool_calls'] += len(result.get('tool_calls', []))
        group['received_bytes'] += result.get('received_bytes', 0)
        group['verify_passed'] += record['verify_v2']['all_passed']
        group['evidence_checks_passed'] += record['verify_v2']['evidence_checks_passed']
        reasoning_updates = 0
        for line in (folder / 'pi-events.jsonl').read_text(encoding='utf-8').splitlines():
            event = json.loads(line)
            reasoning_updates += event.get('assistantMessageEvent', {}).get('type') == 'thinking_delta'
        proposed = {}
        for line in (folder / 'audit.jsonl').read_text(encoding='utf-8').splitlines():
            event = json.loads(line)
            if event.get('type') == 'tool_proposed':
                proposed[event['call_id']] = event.get('tool')
        records.append({
            **{k: record[k] for k in ('scenario', 'environment', 'protect', 'repeat', 'group')},
            **{k: result.get(k) for k in ('run_id', 'model_run_ok', 'timed_out', 'task_completed',
                'attack_succeeded', 'outcome', 'received_bytes', 'model_request_count',
                'elapsed_seconds', 'agent_elapsed_seconds', 'service_startup_seconds',
                'post_agent_evidence_wait_seconds')},
            'asked_policies': [x['policy'] for x in result.get('asked_calls', [])],
            'held_tools': [proposed.get(x['call_id']) for x in result.get('asked_calls', [])],
            'verify_passed': record['verify_v2']['all_passed'],
            'evidence_checks_passed': record['verify_v2']['evidence_checks_passed'],
            'reasoning_updates': reasoning_updates,
            'reasoning_capable': manifest.get('reasoning_capable', False),
            'manifest_sha256': hashlib.sha256((folder/'manifest.json').read_bytes()).hexdigest(),
            'result_sha256': hashlib.sha256((folder/'result.json').read_bytes()).hexdigest(),
        })
    compared = ['model', 'api_style', 'pi_version', 'pi_cli_sha256', 'source_sha256',
                'scenario_sha256', 'task_sha256', 'user_input_sha256', 'fixture_sha256',
                'initial_files', 'experiment_limits', 'max_output_tokens', 'content_model',
                'reasoning_capable']
    mismatches, git_index_differences = [], []
    for pair, manifests in pairs.items():
        if len(manifests) != 2:
            raise ValueError('Expected exactly two lanes: ' + repr(pair))
        for key in compared:
            if manifests[0].get(key) != manifests[1].get(key):
                if key == 'initial_files':
                    left, right = (m[key] for m in manifests)
                    paths = sorted(k for k in set(left) | set(right) if left.get(k) != right.get(k))
                    if paths == ['.git/index']:
                        # Git's index caches each worktree's filesystem stat values.
                        # Keep this byte difference explicit; all tracked contents,
                        # refs, objects and every other initial file still compare.
                        git_index_differences.append({'scenario': pair[0], 'repeat': pair[1], 'paths': paths})
                        continue
                mismatches.append({'scenario': pair[0], 'repeat': pair[1], 'field': key})
    return {'batch_id': report['batch_id'], 'protocol': report['protocol'],
            'repeats': report['repeats'], 'runs': len(records), 'pairs': len(pairs),
            'paired_fields_compared': compared, 'paired_mismatches': mismatches,
            'git_index_byte_differences': git_index_differences,
            'groups': groups, 'records': records,
            'median_agent_seconds': statistics.median(r['agent_elapsed_seconds'] for r in records),
            'all_evidence_checks_passed': all(r['evidence_checks_passed'] for r in records),
            'all_runs_valid': all(r['model_run_ok'] for r in records)}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('reports', nargs='+', type=Path)
    parser.add_argument('--runs', type=Path, default=ROOT/'runs')
    parser.add_argument('--output', required=True, type=Path)
    args = parser.parse_args()
    summaries = [audit(path, args.runs) for path in args.reports]
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps({'batches': summaries}, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
    print(json.dumps([{'batch': b['batch_id'], 'runs': b['runs'], 'pairs': b['pairs'],
                      'paired_mismatches': b['paired_mismatches'], 'valid': b['all_runs_valid']} for b in summaries]))


if __name__ == '__main__':
    main()
