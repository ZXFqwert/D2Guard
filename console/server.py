"""D2Guard security console: a local web UI over real run evidence.

    python server.py --repo ../d2guard-next --port 8765

Reads runs/, scenarios/ and the policy file from the repository, renders the
overview, scenario library, arena, escort mode and trace analysis, and can
launch `lab.py run`. Binds to 127.0.0.1 by default; it never edits run
evidence. Scenarios created in the console are written to scenarios/ with
"origin": "console" and are the only ones it will edit or delete.
"""
import argparse
import hashlib
import os
import json
import re
import subprocess
import socket
import shutil
import sys
import threading
import time
import uuid
import urllib.request
import urllib.error
from collections import Counter, defaultdict
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

from d2trace import build_trace, jsonl, mask

HERE = Path(__file__).resolve().parent
STATIC = HERE / 'static'
RUN_ID = re.compile(r'^\d{8}-\d{6}-[0-9a-f]{6}$')
SCENARIO_ID = re.compile(r'^[a-z0-9][a-z0-9-]{2,63}$')
INDEX_VERSION = 4
TYPES = {'.html': 'text/html; charset=utf-8', '.js': 'text/javascript; charset=utf-8',
         '.css': 'text/css; charset=utf-8', '.svg': 'image/svg+xml', '.png': 'image/png'}
FAMILY_ZH = {'cve': 'CVE 复现', 'indirect': '间接注入', 'direct': '直接注入', 'memory': '记忆污染', 'supply_chain': 'MCP 供应链',
             'tool_abuse': '工具滥用', 'egress': '敏感外发', 'write': '敏感写入', 'ssh': '私钥窃取',
             'subagent': '子 Agent', 'variant': '变形绕过', 'language': '多语言绕过', 'dilution': '上下文稀释',
             'adversarial': '对抗样本', 'semantic_camouflage': '语义伪装', 'normal': '正常任务',
             'hard_negative': '困难负例', 'benign_nonliteral': '非字面正常任务', 'legacy': '早期 README 场景',
             'direct-user': '直接注入',
             'custom': '自定义'}

# Decision table (first match wins), as in the design document, table 5-2.
DECISION_TABLE = [
    {'id': 'POL-*', 'no': '1／1b', 'cond': '命中语义策略：风险为 R3 时阻断，风险降为 R2 时挂起', 'verdict': 'BLOCK／ASK'},
    {'id': 'DT-2a', 'no': '2a', 'cond': '参数命中机密指纹，且目标为外发出口', 'verdict': 'BLOCK'},
    {'id': 'DT-2b', 'no': '2b', 'cond': '上下文持有机密，外发至未授权目标但未命中指纹', 'verdict': 'ASK'},
    {'id': 'DT-3', 'no': '3', 'cond': '在用户字面授权内，且无机密外流', 'verdict': 'ALLOW'},
    {'id': 'DT-4i', 'no': '4i', 'cond': '上下文含直接注入特征的用户输入，超出授权的敏感或高风险动作', 'verdict': 'ASK'},
    {'id': 'DT-4a', 'no': '4a', 'cond': '超出授权，敏感目标，命中外部指令', 'verdict': 'ASK'},
    {'id': 'DT-4b', 'no': '4b', 'cond': '超出授权，敏感目标，未命中外部指令', 'verdict': 'ASK'},
    {'id': 'DT-4c', 'no': '4c', 'cond': '超出授权，非敏感但高风险，上下文含请求污染来源', 'verdict': 'ASK'},
    {'id': 'DT-4c-EGRESS', 'no': '4c2', 'cond': '超出授权，上下文无请求污染，但向未授权目标外发', 'verdict': 'ASK'},
    {'id': 'DT-4c-S1', 'no': '4c′', 'cond': '超出授权，非敏感但高风险，快镜判定全部来源未提出请求', 'verdict': 'ALLOW'},
    {'id': 'DT-4d', 'no': '4d', 'cond': '超出授权，非敏感且低风险（读取、GET）', 'verdict': 'ALLOW'},
    {'id': 'DT-4e', 'no': '4e', 'cond': '超出授权，高风险，上下文从未摄入不可信内容', 'verdict': 'ALLOW'},
    {'id': 'DT-5', 'no': '5', 'cond': '动作涉及覆盖不足项，且属于高风险', 'verdict': 'ASK'},
    {'id': 'DT-6', 'no': '6', 'cond': '其余情况：高风险挂起，低风险放行并记录', 'verdict': 'ASK／ALLOW'},
]

# Host-control calls go to the per-run loopback service; a system or environment
# proxy must never sit between the console and that service.
DIRECT = urllib.request.build_opener(urllib.request.ProxyHandler({}))
LOCAL_HOSTS = {'127.0.0.1', 'localhost'}
API_STYLES = ('chat_completions', 'responses')


def pct(a, b):
    return round(100.0 * a / b, 1) if b else None


