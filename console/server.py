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
import sys
import threading
import time
import uuid
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
FAMILY_ZH = {'indirect': '间接注入', 'direct': '直接注入', 'memory': '记忆污染', 'supply_chain': 'MCP 供应链',
             'tool_abuse': '工具滥用', 'egress': '敏感外发', 'write': '敏感写入', 'ssh': '私钥窃取',
             'subagent': '子 Agent', 'variant': '变形绕过', 'language': '多语言绕过', 'dilution': '上下文稀释',
             'adversarial': '对抗样本', 'semantic_camouflage': '语义伪装', 'normal': '正常任务',
             'hard_negative': '困难负例', 'benign_nonliteral': '非字面正常任务', 'legacy': '早期 README 场景',
             'custom': '自定义'}


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
            'outcome': result.get('outcome') or ('running' if not result else None),
            'attack_succeeded': result.get('attack_succeeded'), 'received_bytes': result.get('received_bytes'),
            'asked': len(result.get('asked_calls') or []), 'blocked': len(result.get('blocked_calls') or []),
            'task_completed': result.get('task_completed'), 'elapsed_seconds': result.get('elapsed_seconds'),
            'complete': bool(result), 'verdicts': dict(verdicts), 'would': dict(would), 'rules': dict(rules),
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
                signature = tuple((f.stat().st_mtime_ns, f.stat().st_size) if f.exists() else None for f in (folder/'manifest.json',folder/'result.json',folder/'decisions.jsonl'))
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
            out.append({'id': data['id'], 'category': data.get('category'), 'family': data.get('family'),
                        'family_label': FAMILY_ZH.get(data.get('family'), data.get('family')),
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
        for rule in ('DT-4c-S1','DT-4c-EGRESS','POL-TOOL-BUDGET'):
            hits.setdefault(rule,0)
            reasons.setdefault(rule,'当前索引中尚无命中记录')
        cfg_path = os.environ.get('D2_S1_CONFIG')
        cfg = self._load(Path(cfg_path), {}) if cfg_path else self._load(self.repo / '.local/stage-d5/s1-enabled-config.json', self._load(self.repo / '.local/stage-d4/s1-enabled-config.json', {}))
        runtime_mode = 'add_risk' if os.environ.get('D2_S1_DISABLE') == '1' else cfg.get('decision_mode', 'add_risk')
        return {'runtime_mode':runtime_mode, 'dsl': dsl, 'hits': dict(hits), 'reasons': reasons, 'verdicts': {k: dict(v) for k, v in verdict_of.items()}}

    # ---------- launching real runs ----------
    def launch(self, body):
        ids = {s['id'] for s in self._scenario_files()}
        scenario, env, mode = body.get('scenario'), body.get('environment'), body.get('mode', 'single')
        if scenario not in ids or env not in ('clean', 'attack'):
            return 400, {'error': '参数无效'}
        if mode == 'arena':
            steps = ['off', 'on']
        elif mode == 'single' and body.get('protect') in ('on', 'off'):
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
        threading.Thread(target=self._run_job, args=(job,), daemon=True).start()
        return 200, self.job(job_id)

    def _run_job(self, job):
        with job['_log'].open('w', encoding='utf-8') as log:
            for step in job['steps']:
                before = {p.name for p in self.runs.iterdir()} if self.runs.exists() else set()
                step['status'] = 'running'
                step['_before'] = before
                step['_log_offset'] = job['_log'].stat().st_size
                cmd = [self.python, 'lab.py', 'run', '--scenario', job['scenario'],
                       '--environment', job['environment'], '--protect', step['protect'], '--engine', 'd2v2']
                log.write(f"$ lab.py run --scenario {job['scenario']} --environment {job['environment']} "
                          f"--protect {step['protect']} --engine d2v2\n")
                log.flush()
                try:
                    code = subprocess.call(cmd, cwd=self.repo, stdout=log, stderr=subprocess.STDOUT)
                except OSError as exc:
                    log.write(f'启动失败：{exc}\n')
                    code = -1
                self._find_run(job, step)
                step['returncode'] = code
                step['status'] = 'finished' if code == 0 and step.get('run_id') and self._load(self.runs / step['run_id'] / 'result.json', {}) else 'failed'
                self._scanned = 0
        job['status'] = 'finished' if all(s['status'] == 'finished' for s in job['steps']) else 'failed'
        job['finished'] = time.time()

    def _find_run(self, job, step):
        if step.get('run_id') or not self.runs.exists() or '_before' not in step:
            return
        # Bind to this subprocess's RUN output, never another experiment's new folder.
        with job['_log'].open('rb') as log:
            log.seek(step.get('_log_offset', 0))
            output = log.read().decode('utf-8', errors='replace')
        for rid in re.findall(r'^RUN (\d{8}-\d{6}-[0-9a-f]{6}) ', output, re.M):
            manifest = self._load(self.runs / rid / 'manifest.json', {})
            if (rid not in step['_before'] and manifest.get('scenario') == job['scenario']
                    and manifest.get('environment') == job['environment']
                    and manifest.get('protection') == step['protect']
                    and manifest.get('guard_engine') == 'd2v2'):
                step['run_id'] = rid
                return

    def job(self, job_id):
        j = self.jobs.get(job_id)
        if not j:
            return None
        for step in j['steps']:
            if step['status'] == 'running':
                self._find_run(j, step)
        try:
            tail = j['_log'].read_text(encoding='utf-8', errors='replace')[-3000:]
        except OSError:
            tail = ''
        out = {k: v for k, v in j.items() if not k.startswith('_')}
        out['steps'] = [{k: v for k, v in s.items() if not k.startswith('_')} for s in j['steps']]
        out['log_tail'] = mask(tail)
        out['elapsed'] = round(j.get('finished', time.time()) - j['started'], 1)
        return out


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
            try:
                if method == 'GET':
                    if parts == ['api', 'overview']:
                        return self.send_json(200, console.overview(query))
                    if parts == ['api', 'runs']:
                        return self.send_json(200, console.list_runs(query))
                    if parts[:2] == ['api', 'runs'] and len(parts) == 3:
                        trace = console.trace(parts[2])
                        return self.send_json(200, trace) if trace else self.send_json(404, {'error': '未找到运行'})
                    if parts[:2] == ['api', 'pairs'] and len(parts) == 3:
                        return self.send_json(200, console.pairs(parts[2]))
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
                    if parts[:2] == ['api', 'jobs'] and len(parts) == 3:
                        job = console.job(parts[2])
                        return self.send_json(200, job) if job else self.send_json(404, {'error': '未找到任务'})
                elif method == 'POST':
                    if parts == ['api', 'launch']:
                        return self.send_json(*console.launch(self.body()))
                    if parts == ['api', 'scenarios']:
                        return self.send_json(*console.create_scenario(self.body()))
                    if parts == ['api', 'scenarios-import']:
                        return self.send_json(*console.import_scenarios(self.body()))
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
    print(f'D2Guard 控制台：http://{args.host}:{args.port}  （仓库 {console.repo}）', flush=True)
    print('首次启动会建立运行索引，可能需要一两分钟。', flush=True)
    ThreadingHTTPServer((args.host, args.port), make_handler(console)).serve_forever()


if __name__ == '__main__':
    main()
