"""Read-only native Pi -> plugin -> core evidence audit. Never runs an agent."""
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path


def records(path):
    return [json.loads(line) for line in path.read_text(encoding='utf-8').splitlines() if line.strip()]


def text_parts(message):
    # Only public message text, never hidden reasoning.
    return '\n'.join(part['text'] for part in message.get('content', []) if part.get('type') == 'text')


def audit(folder):
    native = records(folder / 'pi-events.jsonl')
    observed = records(folder / 'audit.jsonl')
    core = records(folder / 'core.jsonl')
    messages = [event['message'] for event in native if event.get('type') == 'message_end']
    calls = [part for message in messages if message.get('role') == 'assistant'
             for part in message.get('content', []) if part.get('type') == 'toolCall']
    proposals = {e['call_id']: e for e in observed if e['type'] == 'tool_proposed'}
    decisions = {e['call_id']: e for e in observed if e['type'] == 'guard_decision'}
    returns = {e['call_id']: e for e in observed if e['type'] == 'tool_result'}
    native_returns = [m for m in messages if m.get('role') == 'toolResult']
    successes = [m for m in native_returns if not m.get('isError')]
    matched_args = sum(call['id'] in proposals and call['id'] in decisions and
        call['arguments'] == proposals[call['id']]['args'] == decisions[call['id']]['args']
        for call in calls)
    matched_returns = sum(m['toolCallId'] in returns and text_parts(m) == returns[m['toolCallId']]['text']
                          for m in successes)
    ingested = [e for e in core if e['type'] == 'core_ingest']
    matched_core = sum(any(e['call_id'] == m['toolCallId'] and
        e['raw_sha256'] == hashlib.sha256(text_parts(m).encode()).hexdigest() for e in ingested) for m in successes)
    native_user = [text_parts(m) for m in messages if m.get('role') == 'user']
    users = [e['task'] for e in observed if e['type'] == 'agent_start']
    assistant = [m for m in messages if m.get('role') == 'assistant' and m.get('content')]
    return {'run_id': folder.name,
        'scope': 'main-agent finalized native messages; excludes streaming partials and hidden reasoning',
        'user_task_equal': native_user == users,
        'native_tool_calls': len(calls), 'equal_args_at_plugin_and_decision': matched_args,
        'native_successful_tool_returns': len(successes),
        'equal_successful_returns_at_plugin': matched_returns,
        'equal_successful_returns_at_core_sha256': matched_core,
        'native_error_or_blocked_returns': len(native_returns)-len(successes),
        'native_assistant_messages_with_content': len(assistant),
        'native_assistant_public_text_messages': sum(bool(text_parts(m)) for m in assistant),
        'observed_model_response_payloads': sum('content' in e or 'message' in e or 'text' in e
            for e in observed if e['type'] == 'model_response'),
        'core_ingest_event_types': dict(Counter(e['event_type'] for e in ingested)),
        'audit_event_types': dict(Counter(e['type'] for e in observed)),
        'files_sha256': {name: hashlib.sha256((folder/name).read_bytes()).hexdigest()
            for name in ('pi-events.jsonl', 'audit.jsonl', 'core.jsonl')}}


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('runs', nargs='+', type=Path)
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    result = {'kind': 'historical-read-only-information-flow-audit', 'runs': [audit(p) for p in args.runs]}
    encoded = json.dumps(result, ensure_ascii=False, indent=2)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(encoded+'\n', encoding='utf-8')
    print(encoded)
