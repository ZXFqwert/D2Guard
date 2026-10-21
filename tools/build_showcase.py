"""Builds console/static/showcase.json from recorded runs (no hand-written numbers).

Usage: python tools/build_showcase.py <repo> <console-port>  (the console must be running)."""
import json, sys, urllib.request
from pathlib import Path
repo = Path(sys.argv[1]); port = sys.argv[2]
RUN = '20261019-190141-a0aff9'; SLOW = '20261019-190801-f9c629'; DIL = '20261019-175315-5c1536'
rd = repo / 'runs' / RUN
chain = [json.loads(l) for l in open(rd / 'security_chain.jsonl', encoding='utf-8')]
dec = [json.loads(l) for l in open(rd / 'decisions.jsonl', encoding='utf-8')]
dec = [d for d in dec if d.get('type') == 'decision']
manifest = json.loads((rd / 'manifest.json').read_text(encoding='utf-8'))
ws = rd / 'workspace'
by = {c['seq']: c for c in chain}
sz = lambda c: len(json.dumps(c['state'], ensure_ascii=False).encode())
def s1(seq):
    x = by[seq]['delta']['s1']; p = x['probabilities']
    return {'label': x['label'], 'request': round(p['request'], 3), 'quoted': round(p['quoted'], 3), 'none': round(p['none'], 3), 'latency_ms': round(x.get('latency_ms', 0), 1)}
def d(i):
    x = dec[i]; sd = x['evidence']['security_delta']
    return {'verdict': x['verdict'], 'rule': x['rule_id'], 'risk': x['risk'], 'reason': x['reason'], 'op': sd['op'], 'target': sd['target'],
            'in_scope': sd.get('in_user_granted_scope'), 'request_tainted': sd.get('request_tainted'), 'sensitive': sd.get('sensitive_target')}
anchor = by[5]['delta']['authorization']
readme = (ws / 'README.md').read_text(encoding='utf-8')
steps = [
  {'seq': 5, 'event': '用户下达任务', 'raw': anchor['task_brief'], 'delta': 'USER_GRANT：授权锚点', 'facts': {'读': anchor['read'], '写': anchor['write'], '网络': anchor['net']}, 'state_bytes': sz(by[5])},
  {'seq': 4, 'event': '加载 MCP 工具描述', 'raw': 'mcp://local-docs/project_facts（工具描述）', 'delta': 'UNTRUSTED_OBSERVATION：登记外部来源', 's1': s1(4), 'state_bytes': sz(by[4])},
  {'seq': 20, 'event': 'Agent 计划读取 README.md', 'raw': 'fs_read {"path": "README.md"}', 'delta': 'ACTION_CANDIDATE：规范化动作', 'decision': d(0), 'state_bytes': sz(by[20])},
  {'seq': 25, 'event': 'README.md 内容进入上下文', 'raw': readme, 'delta': 'UNTRUSTED_OBSERVATION：来源级请求标签', 's1': s1(25), 'state_bytes': sz(by[25])},
  {'seq': 40, 'event': 'Agent 计划读取 review.json', 'raw': 'fs_read {"path": "review.json"}', 'delta': 'ACTION_CANDIDATE：规范化动作', 'decision': d(1), 'state_bytes': sz(by[40])},
  {'seq': 45, 'event': 'review.json 内容进入上下文', 'raw': (ws / 'review.json').read_text(encoding='utf-8').strip(), 'delta': 'UNTRUSTED_OBSERVATION：来源级请求标签', 's1': s1(45), 'state_bytes': sz(by[45])},
  {'seq': 61, 'event': 'Agent 计划改写 review.json', 'raw': 'fs_write {"path": "review.json", "content": "{\\"approved\\":true}"}', 'delta': 'ACTION_CANDIDATE：规范化动作＋对齐检查', 'decision': d(2), 'state_bytes': sz(by[61])},
]
def api(p):
    return json.loads(urllib.request.urlopen(f'http://127.0.0.1:{port}{p}').read())
comp = api('/api/compaction/' + RUN); dil = api('/api/compaction/' + DIL)
slow = None
for l in open(repo / 'runs' / SLOW / 'decisions.jsonl', encoding='utf-8'):
    x = json.loads(l)
    if x.get('type') == 'slow_review' and x.get('attribution_status') == 'model_assessed':
        slow = {'run_id': SLOW, 'scenario': json.loads((repo / 'runs' / SLOW / 'manifest.json').read_text(encoding='utf-8'))['scenario'],
                'alignment': x['result']['semantic_alignment'], 'recommended': x['result']['recommended_verdict'],
                'report': x['result']['explainable_report_zh'], 'citations': len(x['result'].get('citations', [])), 'changes_verdict': x.get('changes_verdict')}
        break
out = {'run_id': RUN, 'scenario': manifest['scenario'], 'task': anchor['task_brief'], 'anchor': {'read': anchor['read'], 'write': anchor['write'], 'net': anchor['net']},
       'plan': ['fs_read README.md', 'fs_read review.json', 'fs_write review.json', 'fs_write summary.md'],
       'steps': steps, 'chain_events': len(chain),
       'context_bytes': [r['input_bytes'] for r in comp['requests']], 'state_bytes_max': comp['decision_state_max_bytes'],
       'dilution': {'run_id': DIL, 'scenario': dil['scenario'], 'requests': [{'i': r['i'], 'input': r['input_bytes'], 'state': r['state_bytes']} for r in dil['requests']],
                    'context_min': dil['context_min_bytes'], 'context_max': dil['context_max_bytes'], 'state_max': dil['decision_state_max_bytes']},
       'slow': slow}
(repo / 'console' / 'static' / 'showcase.json').write_text(json.dumps(out, ensure_ascii=False, indent=1) + '\n', encoding='utf-8')
print(json.dumps(out, ensure_ascii=False)[:2500])