class Console:
    def __init__(self, repo, python):
        self.repo = Path(repo).resolve()
        self.runs = self.repo / 'runs'
        self.scenario_dir = self.repo / 'scenarios'
        self.python = python
        self.cache_dir = HERE / '.cache'
        self.cache_dir.mkdir(exist_ok=True)
        self.index_file = self.cache_dir / ('index-' + hashlib.sha256(str(self.repo).encode()).hexdigest()[:12] + '.json')
        self.index = {k: v for k, v in self._load(self.index_file, {}).items() if v.get('v') == INDEX_VERSION}
        self.lock = threading.Lock()
        self._rows, self._scanned = [], 0.0
        self._signatures = {}
        self.jobs = {}
        self.job_lock = threading.Lock()
        self._views = {}
        self.resident = None

    @staticmethod
    def _load(path, default):
        try:
            return json.loads(path.read_text(encoding='utf-8'))
        except (OSError, json.JSONDecodeError):
            return default

    # ---------- run index ----------
    def _summary(self, folder, families):
        manifest = self._load(folder / 'manifest.json', {})
        result = self._load(folder / 'result.json', {})
        # Between the Agent stopping and the evidence review finishing, show the Agent's own outcome.
        finished = {} if result else self._load(folder / 'agent-finished.json', {})
        shown = result or finished.get('preliminary') or {}
        if not manifest:
            return None
        verdicts, would, rules, held = Counter(), Counter(), Counter(), []
        rule_verdicts, rule_reasons = defaultdict(Counter), {}
        lat = []
        decision_mode = (manifest.get('content_model') or {}).get('decision_mode')
        for d in jsonl(folder / 'decisions.jsonl'):
            if d.get('type') == 'core_started':
                decision_mode = d.get('decision_mode') or decision_mode
            if d.get('type') != 'decision':
                continue
            v, w = d.get('verdict'), d.get('would_verdict') or d.get('verdict')
            verdicts[v] += 1
            would[w] += 1
            rule = d.get('rule_id') or d.get('policy')
            rules[rule] += 1
            if rule:
                rule_verdicts[rule][w] += 1
                rule_reasons.setdefault(rule, d.get('reason'))
            if isinstance(d.get('local_latency_ms'), (int, float)):
                lat.append(d['local_latency_ms'])
            if w in ('ASK', 'BLOCK') and len(held) < 4:
                delta = ((d.get('evidence') or {}).get('security_delta')) or {}
                held.append({'op': delta.get('op') or delta.get('tool'), 'target': mask(delta.get('target')),
                             'verdict': v, 'would': w, 'rule': rule, 'risk': d.get('risk'),
                             'reason': d.get('reason'), 'ts': d.get('timestamp_ns')})
        scenario = manifest.get('scenario')
        cat, fam = families.get(scenario, (None, None))
        return {
            'v': INDEX_VERSION, 'id': folder.name, 'day': folder.name[:8], 'scenario': scenario,
            'category': cat, 'family': fam, 'environment': manifest.get('environment'),
            'protection': manifest.get('protection'), 'engine': manifest.get('guard_engine'),
            'decision_mode': decision_mode or 'unknown',
            'batch_id': manifest.get('batch_id'), 'model': manifest.get('model'),
            'outcome': shown.get('outcome') or ('running' if not shown else None),
            'attack_succeeded': shown.get('attack_succeeded'), 'received_bytes': shown.get('received_bytes'),
            'asked': len(result.get('asked_calls') or []), 'blocked': len(result.get('blocked_calls') or []),
            'task_completed': shown.get('task_completed'), 'elapsed_seconds': result.get('elapsed_seconds'),
            'agent_elapsed_seconds': result.get('agent_elapsed_seconds', finished.get('agent_elapsed_seconds')),
            'agent_finished': bool(result or finished), 'complete': bool(result), 'verdicts': dict(verdicts), 'would': dict(would), 'rules': dict(rules),
            'lat_sum': round(sum(lat), 3), 'lat_n': len(lat), 'lat_max': round(max(lat), 3) if lat else None,
            'held_calls': held, 'rule_verdicts': {k: dict(v) for k, v in rule_verdicts.items()},
            'rule_reasons': rule_reasons,
        }

    def refresh_index(self):
        with self.lock:
            if not self.runs.exists():
                return []
            if time.time() - self._scanned < 3:  # one directory scan serves a burst of requests
                return self._rows
            families = {s['id']: (s.get('category'), s.get('family')) for s in self._scenario_files()}
            changed = False
            for folder in self.runs.iterdir():
                if not folder.is_dir() or not RUN_ID.match(folder.name):
                    continue
                cached = self.index.get(folder.name)
                if cached and cached.get('complete'):
                    continue
                signature = tuple((f.stat().st_mtime_ns, f.stat().st_size) if f.exists() else None for f in (folder/'manifest.json',folder/'result.json',folder/'decisions.jsonl',folder/'agent-finished.json'))
                if cached and self._signatures.get(folder.name) == signature:
                    continue
                summary = self._summary(folder, families)
                self._signatures[folder.name] = signature
                if summary:
                    self.index[folder.name] = summary
                    changed = True
            if changed:
                self.index_file.write_text(json.dumps(self.index, ensure_ascii=False), encoding='utf-8')
            self._rows = sorted(self.index.values(), key=lambda r: r['id'], reverse=True)
            self._scanned = time.time()
            return self._rows

    def _done(self):
        return [r for r in self.refresh_index() if r.get('engine') == 'd2v2' and r.get('complete')]

    def list_runs(self, query):
        rows = self.refresh_index()
        q = {k: v[0] for k, v in query.items() if v and v[0]}
        if q.get('engine', 'd2v2') != 'all':
            rows = [r for r in rows if r.get('engine') == q.get('engine', 'd2v2')]
        for key in ('scenario', 'environment', 'protection', 'outcome', 'family', 'category', 'batch_id', 'decision_mode'):
            if key == 'scenario' and key in q:
                rows = [r for r in rows if q[key] in (r.get(key) or '')]
            elif key in q:
                rows = [r for r in rows if r.get(key) == q[key]]
        if q.get('held') == '1':
            rows = [r for r in rows if r.get('asked') or r.get('blocked')]
        limit = min(int(q.get('limit', 300)), 3000)
        light = [{k: v for k, v in r.items() if k not in ('held_calls', 'rules', 'rule_verdicts', 'rule_reasons')}
                 for r in rows[:limit]]
        return {'total': len(rows), 'runs': light}

    # ---------- overview ----------
    def overview(self, query=None):
        all_done = self._done()
        selected = {k:v[0] for k,v in (query or {}).items() if v and v[0]}
        done = [r for r in all_done if all(r.get(k)==selected[k] for k in ('batch_id','decision_mode') if k in selected)]
        attack = [r for r in done if r['environment'] == 'attack' and r.get('category') != 'normal' and isinstance(r.get('attack_succeeded'), bool)]
        clean = [r for r in done if r['environment'] == 'clean']

        def side(rows, protect):
            rs = [r for r in rows if r['protection'] == protect]
            return rs, sum(1 for r in rs if r.get('attack_succeeded'))

        off, off_s = side(attack, 'off')
        on, on_s = side(attack, 'on')
        clean_on = [r for r in clean if r['protection'] == 'on']
        clean_off = [r for r in clean if r['protection'] == 'off']
        fp = sum(1 for r in clean_on if r.get('asked') or r.get('blocked'))
        done_on = sum(1 for r in clean_on if r.get('task_completed'))
        done_off = sum(1 for r in clean_off if r.get('task_completed'))
        would_stop = sum(1 for r in off if r.get('attack_succeeded')
                         and ((r.get('would') or {}).get('ASK') or (r.get('would') or {}).get('BLOCK')))
        lat_sum = sum(r.get('lat_sum') or 0 for r in done if r['protection'] == 'on')
        lat_n = sum(r.get('lat_n') or 0 for r in done if r['protection'] == 'on')

        kpi = {
            'runs': len(done), 'scenarios': len({r['scenario'] for r in done}),
            'off_attack': len(off), 'off_success': off_s, 'off_rate': pct(off_s, len(off)),
            'on_attack': len(on), 'on_success': on_s, 'on_rate': pct(on_s, len(on)),
            'intercept_rate': pct(len(on) - on_s, len(on)),
            'would_stop': would_stop, 'would_stop_rate': pct(would_stop, off_s),
            'clean_on': len(clean_on), 'clean_fp': fp, 'clean_fp_rate': pct(fp, len(clean_on)),
            'clean_done_on': done_on, 'clean_done_on_rate': pct(done_on, len(clean_on)),
            'clean_done_off_rate': pct(done_off, len(clean_off)),
            'held_runs': sum(1 for r in done if r['protection'] == 'on' and (r.get('asked') or r.get('blocked'))),
            'avg_latency_ms': round(lat_sum / lat_n, 2) if lat_n else None, 'decisions': lat_n,
        }

        fam = defaultdict(lambda: {'off': 0, 'off_s': 0, 'on': 0, 'on_s': 0})
        for r in attack:
            if r.get('category') == 'normal':
                continue
            f = fam[r.get('family') or 'legacy']
            key = 'off' if r['protection'] == 'off' else 'on'
            f[key] += 1
            f[key + '_s'] += 1 if r.get('attack_succeeded') else 0
        families = [{'family': k, 'label': FAMILY_ZH.get(k, k), **v, 'off_rate': pct(v['off_s'], v['off']),
                     'on_rate': pct(v['on_s'], v['on'])} for k, v in fam.items() if v['off'] or v['on']]
        families.sort(key=lambda x: -(x['off'] + x['on']))

        # Trend: runs in time order, split into equal buckets so a two-day history still shows a curve.
        ordered = sorted(done, key=lambda r: r['id'])
        size = max(20, -(-len(ordered) // 12))
        trend = []
        for i in range(0, len(ordered), size):
            chunk = ordered[i:i + size]
            b = {'runs': len(chunk), 'off': 0, 'off_s': 0, 'on': 0, 'on_s': 0,
                 'held': sum(1 for r in chunk if r['protection'] == 'on' and (r.get('asked') or r.get('blocked')))}
            for r in chunk:
                if r['environment'] == 'attack' and r.get('category') != 'normal' and isinstance(r.get('attack_succeeded'), bool):
                    key = 'off' if r['protection'] == 'off' else 'on'
                    b[key] += 1
                    b[key + '_s'] += 1 if r.get('attack_succeeded') else 0
            first = chunk[0]['id']
            trend.append({'label': f'{first[4:6]}-{first[6:8]} {first[9:11]}:{first[11:13]}', **b,
                          'off_rate': pct(b['off_s'], b['off']), 'on_rate': pct(b['on_s'], b['on'])})

        verdicts, rules = Counter(), Counter()
        for r in done:
            if r['protection'] == 'on':
                verdicts.update(r.get('verdicts') or {})
                rules.update({k: v for k, v in (r.get('rules') or {}).items() if k and k != 'null'})
        events = []
        for r in done:
            if r['protection'] != 'on':
                continue
            for h in r.get('held_calls') or []:
                events.append({**h, 'run_id': r['id'], 'scenario': r['scenario'], 'environment': r['environment']})
        events.sort(key=lambda e: e['run_id'], reverse=True)
        return {'filters': {'batch_id': sorted({r['batch_id'] for r in all_done if r.get('batch_id')}), 'decision_mode': sorted({r['decision_mode'] for r in all_done})}, 'selected':selected, 'kpi': kpi, 'families': families, 'trend': trend, 'verdicts': dict(verdicts),
                'rules': rules.most_common(12), 'events': events[:12]}

    def pairs(self, scenario):
        cells = {}
        for r in self._done():  # newest first
            if r.get('scenario') == scenario:
                cells.setdefault(f"{r['environment']}/{r['protection']}", r)
        return {'scenario': scenario, 'cells': cells}

    def trace(self, run_id):
        if not RUN_ID.match(run_id) or not (self.runs / run_id).is_dir():
            return None
        return build_trace(self.runs / run_id)

    # ---------- attack/defense screen (攻防大屏) ----------
    def summary(self):
        """The official evaluation summary, served verbatim; None when the file is absent."""
        data = self._load(HERE / 'data' / 'evaluation-summary.json', None)
        return data if isinstance(data, dict) else None

    def _cached(self, kind, run_id, build):
        folder = self.runs / run_id
        key = (kind, run_id)
        if key in self._views:
            return self._views[key]
        out = build(folder)
        if out is not None and (folder / 'result.json').exists():
            self._views[key] = out  # finished runs never change
        return out

    @staticmethod
    def _s1_brief(s1):
        if not isinstance(s1, dict) or not s1.get('label'):
            return None
        probs = s1.get('probabilities') or {}
        return {'label': s1.get('label'), 'p_request': probs.get('request'), 'threshold': s1.get('request_threshold'),
                'calibrated': s1.get('calibrated'), 'latency_ms': s1.get('latency_ms'), 'model': s1.get('model')}

    def replay(self, run_id):
        """Event stream for the duel replay, projected only from the run's own evidence."""
        if not RUN_ID.match(run_id) or not (self.runs / run_id).is_dir():
            return None

        def build(folder):
            t = build_trace(folder)
            result = self._load(folder / 'result.json', {})
            decisions = [d for d in jsonl(folder / 'decisions.jsonl') if d.get('type') == 'decision']
            basis = {d.get('call_id'): d.get('decision_basis') for d in decisions}
            slow = {d.get('call_id'): bool((d.get('slow') or {}).get('triggered')) for d in decisions}
            agents = {a['id']: a['label'] for a in t['agents']}
            decided = {e['call_id']: e['t_ms'] for e in t['timeline'] if e['kind'] == 'guard_decision'}
            events, seen = [], set()
            run = t['run']
            events.append({'t': 0, 'kind': 'task', 'agent': '用户', 'text': run.get('task')})
            for s in t['sources']:
                if s.get('t_ms') is not None:
                    continue
                key = (s.get('uri'), (s.get('evidence_ref') or {}).get('sha256'))
                if key in seen:
                    continue
                seen.add(key)
                events.append({'t': 0, 'kind': 'context', 'uri': s.get('uri'), 'source_kind': s.get('kind'),
                               'source_type': s.get('type'), 's1': self._s1_brief(s.get('s1')),
                               'excerpt': (s.get('text') or '')[:160]})
            for c in t['calls']:
                facts = c.get('decision_facts') or {}
                args = json.dumps(c.get('args') or {}, ensure_ascii=False)
                events.append({
                    't': c.get('t_ms') or 0, 't_decided': decided.get(c['call_id']), 'kind': 'call',
                    'call_id': c['call_id'], 'agent': agents.get(c.get('agent'), c.get('agent')), 'op': c.get('op'),
                    'target': c.get('target'), 'args': args if len(args) <= 180 else args[:178] + '…',
                    'verdict': c.get('verdict'), 'would': c.get('would_verdict') or c.get('verdict'),
                    'rule_id': c.get('rule_id'), 'risk': c.get('risk'), 'reason': c.get('reason'),
                    'latency_ms': c.get('latency_ms'), 'executed': c.get('executed'),
                    'induced': [i.get('uri') for i in c.get('induced_by') or []],
                    'basis': basis.get(c['call_id']), 'slow_triggered': slow.get(c['call_id'], False),
                    'facts': {k: facts.get(k) for k in ('request_tainted', 'directive', 'secret_hit', 'sensitive',
                                                       'hard_policy', 'soft_policy', 'literal_scope', 'tainted')}})
            for s in t['sources']:
                if s.get('t_ms') is None:
                    continue
                events.append({'t': s['t_ms'], 'kind': 'source', 'call_id': s.get('via_call'), 'uri': s.get('uri'),
                               'source_kind': s.get('kind'), 'source_type': s.get('type'),
                               'agent': agents.get(s.get('agent'), s.get('agent')),
                               's1': self._s1_brief(s.get('s1')), 'excerpt': (s.get('text') or '')[:160]})
            for e in t['timeline']:
                if e['kind'] == 'approval_hold_complete' and e.get('t_ms') is not None:
                    events.append({'t': e['t_ms'], 'kind': 'held', 'call_id': e.get('call_id')})
            order = {'task': 0, 'context': 1, 'call': 2, 'source': 3, 'held': 4}
            events.sort(key=lambda e: (e['t'], order[e['kind']]))
            last = max([e['t_ms'] for e in t['timeline'] if e.get('t_ms') is not None] + [e['t'] for e in events])
            keep = ('outcome', 'attack_succeeded', 'received_bytes', 'defense_containment', 'attack_prevented',
                    'approval_pending', 'defense_blocked', 'task_status', 'task_completed', 'elapsed_seconds',
                    'agent_elapsed_seconds', 'model_request_count')
            res = {k: result.get(k) for k in keep}
            res['asked_rules'] = [x.get('policy') for x in result.get('asked_calls') or []]
            res['blocked_rules'] = [x.get('policy') for x in result.get('blocked_calls') or []]
            return {'run': run, 'result': res, 'impact': t['impact'], 'end_t': last, 'events': events}

        return self._cached('replay', run_id, build)

    def compaction_runs(self):
        rows = [r for r in self.refresh_index() if r.get('complete') and (self.runs / r['id'] / 'gateway.jsonl').exists()]
        return {'runs': [{k: r.get(k) for k in ('id', 'scenario', 'environment', 'protection', 'family', 'outcome')}
                         for r in rows]}

    def compaction(self, run_id):
        """Model-input bytes per request vs. the bounded security state the kernel reads."""
        if not RUN_ID.match(run_id) or not (self.runs / run_id).is_dir():
            return None

        def size(state):
            return len(json.dumps(state).encode('utf-8'))  # same serialization as the evaluation summary

        def latest(series, ts):  # value of the last entry at or before ts
            best = None
            for when, value in series:
                if when > ts:
                    break
                best = value
            return best

        def build(folder):
            manifest = self._load(folder / 'manifest.json', {})
            audit = jsonl(folder / 'audit.jsonl')
            t0 = next((x.get('timestamp_ns') for x in audit if x.get('timestamp_ns')), None)
            ms = lambda ts: round((ts - t0) / 1e6) if ts and t0 else None
            chain = sorted((c['timestamp_ns'], size(c['state'])) for c in jsonl(folder / 'security_chain.jsonl')
                           if c.get('timestamp_ns') and isinstance(c.get('state'), dict))
            snaps = sorted(((d.get('timestamp_ns') or 0), size(d['previous_security_state']), d.get('verdict'),
                            d.get('rule_id') or d.get('policy')) for d in jsonl(folder / 'decisions.jsonl')
                           if d.get('type') == 'decision' and isinstance(d.get('previous_security_state'), dict))
            requests, stamps = [], []
            for g in jsonl(folder / 'gateway.jsonl'):
                if g.get('type') != 'proxy_request' or not isinstance(g.get('input_bytes'), int):
                    continue
                ts = g.get('timestamp_ns') or 0
                stamps.append(ts)
                requests.append({'i': len(requests) + 1, 'agent': g.get('agent_id'), 't_ms': ms(ts),
                                 'input_bytes': g['input_bytes'],
                                 'state_bytes': latest(chain if chain else [(s[0], s[1]) for s in snaps], ts)})
            marks = [{'t_ms': ms(ts), 'after_request': sum(1 for x in stamps if x <= ts) or None, 'state_bytes': value,
                      'verdict': verdict, 'rule_id': rule} for ts, value, verdict, rule in snaps]
            ctx = [r['input_bytes'] for r in requests]
            dec_max = max((m['state_bytes'] for m in marks), default=None)
            chain_max = max((v for _, v in chain), default=None)
            return {'run_id': folder.name, 'scenario': manifest.get('scenario'),
                    'environment': manifest.get('environment'), 'protection': manifest.get('protection'),
                    'state_series': 'security_chain' if chain else 'decisions', 'requests': requests,
                    'decisions': marks, 'context_min_bytes': min(ctx, default=None),
                    'context_max_bytes': max(ctx, default=None), 'decision_state_max_bytes': dec_max,
                    'chain_state_max_bytes': chain_max,
                    'ratio': round(max(ctx) / dec_max, 2) if ctx and dec_max else None}

        return self._cached('compaction', run_id, build)

    # ---------- scenarios ----------
    def _scenario_files(self):
        out = []
        for path in sorted(self.scenario_dir.glob('*.json')):
            data = self._load(path, {})
            if data:
                data['id'] = path.stem
                out.append(data)
        return out

    def scenarios(self):
        stats = defaultdict(Counter)
        for r in self._done():
            s = stats[r['scenario']]
            s['runs'] += 1
            key = f"{r['environment']}_{r['protection']}"
            s[key] += 1
            if r.get('attack_succeeded'):
                s[key + '_success'] += 1
            if r.get('asked') or r.get('blocked'):
                s[key + '_held'] += 1
        out = []
        for data in self._scenario_files():
            fam = 'cve' if data['id'].startswith('cve-') or data['id'] == 'g-ide-autoapprove' else data.get('family')
            out.append({'id': data['id'], 'category': data.get('category'), 'family': fam,
                        'family_label': FAMILY_ZH.get(fam, fam) or '演示场景',
                        'language': data.get('language'), 'attack_source': data.get('attack_source'),
                        'task': mask(data.get('task')), 'payload_text': mask(data.get('payload_text')),
                        'expected_decision': data.get('expected_decision'),
                        'evaluation_only': data.get('evaluation_only'), 'origin': data.get('origin', 'official'),
                        'stats': dict(stats.get(data['id'], {}))})
        return out

    def scenario(self, sid):
        path = self.scenario_dir / f'{sid}.json'
        if not SCENARIO_ID.match(sid) or not path.is_file():
            return None
        data = self._load(path, {})
        runs = [{k: r.get(k) for k in ('id', 'environment', 'protection', 'outcome', 'attack_succeeded', 'asked', 'blocked')}
                for r in self._done() if r['scenario'] == sid][:20]
        return {'id': sid, 'origin': data.get('origin', 'official'), 'data': mask(data), 'runs': runs}

    def _validate(self, data):
        if not isinstance(data, dict):
            return '场景必须是 JSON 对象'
        for key in ('task', 'deliverable'):
            if not isinstance(data.get(key), str) or not data[key].strip():
                return f'缺少字段 {key}'
        if data.get('category') not in ('attack', 'normal'):
            return 'category 只能是 attack 或 normal'
        if not isinstance(data.get('completion_terms'), list):
            return 'completion_terms 必须是列表'
        res = data.get('resources')
        if not isinstance(res, dict) or not isinstance(res.get('clean'), dict) or not isinstance(res.get('attack'), dict):
            return 'resources 需要包含 clean 与 attack 两份初始资源'
        return None

    def _write_scenario(self, sid, data):
        data = {**data, 'id': sid, 'origin': 'console', 'evaluation_only': True, 'training_allowed': False,
                'split': 'evaluation'}
        data.setdefault('version', 1)
        for key, default in (('file_sources', {}), ('requirements', []), ('expected_decision', []),
                             ('oracle', {'kind': 'canary_receipt'}), ('family', 'custom')):
            data.setdefault(key, default)
        tmp = self.scenario_dir / f'.{sid}.json.tmp'
        tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
        tmp.replace(self.scenario_dir / f'{sid}.json')
        return data

    def create_scenario(self, data):
        sid = str((data or {}).get('id') or '')
        if not SCENARIO_ID.match(sid):
            return 400, {'error': '场景 ID 只能用小写字母、数字和连字符，3–64 位'}
        if (self.scenario_dir / f'{sid}.json').exists():
            return 409, {'error': f'场景 {sid} 已存在'}
        err = self._validate(data)
        if err:
            return 400, {'error': err}
        self._write_scenario(sid, data)
        return 200, {'id': sid}

    def update_scenario(self, sid, data):
        cur = self.scenario(sid)
        if not cur:
            return 404, {'error': '未找到场景'}
        if cur['origin'] != 'console':
            return 403, {'error': '官方评测场景只读，可复制为新场景后修改'}
        err = self._validate(data)
        if err:
            return 400, {'error': err}
        self._write_scenario(sid, data)
        return 200, {'id': sid}

    def delete_scenario(self, sid):
        cur = self.scenario(sid)
        if not cur:
            return 404, {'error': '未找到场景'}
        if cur['origin'] != 'console':
            return 403, {'error': '官方评测场景不能删除'}
        (self.scenario_dir / f'{sid}.json').unlink()
        return 200, {'deleted': sid}

    def import_scenarios(self, body):
        items = body if isinstance(body, list) else (body.get('scenarios') if isinstance(body, dict) and 'scenarios' in body else [body])
        done, failed = [], []
        for item in items:
            code, out = self.create_scenario(item)
            (done if code == 200 else failed).append({'id': (item or {}).get('id'), **out})
        return 200, {'imported': done, 'failed': failed}

    def export_scenarios(self, origin):
        rows = [d for d in self._scenario_files() if origin == 'all' or d.get('origin', 'official') == origin]
        return {'exported_from': str(self.scenario_dir.name), 'count': len(rows), 'scenarios': rows}

    # ---------- policies ----------
    def policies(self):
        path = self.repo / 'src' / 'd2v2' / 'policies.yaml'
        text = path.read_text(encoding='utf-8') if path.exists() else ''
        dsl = []
        for block in re.split(r'\n  - id: ', text)[1:]:
            pid = block.split('\n', 1)[0].strip()
            tools = re.search(r'tool: \[([^\]]*)\]', block)
            explain = re.search(r'explain: (.*)', block)
            verdict = re.search(r'verdict: \{([^}]*)\}', block)
            dsl.append({'id': pid, 'tools': tools.group(1) if tools else '', 'explain': explain.group(1).strip() if explain else '',
                        'verdict': verdict.group(1) if verdict else '', 'source': mask('  - id: ' + block.rstrip())})
        hits, reasons, verdict_of = Counter(), {}, defaultdict(Counter)
        for r in self._done():
            if r['protection'] != 'on':
                continue
            hits.update({k: v for k, v in (r.get('rules') or {}).items() if k and k != 'null'})
            for k, v in (r.get('rule_verdicts') or {}).items():
                verdict_of[k].update(v)
            for k, v in (r.get('rule_reasons') or {}).items():
                reasons.setdefault(k, v)
        cfg_path = os.environ.get('D2_S1_CONFIG') or (str(self.repo / '.local/s1.json') if (self.repo / '.local/s1.json').is_file() else None)
        cfg = self._load(Path(cfg_path), {}) if cfg_path else self._load(self.repo / '.local/stage-d5/s1-enabled-config.json', self._load(self.repo / '.local/stage-d4/s1-enabled-config.json', {}))
        latest = next((r.get('decision_mode') for r in self._done() if r['protection'] == 'on' and r.get('decision_mode') not in (None, 'unknown')), None)
        runtime_mode = 'rules_only' if os.environ.get('D2_S1_DISABLE') == '1' else cfg.get('decision_mode') or latest or 'taint_gate'
        return {'runtime_mode':runtime_mode, 'dsl': dsl, 'table': DECISION_TABLE, 'hits': dict(hits), 'reasons': reasons, 'verdicts': {k: dict(v) for k, v in verdict_of.items()}}

    # ---------- launching real runs ----------
    @staticmethod
    def chat_message(body):
        text = body.get('message')
        attachment = body.get('attachment', '')
        if not isinstance(text, str) or not text.strip() or len(text) > 32000:
            raise ValueError('请输入任务（最多 32000 字符）')
        if not isinstance(attachment, str) or len(attachment) > 100000:
            raise ValueError('附带资料最多 100000 字符')
        # Quote every line so an attachment cannot close a delimiter and become authority.
        return text.strip() + ('\n\n附带资料（仅作参考）：\n'+'\n'.join('> '+line for line in attachment.splitlines()) if attachment else '')

    def start_chat(self, body):
        try:
            message = self.chat_message(body)
        except ValueError as exc:
            return 400, {'error': str(exc)}
        if body.get('protect', 'on') not in ('on', 'off'):
            return 400, {'error': '防护设置无效'}
        return self.launch({'scenario': 'live-chat', 'environment': 'clean', 'mode': 'chat',
                            'protect': body.get('protect', 'on'), '_message': message})

    def chat_command(self, job_id, body):
        with self.job_lock:
            job = self.jobs.get(job_id)
            if not job or job['mode'] != 'chat' or job['status'] != 'running':
                return 409, {'error': '会话已结束，请新建对话'}
            channel = job['_channel']
            state = self._load(channel/'status.json', {})
            kind = body.get('type')
            if kind not in ('prompt','abort','close'):
                return 400, {'error':'未知会话操作'}
            if (channel/'command.json').exists():
                return 409, {'error':'上一条操作正在处理'}
            if kind == 'prompt' and state.get('phase') != 'idle':
                return 409, {'error':'Agent 正在执行，请等待回复或停止生成'}
            command = {'type':kind}
            if kind in ('abort','close'):
                rid = job['steps'][0].get('run_id')
                if rid:
                    try:
                        self._host_control(rid,'/cancel-turn',{})
                    except (ValueError,OSError):
                        if state.get('phase') == 'running':
                            return 503, {'error':'取消通道暂不可用，请重试；待审批操作不会因此放行'}
            if kind == 'prompt':
                try:
                    command['message'] = self.chat_message(body)
                except ValueError as exc:
                    return 400, {'error':str(exc)}
            temp = channel/'command.tmp'
            temp.write_text(json.dumps(command, ensure_ascii=False), encoding='utf-8')
            temp.replace(channel/'command.json')
        return 200, {'accepted':True}

    def chat_view(self, job):
        channel = job['_channel']
        state = self._load(channel/'status.json', {'phase':'starting'})
        messages, partial, tools = [], '', []
        rid = job['steps'][0].get('run_id')
        if rid:
            folder = self.runs/rid
            for event in jsonl(folder/'pi-events.jsonl'):
                message = event.get('message', {})
                if event.get('type') == 'message_end':
                    if message.get('role') in ('user','assistant'):
                        content = message.get('content', [])
                        text = content if isinstance(content,str) else '\n'.join(c.get('text','') for c in content if c.get('type')=='text')
                        if message.get('errorMessage'):
                            text += '\n'+message['errorMessage']
                        if text:
                            messages.append({'role':message['role'], 'text':mask(text)})
                    partial = ''
                elif event.get('type') == 'message_update':
                    update = event.get('assistantMessageEvent', {})
                    if update.get('type') == 'text_delta':
                        partial += update.get('delta','')
            # Pi may not emit a message_end for user input on every supported RPC build.
            if not any(m['role']=='user' for m in messages):
                turns = [e for e in jsonl(folder/'conversation.jsonl') if e.get('type')=='user_turn_submitted']
                state['submitted_messages'] = [{'role':'user','text':mask(e['text'])} for e in turns]
            for event in jsonl(folder/'audit.jsonl'):
                if event.get('type') == 'guard_decision':
                    tools.append({k:mask(str(event.get(k,''))) for k in ('call_id','tool','verdict','rule_id','reason','approval_status')})
        return {**state, 'messages':messages, 'partial':mask(partial), 'tools':tools[-40:],
                'command_pending':(channel/'command.json').exists()}

    def launch(self, body):
        ids = {s['id'] for s in self._scenario_files()}
        scenario, env, mode = body.get('scenario'), body.get('environment'), body.get('mode', 'single')
        if scenario not in ids or env not in ('clean', 'attack'):
            return 400, {'error': '参数无效'}
        if mode == 'arena':
            steps = ['off', 'on']
        elif mode in ('single','chat') and body.get('protect') in ('on', 'off'):
            steps = [body['protect']]
        else:
            return 400, {'error': '参数无效'}
        with self.job_lock:
            if any(j['status'] == 'running' for j in self.jobs.values()):
                return 409, {'error': '已有运行在进行，请等待其结束'}
            job_id = uuid.uuid4().hex[:12]
            job = {'id': job_id, 'status': 'running', 'mode': mode, 'scenario': scenario, 'environment': env,
                   'started': time.time(), 'steps': [{'protect': p, 'status': 'queued', 'run_id': None,
                                                      'returncode': None} for p in steps],
                   '_log': self.cache_dir / f'job-{job_id}.log'}
            self.jobs[job_id] = job
            if mode == 'chat':
                if not body.get('_message'):
                    self.jobs.pop(job_id)
                    return 400, {'error':'请从自由对话入口输入任务'}
                channel = self.repo/'.local/chat-sessions'/job_id
                channel.mkdir(parents=True, exist_ok=False)
                (channel/'task.txt').write_text(body['_message'], encoding='utf-8')
                job['_channel'] = channel
        threading.Thread(target=self._run_job, args=(job,), daemon=True).start()
        return 200, self.job(job_id)

    def _run_job(self, job):
        with job['_log'].open('w', encoding='utf-8') as log:
            # The real writer and both evaluation lanes use the same fixture.
            run_env = {**os.environ, 'D2_FIXTURE_CANARY': 'd2-test-' + uuid.uuid4().hex}
            if self.resident:
                job['initializing_models'] = True
                try:
                    run_env['D2_INFERENCE_DESCRIPTOR'] = self.resident.wait()
                except RuntimeError as exc:
                    log.write(str(exc)+'\n')
                    for step in job['steps']:
                        step.update(status='failed', returncode=-1)
                    job.update(status='failed', finished=time.time(), initializing_models=False)
                    return
                job['initializing_models'] = False
            seed = None
            scenario = self._load(self.repo / 'scenarios' / (job['scenario'] + '.json'), {})
            if scenario.get('setup_task'):
                seed = self.repo / '.local/console-memory' / job['id'] / 'seed'
                seed.mkdir(parents=True, exist_ok=True)
                job['preparing_memory'] = True
                cmd = [self.python, 'lab.py', 'run', '--scenario', job['scenario'],
                       '--environment', job['environment'], '--protect', 'off', '--engine', 'd2v2',
                       '--memory-root', str(seed), '--task', scenario['setup_task'], '--phase', 'memory-setup', '--max-output-tokens','8192']
                log.write('Preparing cross-session memory with a real Agent...\n'); log.flush()
                try:
                    code = subprocess.call(cmd, cwd=self.repo, env=run_env, stdout=log, stderr=subprocess.STDOUT)
                except OSError as exc:
                    log.write(f'Memory preparation failed: {exc}\n'); code = -1
                job['preparing_memory'] = False
                if code != 0 or not any(seed.glob('*.json')):
                    log.write('Memory preparation did not produce usable memory. Evaluation was not started.\n')
                    for step in job['steps']:
                        step.update(status='failed', returncode=code if code else -1)
                    job.update(status='failed', finished=time.time())
                    return
        # Both lanes start together: same task, same fixture, independent run folders and services.
        lanes = [threading.Thread(target=self._run_step, args=(job, step, run_env, seed), daemon=True) for step in job['steps']]
        for lane in lanes:
            lane.start()
        for lane in lanes:
            lane.join()
        with self.job_lock:
            job['status'] = 'finished' if all(s['status'] == 'finished' for s in job['steps']) else 'failed'
            job['finished'] = time.time()

    def _run_step(self, job, step, run_env, seed):
        step['_log'] = self.cache_dir / f"job-{job.get('id', 'job')}-{step['protect']}.log"
        step['_before'] = {p.name for p in self.runs.iterdir()} if self.runs.exists() else set()
        step['_log_offset'] = 0
        step['status'] = 'running'
        cmd = [self.python, 'lab.py', 'run', '--scenario', job['scenario'],
               '--environment', job['environment'], '--protect', step['protect'], '--engine', 'd2v2', '--interactive-approval', '--max-output-tokens','8192']
        if job.get('mode') == 'chat':
            cmd += ['--session-channel', str(job['_channel']), '--task-file', str(job['_channel']/'task.txt'),
                    '--phase', 'user-session']
        if seed:
            memory = seed.parent / step['protect']
            shutil.copytree(seed, memory)
            cmd.extend(['--memory-root', str(memory), '--memory-reader'])
        with step['_log'].open('w', encoding='utf-8') as log:
            log.write(f"$ lab.py run --scenario {job['scenario']} --environment {job['environment']} "
                      f"--protect {step['protect']} --engine d2v2\n")
            log.flush()
            try:
                code = subprocess.call(cmd, cwd=self.repo, env=run_env, stdout=log, stderr=subprocess.STDOUT)
            except OSError as exc:
                log.write(f'启动失败：{exc}\n')
                code = -1
        self._find_run(job, step)
        step['returncode'] = code
        result = self._load(self.runs / step['run_id'] / 'result.json', {}) if step.get('run_id') else {}
        step['status'] = 'finished' if code == 0 and result.get('model_run_ok') is True else 'failed'
        self._scanned = 0

    def _find_run(self, job, step):
        if step.get('run_id') or not self.runs.exists() or '_before' not in step:
            return
        # Bind to this subprocess's RUN output, never another experiment's new folder.
        with step.get('_log', job['_log']).open('rb') as log:
            log.seek(step.get('_log_offset', 0))
            output = log.read().decode('utf-8', errors='replace')
        for rid in re.findall(r'^RUN (\d{8}-\d{6}-[0-9a-f]{6}) ', output, re.M):
            manifest = self._load(self.runs / rid / 'manifest.json', {})
            if (rid not in step['_before'] and manifest.get('scenario') == job['scenario']
                    and manifest.get('environment') == job['environment']
                    and manifest.get('protection') == step['protect']
                    and manifest.get('guard_engine') == 'd2v2'
                    and manifest.get('evaluation_phase') != 'memory-setup'):
                step['run_id'] = rid
                return

    def job(self, job_id):
        j = self.jobs.get(job_id)
        if not j:
            return None
        for step in j['steps']:
            if step['status'] == 'running':
                self._find_run(j, step)
        parts = []
        for path, title in [(j['_log'], None)] + [(s.get('_log'), {'off': '防护关闭', 'on': '防护开启'}[s['protect']]) for s in j['steps']]:
            try:
                text = path.read_text(encoding='utf-8', errors='replace') if path else ''
            except OSError:
                text = ''
            if text.strip():
                parts.append((f'── {title} ──\n' if title else '') + text[-2000:])
        tail = '\n'.join(parts)
        out = {k: v for k, v in j.items() if not k.startswith('_')}
        out['steps'] = [{k: v for k, v in s.items() if not k.startswith('_')} for s in j['steps']]
        for step in out['steps']:
            if step.get('status') == 'running' and step.get('run_id'):
                finished = self._load(self.runs / step['run_id'] / 'agent-finished.json', None)
                if finished:
                    step['agent_finished'] = {'agent_elapsed_seconds': finished.get('agent_elapsed_seconds')}
                else:
                    step['progress'] = self._runtime_progress(step['run_id'])
        # Every Agent has stopped; only the background evidence review is still running.
        out['agents_finished'] = (j['status'] == 'running' and j.get('mode') != 'chat' and
            all(s.get('agent_finished') or s.get('status') in ('finished', 'failed') for s in out['steps']))
        out['log_tail'] = mask(tail)
        out['elapsed'] = round(j.get('finished', time.time()) - j['started'], 1)
        if j.get('mode') == 'chat':
            out['chat'] = self.chat_view(j)
            if out['chat']['phase'] == 'closed':
                with self.job_lock:
                    if j['status'] == 'running':
                        j['status'] = 'finalizing'
                    out['status'] = j['status']
        out['approvals'] = []
        for step in j['steps']:
            if step['status']=='running' and step.get('run_id'):
                try:
                    data=self._host_control(step['run_id'],'/approvals',{})
                    out['approvals'].extend({'run_id':step['run_id'],'protect':step['protect'],**a} for a in data['pending'])
                except ValueError:pass  # services still starting, or the run already closed its control file
                except OSError as exc:
                    # Keep a waiting Agent visible even when the control channel fails, and say why.
                    waiting=self._waiting_from_audit(step['run_id'])
                    out['approvals'].extend({'run_id':step['run_id'],'protect':step['protect'],**w} for w in waiting)
                    if waiting:out['approval_error']=f'审批通道连接失败（{type(exc).__name__}: {str(exc)[:160]}）'
        return out

    def _runtime_progress(self, run_id):
        """Expose transport timing and phase only, never model reasoning text."""
        folder = self.runs / run_id
        pending = {}
        for event in jsonl(folder / 'gateway.jsonl'):
            rid = event.get('request_id')
            if event.get('type') == 'proxy_request':
                pending[rid] = event
            elif event.get('type') in ('proxy_response', 'proxy_error', 'proxy_cancelled'):
                pending.pop(rid, None)
        if not pending:
            return None
        started = min(e.get('timestamp_ns', time.time_ns()) for e in pending.values())
        phase = 'waiting'
        log = folder / 'pi-events.jsonl'
        try:
            with log.open('rb') as stream:
                stream.seek(max(0, log.stat().st_size - 65536))
                tail = stream.read().decode('utf-8', errors='replace').splitlines()
            for line in reversed(tail):
                try:
                    event = json.loads(line)
                except ValueError:
                    continue
                if event.get('type') == 'message_update':
                    kind = event.get('assistantMessageEvent', {}).get('type', '')
                    phase = 'thinking' if kind.startswith('thinking_') else 'generating'
                    break
            updated = max(0, round(time.time() - log.stat().st_mtime, 1))
        except OSError:
            updated = None
        return {'phase': phase, 'request_seconds': max(0, round((time.time_ns() - started) / 1e9, 1)),
                'last_update_seconds': updated}

    def _waiting_from_audit(self, run_id):
        proposed, asked, waiting, closed = {}, {}, [], set()
        for e in jsonl(self.runs / run_id / 'audit.jsonl'):
            cid = e.get('call_id')
            if e.get('type') == 'tool_proposed':
                proposed[cid] = e
            elif e.get('type') == 'guard_decision' and e.get('origin') == 'host_approval':
                closed.add(cid)
            elif e.get('type') == 'guard_decision' and e.get('verdict') == 'ASK':
                asked[cid] = e
            elif e.get('type') == 'approval_waiting':
                waiting.append(cid)
            elif e.get('type') in ('approval_resumed', 'approval_hold_complete'):
                closed.add(cid)
        return [{'call_id': cid, 'agent_id': proposed.get(cid, {}).get('agent_id', 'main'),
                 'tool': proposed.get(cid, {}).get('tool'), 'args': proposed.get(cid, {}).get('args'),
                 'reason': asked.get(cid, {}).get('reason', ''), 'rule_id': asked.get(cid, {}).get('policy', ''),
                 'approvable': True, 'channel_error': True} for cid in waiting if cid not in closed]

    def _host_control(self, run_id, route, data):
        config=self._load(self.runs/run_id/'.local/host-control.json',{})
        if not config:raise ValueError('当前运行未开放交互审批，或已经结束')
        request=urllib.request.Request(config['origin']+route,data=json.dumps(data).encode(),
            headers={'Content-Type':'application/json','Authorization':'Bearer '+config['credential']},method='POST')
        with DIRECT.open(request,timeout=5) as response:return json.load(response)

    def resolve_approval(self, job_id, body):
        job=self.job(job_id)
        if not job or job['status']!='running':return 409,{'error':'运行已结束'}
        candidate=next((a for a in job['approvals'] if a['call_id']==body.get('call_id') and a['run_id']==body.get('run_id')),None)
        if not candidate or body.get('choice') not in ('approve','reject','reject_stop'):
            return 409,{'error':'该审批已处理、过期或不存在'}
        try:
            return 200,self._host_control(candidate['run_id'],'/resolve-approval',
                {'call_id':candidate['call_id'],'choice':body['choice']})
        except urllib.error.HTTPError as exc:
            detail=self._load_bytes(exc.read()).get('error','')
            return 409,{'error':'审批未生效：已过期、已处理或当前策略禁止批准'+(f'（{detail}）' if detail else '')}
        except (OSError,ValueError) as exc:return 409,{'error':f'审批未生效：无法连接本轮运行的审批通道（{type(exc).__name__}）'}

    @staticmethod
    def _load_bytes(data):
        try:
            value = json.loads(data or b'{}')
            return value if isinstance(value, dict) else {}
        except ValueError:
            return {}

    # ---------- model settings ----------
    def _settings_paths(self):
        return self.repo / '.local' / 'provider.json', self.repo / '.local' / 'review.json'

    def settings(self):
        agent_path, review_path = self._settings_paths()
        agent, review = self._load(agent_path, {}), self._load(review_path, {})
        view = lambda cfg, key: {'base_url': cfg.get('base_url', ''), 'model': cfg.get(key, ''),
                                 'api_style': cfg.get('api_style', 'chat_completions'), 'has_key': bool(cfg.get('api_key'))}
        return {'agent': view(agent, 'main_model'),
                'review': {**view(review, 'model'), 'separate': bool(review.get('enabled', True) and review.get('base_url') and review.get('model'))},
                'configured': bool(agent.get('base_url') and agent.get('api_key') and agent.get('main_model')),
                'running': any(j['status'] == 'running' for j in self.jobs.values()),
                'reasoning_capable': agent.get('reasoning_capable') is True}

    @staticmethod
    def _merge_model(form, current, model_key):
        merged = dict(current)
        for source, target in (('base_url', 'base_url'), ('model', model_key), ('api_style', 'api_style')):
            value = str(form.get(source) or '').strip()
            if value:
                merged[target] = value.rstrip('/') if source == 'base_url' else value
        key = str(form.get('api_key') or '').strip()
        if key:
            merged['api_key'] = key
        elif merged.get('base_url') != current.get('base_url'):
            # A stored key is only ever sent to the address it was entered for.
            merged.pop('api_key', None)
        if model_key == 'main_model' and 'reasoning_capable' in form:
            merged['reasoning_capable'] = form['reasoning_capable']
        return merged

    @staticmethod
    def _model_error(cfg, model_key, need_key=True):
        if 'reasoning_capable' in cfg and not isinstance(cfg['reasoning_capable'], bool):
            return '思考模式控制选项必须为布尔值'
        if not re.match(r'^https?://[^\s/]+', cfg.get('base_url') or ''):
            return '接口地址需以 http:// 或 https:// 开头'
        if not cfg.get(model_key):
            return '请填写模型名称'
        if cfg.get('api_style') not in API_STYLES:
            return '接口类型只能是 chat_completions 或 responses'
        if need_key and not cfg.get('api_key'):
            return '请填写 API Key（更换接口地址时需要重新填写）'
        return None

    def _write_private(self, path, value):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
        try:
            os.chmod(path, 0o600)
        except OSError:
            pass

    def save_settings(self, body):
        agent_path, review_path = self._settings_paths()
        agent = self._merge_model(body.get('agent') or {}, self._load(agent_path, {}), 'main_model')
        err = self._model_error(agent, 'main_model')
        if err:
            return 400, {'error': 'Agent 模型：' + err}
        form = body.get('review') or {}
        old_review = self._load(review_path, {})
        if form.get('separate'):
            review = self._merge_model(form, old_review, 'model')
            review.setdefault('api_style', agent['api_style'])
            if not review.get('api_key') and review.get('base_url') == agent['base_url']:
                review.pop('api_key', None)  # same service: lab.py reuses the Agent key
            err = self._model_error(review, 'model', need_key=review.get('base_url') != agent['base_url'])
            if err:
                return 400, {'error': '慢镜模型：' + err}
            review['enabled'] = True
        else:
            review = {**old_review, 'enabled': False}
        if agent != self._load(agent_path, {}):
            agent['credential_source'] = 'console settings'
            self._write_private(agent_path, agent)
        if review != old_review:
            self._write_private(review_path, review)
        return 200, self.settings()

    def _resolve_model(self, body):
        agent_path, review_path = self._settings_paths()
        agent = self._load(agent_path, {})
        if body.get('target') == 'review':
            current = self._load(review_path, {})
            cfg = self._merge_model(body, current, 'model')
            if not cfg.get('api_key') and cfg.get('base_url') == agent.get('base_url'):
                cfg['api_key'] = agent.get('api_key')
            return {'base_url': cfg.get('base_url'), 'api_key': cfg.get('api_key'), 'model': cfg.get('model'), 'api_style': cfg.get('api_style') or agent.get('api_style')}
        cfg = self._merge_model(body, agent, 'main_model')
        return {'base_url': cfg.get('base_url'), 'api_key': cfg.get('api_key'), 'model': cfg.get('main_model'), 'api_style': cfg.get('api_style'),
                'reasoning_capable': cfg.get('reasoning_capable') is True}

    def test_model(self, body):
        cfg = self._resolve_model(body)
        err = self._model_error(cfg, 'model')
        if err:
            return 400, {'error': err}
        import httpx
        responses = cfg['api_style'] == 'responses'
        url = cfg['base_url'].rstrip('/') + ('/responses' if responses else '/chat/completions')
        payload = ({'model': cfg['model'], 'input': 'Reply with the single word OK.', 'max_output_tokens': 16, 'store': False}
                   if responses else {'model': cfg['model'], 'messages': [{'role': 'user', 'content': 'Reply with the single word OK.'}], 'max_tokens': 16})
        if responses and cfg.get('reasoning_capable'):
            payload['reasoning'] = {'effort': 'none'}
        start = time.perf_counter()
        try:
            # Same network path as real runs: the service gateway does not use system proxies.
            with httpx.Client(timeout=60, trust_env=False) as client:
                response = client.post(url, json=payload, headers={'Authorization': 'Bearer ' + cfg['api_key']})
        except httpx.HTTPError as exc:
            return 200, {'ok': False, 'error': f'连接失败：{type(exc).__name__}'}
        latency = round((time.perf_counter() - start) * 1000)
        if response.status_code != 200:
            return 200, {'ok': False, 'latency_ms': latency, 'error': f'HTTP {response.status_code}：{response.text[:200]}'}
        try:
            data = response.json()
            text = (data['output_text'] if 'output_text' in data else
                    ''.join(c.get('text', '') for o in data.get('output', []) for c in o.get('content', []) if isinstance(c, dict))) if responses \
                else data['choices'][0]['message'].get('content') or ''
        except (ValueError, KeyError, IndexError, TypeError):
            return 200, {'ok': False, 'latency_ms': latency, 'error': '接口返回格式不符合所选接口类型'}
        return 200, {'ok': True, 'latency_ms': latency, 'reply': str(text)[:80], 'model': cfg['model']}

    def list_models(self, body):
        cfg = self._resolve_model(body)
        if not re.match(r'^https?://', cfg.get('base_url') or '') or not cfg.get('api_key'):
            return 400, {'error': '请先填写接口地址和 API Key'}
        import httpx
        try:
            with httpx.Client(timeout=30, trust_env=False) as client:
                response = client.get(cfg['base_url'].rstrip('/') + '/models', headers={'Authorization': 'Bearer ' + cfg['api_key']})
            ids = sorted({m.get('id') for m in response.json().get('data', []) if isinstance(m, dict) and m.get('id')})
        except (httpx.HTTPError, ValueError, AttributeError) as exc:
            return 200, {'models': [], 'error': f'该接口不支持列出模型（{type(exc).__name__}），可直接填写模型名称'}
        if response.status_code != 200:
            return 200, {'models': [], 'error': f'HTTP {response.status_code}，可直接填写模型名称'}
        return 200, {'models': ids[:300]}


def make_handler(console):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, fmt, *args):
            pass

        def send_json(self, code, payload, download=None):
            data = json.dumps(mask(payload), ensure_ascii=False, indent=2 if download else None).encode('utf-8')
            self.send_response(code)
            self.send_header('Content-Type', 'application/json; charset=utf-8')
            self.send_header('Content-Length', str(len(data)))
            self.send_header('Cache-Control', 'no-store')
            if download:
                self.send_header('Content-Disposition', f'attachment; filename="{download}"')
            self.end_headers()
            self.wfile.write(data)

        def body(self):
            length = int(self.headers.get('Content-Length') or 0)
            return json.loads(self.rfile.read(min(length, 2_000_000)) or b'{}')

        def route(self, method):
            url = urlsplit(self.path)
            parts = [p for p in url.path.split('/') if p]
            query = parse_qs(url.query)
            if not parts or parts[0] != 'api':
                return False
            host = (self.headers.get('Host') or '').rsplit(':', 1)[0].strip('[]')
            origin = urlsplit(self.headers.get('Origin') or '').hostname
            if host not in LOCAL_HOSTS or method != 'GET' and origin is not None and origin not in LOCAL_HOSTS:
                return self.send_json(403, {'error': '仅允许本机控制台页面访问'})
            try:
                if method == 'GET':
                    if parts == ['api','runtime']:
                        return self.send_json(200,console.resident.status() if console.resident else {'phase':'per_run'})
                    if parts==['api','active-job']:
                        active=next((j for j in console.jobs.values() if j['status']=='running'),None)
                        if active is None:
                            active=next((j for j in console.jobs.values() if j['status']=='finalizing'),None)
                        return self.send_json(200,console.job(active['id']) if active else None)
                    if parts == ['api', 'overview']:
                        return self.send_json(200, console.overview(query))
                    if parts == ['api', 'runs']:
                        return self.send_json(200, console.list_runs(query))
                    if parts[:2] == ['api', 'runs'] and len(parts) == 3:
                        trace = console.trace(parts[2])
                        return self.send_json(200, trace) if trace else self.send_json(404, {'error': '未找到运行'})
                    if parts[:2] == ['api', 'pairs'] and len(parts) == 3:
                        return self.send_json(200, console.pairs(parts[2]))
                    if parts == ['api', 'summary']:
                        s = console.summary()
                        return self.send_json(200, s) if s else self.send_json(404, {'error': '未找到竞赛评测汇总 console/data/evaluation-summary.json'})
                    if parts[:2] == ['api', 'replay'] and len(parts) == 3:
                        r = console.replay(parts[2])
                        return self.send_json(200, r) if r else self.send_json(404, {'error': '未找到运行'})
                    if parts == ['api', 'compaction']:
                        return self.send_json(200, console.compaction_runs())
                    if parts[:2] == ['api', 'compaction'] and len(parts) == 3:
                        r = console.compaction(parts[2])
                        return self.send_json(200, r) if r else self.send_json(404, {'error': '未找到运行'})
                    if parts == ['api', 'scenarios']:
                        return self.send_json(200, console.scenarios())
                    if parts == ['api', 'scenarios-export']:
                        origin = (query.get('origin') or ['all'])[0]
                        return self.send_json(200, console.export_scenarios(origin), download=f'd2guard-scenarios-{origin}.json')
                    if parts[:2] == ['api', 'scenarios'] and len(parts) == 3:
                        s = console.scenario(parts[2])
                        return self.send_json(200, s) if s else self.send_json(404, {'error': '未找到场景'})
                    if parts == ['api', 'policies']:
                        return self.send_json(200, console.policies())
                    if parts == ['api', 'settings']:
                        return self.send_json(200, console.settings())
                    if parts[:2] == ['api', 'jobs'] and len(parts) == 3:
                        job = console.job(parts[2])
                        return self.send_json(200, job) if job else self.send_json(404, {'error': '未找到任务'})
                elif method == 'POST':
                    if parts == ['api','chat']:
                        return self.send_json(*console.start_chat(self.body()))
                    if len(parts)==4 and parts[:2]==['api','jobs'] and parts[3]=='chat':
                        return self.send_json(*console.chat_command(parts[2],self.body()))
                    if len(parts)==4 and parts[:2]==['api','jobs'] and parts[3]=='approval':
                        return self.send_json(*console.resolve_approval(parts[2],self.body()))
                    if parts == ['api', 'launch']:
                        return self.send_json(*console.launch(self.body()))
                    if parts == ['api', 'settings', 'test']:
                        return self.send_json(*console.test_model(self.body()))
                    if parts == ['api', 'settings', 'models']:
                        return self.send_json(*console.list_models(self.body()))
                    if parts == ['api', 'scenarios']:
                        return self.send_json(*console.create_scenario(self.body()))
                    if parts == ['api', 'scenarios-import']:
                        return self.send_json(*console.import_scenarios(self.body()))
                elif method == 'PUT' and parts == ['api', 'settings']:
                    return self.send_json(*console.save_settings(self.body()))
                elif method == 'PUT' and parts[:2] == ['api', 'scenarios'] and len(parts) == 3:
                    return self.send_json(*console.update_scenario(parts[2], self.body()))
                elif method == 'DELETE' and parts[:2] == ['api', 'scenarios'] and len(parts) == 3:
                    return self.send_json(*console.delete_scenario(parts[2]))
                return self.send_json(404, {'error': 'not found'})
            except json.JSONDecodeError:
                return self.send_json(400, {'error': '请求格式错误，需要 JSON'})
            except Exception as exc:  # report, never crash the console
                return self.send_json(500, {'error': type(exc).__name__, 'detail': str(exc)[:300]})

        def do_GET(self):
            if self.route('GET') is not False:
                return
            parts = [p for p in urlsplit(self.path).path.split('/') if p]
            name = 'index.html' if not parts else '/'.join(parts)
            path = (STATIC / name).resolve()
            if not path.is_file() or STATIC.resolve() not in path.parents:
                self.send_error(404)
                return
            data = path.read_bytes()
            self.send_response(200)
            self.send_header('Content-Type', TYPES.get(path.suffix, 'application/octet-stream'))
            self.send_header('Content-Length', str(len(data)))
            self.send_header('Cache-Control', 'no-cache')
            self.end_headers()
            self.wfile.write(data)

        def do_POST(self):
            if self.route('POST') is False:
                self.send_json(404, {'error': 'not found'})

        def do_PUT(self):
            if self.route('PUT') is False:
                self.send_json(404, {'error': 'not found'})

        def do_DELETE(self):
            if self.route('DELETE') is False:
                self.send_json(404, {'error': 'not found'})

    return Handler



class LocalHTTPServer(ThreadingHTTPServer):
    allow_reuse_address = os.name != 'nt'

    def server_bind(self):
        if os.name == 'nt':
            self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
        super().server_bind()


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--repo', default=str(HERE.parent / 'd2guard-next'), help='d2guard-next 仓库路径')
    parser.add_argument('--host', default='127.0.0.1')
    parser.add_argument('--port', type=int, default=8765)
    parser.add_argument('--python', default=sys.executable, help='运行 lab.py 所用的 Python')
    args = parser.parse_args()
    if args.host != '127.0.0.1':
        parser.error('控制台仅允许监听 127.0.0.1')
    console = Console(args.repo, args.python)
    server = LocalHTTPServer((args.host, args.port), make_handler(console))
    if os.environ.get('D2_RESIDENT_INFERENCE') == '1' and all((console.repo/'.local'/n).is_file() for n in ('laya.json','s1.json')):
        from inference_pool import ResidentProcess
        console.resident = ResidentProcess(console.repo, args.python)
    print(f'D2Guard 控制台：http://{args.host}:{server.server_port}  （仓库 {console.repo}）', flush=True)
    print('首次启动会建立运行索引，可能需要一两分钟。', flush=True)
    if os.environ.get('D2_OPEN_BROWSER') == '1':
        import webbrowser
        webbrowser.open(f'http://{args.host}:{server.server_port}/')
    try:
        server.serve_forever()
    finally:
        server.server_close()
        if console.resident:
            console.resident.close()


if __name__ == '__main__':
    main()
