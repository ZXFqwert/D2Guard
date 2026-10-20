"""Build a read-only attack trace for one D2Guard run directory.

The trace is assembled only from evidence that the run already recorded
(manifest, result, audit, decisions and the run's SQLite evidence store).
Nothing here calls a model or changes a verdict.
"""
import json
import os
import re
import shutil
import sqlite3
import tempfile
import hashlib
import base64
from .ledger import values
from .provenance import memory_origin
from d2core.extractor import SECRET_ASSIGNMENT, KEY_PATTERNS
from pathlib import Path

SECRET = re.compile(r'(?:d2-test-|D2-CANARY-)[0-9A-Za-z_-]+')
TOOL_OP = {'fs_read': 'fs.read', 'fs_write': 'fs.write', 'net_fetch': 'net.fetch', 'spawn_subagent': 'spawn',
           'mcp_call': 'mcp.call', 'memory_read': 'memory.read', 'memory_write': 'memory.write',
           'exec': 'exec', 'git_push': 'git.push', 'git_commit': 'git.commit'}
SOURCE_KIND = {'LOCAL_FILE': '文件', 'WEB': '网页', 'MCP_RET': 'MCP 返回', 'MCP_DESC': 'MCP 工具描述', 'MEMORY': '记忆',
               'USER_QUOTED': '用户转发内容', 'USER_INJECTED': '用户输入（疑似直接注入）', 'SUBAGENT_OUTPUT': '子 Agent 输出', 'SUBAGENT': '子 Agent 输出',
               'TOOL_ERROR': '工具错误'}
EXCERPT = 160


def mask(value):
    if isinstance(value, str):
        value = SECRET_ASSIGNMENT.sub(lambda m: m.group().replace(m.group(1), '•' * len(m.group(1))), value)
        value = KEY_PATTERNS.sub(lambda m: '•' * len(m.group()), value)
        return SECRET.sub(lambda m: '•' * len(m.group()), value)
    if isinstance(value, list):
        return [mask(v) for v in value]
    if isinstance(value, dict):
        return {k: mask(v) for k, v in value.items()}
    return value


def jsonl(path):
    rows = []
    if not path.exists():
        return rows
    with path.open(encoding='utf-8') as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError:
                break  # a run still being written may end mid-line
    return rows


def load_json(path):
    try:
        return json.loads(path.read_text(encoding='utf-8'))
    except (OSError, json.JSONDecodeError):
        return {}


def open_store(folder):
    """Open the run's evidence store without writing to it."""
    db_path = folder / 'state.sqlite3'
    if not db_path.exists():
        return None, None
    tmp = tempfile.mkdtemp(prefix='d2trace-')
    db = sqlite3.connect(Path(tmp) / 'state.sqlite3')
    source = sqlite3.connect(db_path.resolve().as_uri()+'?mode=ro', uri=True)
    try: source.backup(db)
    finally: source.close()
    db.row_factory = sqlite3.Row
    return db, tmp


def store_rows(db, sql):
    try:
        return db.execute(sql).fetchall()
    except sqlite3.Error:
        return []


def target_of(tool, args):
    args = args or {}
    for key in ('path', 'url', 'key', 'name', 'command', 'remote'):
        if args.get(key):
            return str(args[key])
    if tool == 'spawn_subagent':
        return '子 Agent'
    return ''


def short(text, n=EXCERPT):
    text = ' '.join(str(text or '').split())
    return text if len(text) <= n else text[:n] + '…'


def build_trace(folder):
    folder = Path(folder)
    manifest = load_json(folder / 'manifest.json')
    result = load_json(folder / 'result.json')
    finished = {} if result else load_json(folder / 'agent-finished.json')
    shown = result or finished.get('preliminary') or {}
    audit = jsonl(folder / 'audit.jsonl')
    decisions = jsonl(folder / 'decisions.jsonl')
    task = (folder / 'task.txt').read_text(encoding='utf-8') if (folder / 'task.txt').exists() else ''

    db, tmp = open_store(folder)
    events, source_s1, spawn_of = {}, {}, {}
    memory_entries=[]
    try:
        if db is not None:
            for r in store_rows(db, 'SELECT id,agent,kind,source,uri,raw,sha,metadata FROM events'):
                events[r['id']] = dict(r)
            for r in store_rows(db,'SELECT data FROM memory_entries'):
                memory_entries.append(json.loads(r['data']))
            sid_event = {}
            for r in store_rows(db, 'SELECT source_id,event_id FROM source_events'):
                sid_event.setdefault(r['source_id'], []).append(r['event_id'])
            for r in store_rows(db, 'SELECT source_id,data FROM source_analysis'):
                try:
                    data = json.loads(r['data'])
                except (TypeError, json.JSONDecodeError):
                    continue
                for ev in sid_event.get(r['source_id'], []):
                    source_s1[ev] = {'s1': data.get('s1'), 'directives': data.get('directives') or [],
                                     'unknowns': data.get('unknowns') or [],
                                     'direct_injection': data.get('direct_injection')}
    finally:
        if db is not None:
            db.close()
            shutil.rmtree(tmp, ignore_errors=True)

    def valid_ref(ref):
        if not isinstance(ref,dict):return False
        ev=events.get(ref.get('event_id'))
        span=ref.get('char_span')
        return bool(ev and ev['sha']==hashlib.sha256(ev['raw'].encode()).hexdigest()
            and ref.get('sha256')==ev['sha'] and isinstance(span,list) and len(span)==2
            and all(type(x) is int for x in span) and 0<=span[0]<=span[1]<=len(ev['raw']))

    t0 = next((x.get('timestamp_ns') for x in audit if x.get('timestamp_ns')), None)

    def ms(x):
        ts = x.get('timestamp_ns')
        return round((ts - t0) / 1e6) if ts and t0 else None

    # Agents and the spawn tree.
    agents = {'main': {'id': 'main', 'label': '主 Agent', 'parent': None, 'spawn_call': None}}
    for x in audit:
        if x.get('type') == 'subagent_spawn':
            child = x.get('child_agent_id')
            n = sum(1 for a in agents.values() if a['parent']) + 1
            agents[child] = {'id': child, 'label': f'子 Agent {n}', 'parent': x.get('agent_id', 'main'),
                             'spawn_call': x.get('call_id')}
            spawn_of[x.get('call_id')] = child
        aid = x.get('agent_id')
        if aid and aid not in agents:
            agents[aid] = {'id': aid, 'label': aid, 'parent': None, 'spawn_call': None}

    # Decisions with full evidence, keyed by call id (the last decision wins).
    dec_by_call, reviews, core = {}, {}, {}
    for d in decisions:
        t = d.get('type')
        if t == 'core_started':
            core = d
        elif t in ('decision','approval_consumed','approval_rejected') and d.get('call_id'):
            dec_by_call[d['call_id']] = {**dec_by_call.get(d['call_id'],{}),**d}
        elif t == 'slow_review':
            reviews[d.get('call_id')] = {'status': 'ok', **(d.get('result') or {}), 'latency_ms': d.get('latency_ms')}
        elif t == 'slow_review_failed':
            reviews.setdefault(d.get('call_id'), {'status': 'failed', 'error_type': d.get('error_type')})

    # Calls, sources and the timeline, in audit order.
    calls, sources, timeline = {}, {}, []
    for x in audit:
        t, cid, aid = x.get('type'), x.get('call_id'), x.get('agent_id', 'main')
        row = {'seq': x.get('seq'), 't_ms': ms(x), 'agent': aid, 'kind': t, 'call_id': cid}
        if t == 'user_input':
            row.update(title='用户任务', detail=short(x.get('task'), 400))
        elif t == 'system_init':
            continue
        elif t == 'model_request':
            row.update(title=f"模型请求 #{x.get('request_index')}", detail='')
        elif t in ('model_response', 'tool_outcome'):
            continue
        elif t == 'assistant_turn':
            if not x.get('text') and x.get('proposals'):
                continue
            row.update(title='Agent 回复', detail=short(x.get('text'), 400) or '（无文字）')
        elif t == 'tool_proposed':
            tool = x.get('tool')
            calls[cid] = {'call_id': cid, 'agent': aid, 'tool': tool, 'op': TOOL_OP.get(tool, tool),
                          'target': mask(target_of(tool, x.get('args'))), 'args': mask(x.get('args')),
                          'verdict': None, 'executed': False, 'seq': x.get('seq'), 't_ms': ms(x)}
            row.update(title=f"提出调用 {calls[cid]['op']}", detail=calls[cid]['target'])
        elif t == 'guard_decision':
            c = calls.setdefault(cid, {'call_id': cid, 'agent': aid, 'tool': x.get('tool'),
                                       'op': TOOL_OP.get(x.get('tool'), x.get('tool')),
                                       'target': mask(target_of(x.get('tool'), x.get('args'))),
                                       'args': mask(x.get('args')), 'executed': False,
                                       'seq': x.get('seq'), 't_ms': ms(x)})
            would = x.get('would_verdict') or x.get('verdict')
            c.update(verdict=x.get('verdict'), would_verdict=would, rule_id=x.get('rule_id') or x.get('policy'),
                     risk=x.get('risk'), reason=x.get('reason'))
            title = f"裁决 {x.get('verdict')}"
            c['approval_status']=x.get('approval_status')
            if x.get('origin')=='host_approval':
                title={'approved_once':'人工批准本次调用','rejected':'人工拒绝本次调用','expired':'审批过期，未执行'}.get(x.get('approval_status'),title)
            elif would != x.get('verdict'):
                title += f"（防护关闭，开启时应为 {would}）"
            row.update(title=title, detail=f"{c['op']} {c['target']}", verdict=x.get('verdict'), would_verdict=would,
                       rule_id=c['rule_id'], risk=x.get('risk'), reason=x.get('reason'))
        elif t == 'tool_started':
            if cid in calls:
                calls[cid]['executed'] = True
            row.update(title='开始执行', detail=cid)
        elif t == 'tool_result':
            c = calls.get(cid)
            if c is not None:
                c['result_excerpt'] = mask(short(x.get('text')))
                c['is_error'] = bool(x.get('is_error'))
            ev = events.get(x.get('event_id'), {})
            src_type = ev.get('source')
            if src_type and src_type not in ('MODEL_GENERATED', 'TRUSTED_USER'):
                sources[x['event_id']] = {'event_id': x['event_id'], 'type': src_type,
                                          'kind': SOURCE_KIND.get(src_type, src_type), 'uri': mask(ev.get('uri')),
                                          'agent': aid, 'via_call': cid, 'text': mask(ev.get('raw') or x.get('text') or ''),
                                          't_ms': ms(x)}
            row.update(title=f"返回 {c['op'] if c else x.get('tool')}", detail=mask(short(x.get('text'))),
                       source_type=src_type, event_id=x.get('event_id'))
        elif t == 'subagent_spawn':
            row.update(title='派发子 Agent', detail=agents.get(x.get('child_agent_id'), {}).get('label', ''),
                       child=x.get('child_agent_id'))
        elif t == 'subagent_end':
            row.update(title='子 Agent 结束', detail=mask(short(x.get('final_answer'))), child=x.get('child_agent_id'))
        elif t == 'approval_hold_complete':
            row.update(title='挂起等待用户确认', detail='该调用未执行')
        elif t == 'approval_waiting':
            row.update(title='等待网页审批',detail='当前调用尚未执行')
        elif t == 'approval_resumed':
            row.update(title='批准后继续原生调用',detail=cid)
        else:
            row.update(title=t, detail='')
        timeline.append(row)

    # Sources the store saw that never came back as a tool result (MCP descriptions, memory, quotes).
    for ev_id, ev in events.items():
        if ev_id in sources or ev.get('source') in (None, 'MODEL_GENERATED', 'TRUSTED_USER', 'HOST_CONFIGURATION'):
            continue
        if ev.get('kind') in ('mcp_description', 'user_quote', 'memory_entry', 'tool_result','MEMORY_PROVENANCE') or (ev.get('kind') == 'CONTENT_IN' and ev.get('source') in ('USER_QUOTED', 'USER_INJECTED')):
            sources[ev_id] = {'event_id': ev_id, 'type': ev['source'], 'kind': SOURCE_KIND.get(ev['source'], ev['source']),
                              'uri': mask(ev.get('uri')), 'agent': ev.get('agent') or 'main', 'via_call': None,
                              'text': mask(ev.get('raw') or ''), 't_ms': None}
            if ev.get('kind')=='MEMORY_PROVENANCE':
                metadata=json.loads(ev.get('metadata') or '{}')
                sources[ev_id].update(kind='记忆继承 / '+sources[ev_id]['kind'],
                    writer_session=metadata.get('writer_session'),original_event_id=metadata.get('original_event_id'))

    alias = {}

    # Highlights: rule-extracted directives, unresolved spans, and spans cited by decisions.
    for ev_id, src in sources.items():
        marks = []
        info = source_s1.get(ev_id, {})
        for d in info.get('directives', []):
            span = (d.get('evidence_ref') or {}).get('char_span')
            if span and valid_ref(d.get('evidence_ref') or {}):
                ops = ', '.join(f"{r.get('op')} {r.get('target')}" for r in d.get('action_relations', []))
                marks.append({'span': span, 'kind': 'directive', 'label': '规则抽取的指令：' + mask(ops)})
        for u in info.get('unknowns', []):
            span = (u.get('evidence_ref') or {}).get('char_span')
            if span and valid_ref(u.get('evidence_ref') or {}):
                kind = 's1' if str(u.get('signal', '')).startswith('model:') else 'unknown'
                marks.append({'span': span, 'kind': kind, 'label': u.get('reason', '')})
        for m in ((info.get('direct_injection') or {}).get('matches') or []):
            if m.get('char_span'):
                marks.append({'span': m['char_span'], 'kind': 'injection', 'label': '直接注入特征（' + m.get('label', '') + '）：' + mask(m.get('cue', ''))})
        if info.get('direct_injection'):
            src['direct_injection'] = info['direct_injection'].get('labels')
        ev=events[ev_id]
        src['evidence_ref']={'event_id':ev_id,'sha256':ev['sha'],'char_span':[0,len(ev['raw'])]}
        src['s1'] = info.get('s1')
        src['highlights'] = marks

    # Attach evidence, induced-by links and slow reviews to each call.
    for cid, c in calls.items():
        d = dec_by_call.get(cid, {})
        delta = ((d.get('evidence') or {}).get('security_delta')) or {}
        induced = []
        for m in (delta.get('matches_untrusted_taint') or []):
            ref = m.get('evidence_ref') or {}
            ev = alias.get(ref.get('event_id'), ref.get('event_id'))
            if valid_ref(ref) and ev in sources and not any(i['event_id'] == ev and i['span'] == ref.get('char_span') for i in induced):
                induced.append({'event_id': ev, 'span': ref.get('char_span'), 'uri': mask(m.get('source_uri')),
                                'source_type': m.get('source_type'), 'by': 'rule', 'reference': ref, 'causal_strength':'association'})
        for ref in ((d.get('evidence') or {}).get('evidence_refs') or []):
            if not ref:continue
            ev = alias.get(ref.get('event_id'), ref.get('event_id'))
            if valid_ref(ref) and ev in sources and not any(i['event_id'] == ev for i in induced):
                induced.append({'event_id': ev, 'span': ref.get('char_span'), 'uri': sources[ev]['uri'],
                                'source_type': sources[ev]['type'], 'by': 'evidence', 'reference': ref, 'causal_strength':'association'})
        for i in induced:
            src = sources.get(i['event_id'])
            if src and i.get('span'):
                a, b = i['span']
                i['excerpt'] = short(src['text'][a:b], 240)
        c['induced_by'] = induced
        c['decision_facts'] = d.get('decision_facts')
        c['fast'] = mask(d.get('fast')) if d.get('fast') else None
        c['latency_ms'] = d.get('local_latency_ms')
        c['secret_hit'] = bool(delta.get('carries_secret'))
        c['review'] = mask(reviews.get(cid)) if cid in reviews else None
        c['evidence_refs']=[ref for ref in ((d.get('evidence') or {}).get('evidence_refs') or []) if ref and valid_ref(ref)]
        c['report'] = template_report(task, c, sources)
        c['in_scope'] = bool(delta.get('in_user_granted_scope') or (c['decision_facts'] or {}).get('literal_scope'))
        c['alignment'] = alignment(c)
        if cid in spawn_of:
            c['child'] = spawn_of[cid]

    anchor = next((((d.get('previous_security_state') or {}).get('authority_anchor'))
                   for d in decisions if d.get('type') == 'decision'
                   and (d.get('previous_security_state') or {}).get('authority_anchor')), None) or {}
    plan = {'mode': anchor.get('intent_mode'), 'read': mask(anchor.get('read') or []),
            'write': mask(anchor.get('write') or []), 'net': mask(anchor.get('net') or []),
            'spawn': mask(anchor.get('spawn') or []), 'complete': not anchor.get('coverage_incomplete'),
            'available': bool(anchor)}
    graph = build_graph(task, agents, calls, sources)
    enrich_graph(graph, timeline, events, calls) 
    impact = build_impact(calls, result)
    run = {
        'id': folder.name, 'scenario': manifest.get('scenario'), 'environment': manifest.get('environment'),
        'protection': manifest.get('protection'), 'model': manifest.get('model'), 'pi_version': manifest.get('pi_version'),
        'decision_mode': core.get('decision_mode') or (manifest.get('content_model') or {}).get('decision_mode') or 'unknown',
        'engine': manifest.get('guard_engine'), 'batch_id': manifest.get('batch_id'), 'task': mask(task),
        'outcome': shown.get('outcome'), 'attack_succeeded': shown.get('attack_succeeded'),
        'received_bytes': shown.get('received_bytes'), 'task_completed': shown.get('task_completed'),
        'approved_calls':shown.get('approved_calls',[]),'rejected_calls':shown.get('rejected_calls',[]),
        'elapsed_seconds': result.get('elapsed_seconds'), 'complete': bool(result),
        'agent_elapsed_seconds': result.get('agent_elapsed_seconds', finished.get('agent_elapsed_seconds')),
        'review_wait_seconds': result.get('post_agent_evidence_wait_seconds'),
        'agent_finished': bool(result or finished),
        'fast_model': (core.get('content_model') or core.get('fast_model') or {}).get('backend')
        if isinstance(core.get('content_model') or core.get('fast_model'), dict) else None,
    }
    output = {'run': run, 'agents': list(agents.values()), 'calls': sorted(calls.values(), key=lambda c: c.get('seq') or 0),
            'sources': sorted(sources.values(), key=lambda s: (s['t_ms'] is None, s['t_ms'] or 0)),
            'timeline': timeline, 'graph': graph, 'impact': impact, 'plan': plan}
    output['memory_links']=[]
    for entry in memory_entries:
        try:origin=memory_origin(folder,entry)
        except (OSError,sqlite3.Error,ValueError,KeyError):origin={'writer_run_id':None,'native_write_verified':False}
        output['memory_links'].append({'key':entry['key'],'writer_session':entry['writer_session'],
            'content_sha256':entry['content_sha256'],**origin})
    # Mask registered values in every public field, including task, args and model reports.
    secrets=set()
    for ev in events.values():
        secrets.update(values(ev['raw']))
    def redact(value):
        if isinstance(value,str):
            for secret in secrets:
                for variant in (secret,base64.b64encode(secret.encode()).decode(),base64.urlsafe_b64encode(secret.encode()).decode()):
                    value=value.replace(variant,'•'*len(variant))
            return mask(value)
        if isinstance(value,list):return [redact(v) for v in value]
        if isinstance(value,dict):return {k:redact(v) for k,v in value.items()}
        return value
    return redact(output)


def alignment(c):
    """Plan-decision-execution consistency of one call."""
    facts = c.get('decision_facts') or {}
    verdict = c.get('verdict')
    held = verdict in ('ASK', 'BLOCK')
    if not verdict:
        return 'pending'
    if c.get('approval_status')=='approved_once' and not held:
        return 'human_approved'
    if c.get('rule_id') == 'TOOL-ARGUMENT-INVALID' and not c.get('executed'):
        return 'parameter_rejected'
    if c.get('rule_id') == 'POL-TOOL-BUDGET' and not c.get('executed'):
        return 'budget_stopped'
    if c.get('rule_id') == 'DT-4b' and held and not c.get('executed'):
        return 'confirmation_stopped'
    if c.get('in_scope') and not held:
        return 'in_plan'
    if facts.get('low_risk') and not held:
        return 'off_plan_low'
    if facts.get('directive') or any(i.get('by') == 'rule' for i in c.get('induced_by', [])) or (facts.get('high_risk') and facts.get('request_tainted')):
        return ('induced_stopped' if held else 'pending') if not c.get('executed') else 'induced_executed'
    if held:
        return 'deviation_stopped' if not c.get('executed') else 'deviation_executed'
    if facts.get('high_risk'):
        return 'off_plan_allowed'
    if facts.get('low_risk'):
        return 'off_plan_low'
    return 'unclassified'



def build_graph(task, agents, calls, sources):
    """Layered DAG: trigger sources -> agents -> tool calls -> affected targets."""
    nodes, edges = {}, []

    def node(nid, layer, kind, label, **extra):
        nodes.setdefault(nid, {'id': nid, 'layer': layer, 'kind': kind, 'label': label, **extra})

    node('user', 0, 'user', '用户任务', detail=short(task, 120))
    for a in agents.values():
        node('agent:' + a['id'], 1, 'agent', a['label'])
    edges.append({'from': 'user', 'to': 'agent:main', 'kind': 'task'})
    for a in agents.values():
        if a['parent']:
            edges.append({'from': 'agent:' + a['parent'], 'to': 'agent:' + a['id'], 'kind': 'spawn'})
    for s in sources.values():
        sid = 'src:' + s['event_id']
        node(sid, 0, 'source', f"{s['kind']}：{s['uri']}", source_type=s['type'],evidence_ref=s.get('evidence_ref'),
             s1=(s.get('s1') or {}).get('label') if isinstance(s.get('s1'), dict) else None)
        edges.append({'from': sid, 'to': 'agent:' + (s['agent'] or 'main'), 'kind': 'ingest'})
        if s['type'] in {'MCP_DESC','MCP_RET'} and str(s['uri']).startswith('mcp://'):
            from urllib.parse import urlsplit
            uri=urlsplit(s['uri']);server='mcp-server:'+uri.netloc;tool='mcp-tool:'+uri.netloc+uri.path
            node(server,0,'mcp_server',uri.netloc)
            node(tool,0,'mcp_tool',uri.path.lstrip('/'))
            edges.extend([{'from':server,'to':tool,'kind':'provides'}, {'from':tool,'to':sid,'kind':'mcp_observation'}])

    for c in calls.values():
        cid = 'call:' + c['call_id']
        node(cid, 2, 'call', f"{c['op']} {short(c['target'], 48)}", verdict=c.get('verdict'),
             would_verdict=c.get('would_verdict'), rule_id=c.get('rule_id'),
             executed=c.get('executed'),approval_status=c.get('approval_status'))
        edges.append({'from': 'agent:' + c['agent'], 'to': cid, 'kind': 'propose'})
        for i in c.get('induced_by', []):
            if 'src:' + i['event_id'] in nodes:
                edges.append({'from': 'src:' + i['event_id'], 'to': cid, 'kind': 'induce_' + i['by']})
        if c.get('child'):
            edges.append({'from': cid, 'to': 'agent:' + c['child'], 'kind': 'spawn'})
        elif c.get('target') and c['op'] not in ('spawn',):
            tid = 'target:' + c['target']
            node(tid, 3, 'target', short(c['target'], 48), op=c['op'])
            edges.append({'from': cid, 'to': tid, 'kind': 'effect' if c.get('executed') else 'prevented'})
    # Collapse duplicate edges.
    seen, unique = set(), []
    for e in edges:
        key = (e['from'], e['to'], e['kind'])
        if key not in seen and e['from'] in nodes and e['to'] in nodes:
            seen.add(key)
            unique.append(e)
    return {'nodes': list(nodes.values()), 'edges': unique, 'acyclic': is_acyclic(nodes, unique)}


def is_acyclic(nodes, edges):
    out = {n: [] for n in nodes}
    for e in edges:
        out[e['from']].append(e['to'])
    state = {}

    def visit(n):
        state[n] = 1
        for m in out[n]:
            if state.get(m) == 1 or (m not in state and not visit(m)):
                return False
        state[n] = 2
        return True

    return all(state.get(n) == 2 or visit(n) for n in nodes)


def build_impact(calls, result):
    files_read, files_written, net, held, blocked = set(), set(), set(), [], []
    repositories,credentials=set(),set()
    for c in calls.values():
        if c.get('verdict') == 'ASK' and not c.get('executed'):
            held.append(c['call_id'])
        if c.get('verdict') == 'BLOCK':
            blocked.append(c['call_id'])
        if not c.get('executed'):
            continue
        if c['op'].startswith('git.'):
            repositories.add(c['target'])
        if (c.get('decision_facts') or {}).get('sensitive'):
            credentials.add(c['target'])
        if c['op'] in ('fs.read', 'memory.read'):
            files_read.add(c['target'])
        elif c['op'] in ('fs.write', 'memory.write'):
            files_written.add(c['target'])
        elif c['op'] == 'net.fetch':
            net.add(c['target'])
    return {'files_read': sorted(files_read), 'files_written': sorted(files_written), 'network': sorted(net),
            'repositories': sorted(repositories), 'sensitive_assets_accessed': sorted(credentials),
            'asked': len(held), 'blocked': len(blocked), 'received_bytes': result.get('received_bytes')}


VERDICT_ZH = {'ALLOW': '放行', 'ASK': '挂起等待用户确认', 'BLOCK': '强制阻断'}


def template_report(task, c, sources):
    """Deterministic analysis text built only from recorded facts (design §7 template)."""
    verdict = c.get('would_verdict') or c.get('verdict')
    if c.get('verdict') not in ('ASK', 'BLOCK'):
        return None
    parts = [f"用户原始请求为“{short(task, 120)}”。"]
    src_bits, grouped = [], {}
    for i in c.get('induced_by', []):
        grouped.setdefault(i['event_id'], []).append(i)
    for ev_id, items in list(grouped.items())[:2]:
        src = sources.get(ev_id)
        if src:
            quotes = [f"“{i['excerpt']}”" for i in items if i.get('excerpt')][:2]
            quote = '，其中' + '、'.join(quotes) if quotes else ''
            src_bits.append(f"{src['kind']} {src['uri']}（事件 {ev_id[:8]}）{quote}")
    if src_bits:
        parts.append('Agent 读取了' + '；'.join(src_bits) + '。')
    parts.append(f"随后提出 {c['op']} {c['target']}。")
    facts = c.get('decision_facts') or {}
    why = []
    if facts.get('literal_scope') is False:
        why.append('不在用户字面授权内')
    if facts.get('sensitive'):
        why.append('目标为敏感资产')
    if facts.get('directive'):
        why.append('与外部内容中的指令目标一致')
    if facts.get('secret_hit'):
        why.append('参数命中机密指纹')
    if facts.get('untrusted_sink'):
        why.append('目标为不可信外发出口')
    if why:
        parts.append('该动作' + '、'.join(why) + '。')
    if verdict != c.get('verdict'):
        parts.append(f"依据规则 {c.get('rule_id')}（风险 {c.get('risk')}）应{VERDICT_ZH.get(verdict, verdict)}；"
                     f"本轮防护关闭，调用{'已执行' if c.get('executed') else '未执行'}。")
    else:
        parts.append(f"依据规则 {c.get('rule_id')}（风险 {c.get('risk')}）{VERDICT_ZH.get(verdict, verdict)}，"
                     f"{'调用未执行' if not c.get('executed') else '调用已执行'}。")
    return ''.join(parts)





def enrich_graph(graph, timeline, events, calls):
    """Extend the existing console DAG, keeping observed flow distinct from causality."""
    nodes=graph['nodes'];edges=graph['edges'];ids={n['id'] for n in nodes}
    def add(nid,kind,label,layer,**data):
        if nid not in ids:nodes.append(dict(id=nid,kind=kind,label=label,layer=layer,**data));ids.add(nid)
    for row in timeline:
        if row['kind']=='model_request':
            nid='model:'+str(row['seq'])
            add(nid,'model_request',row['title'],2,seq=row['seq'])
            edges.append({'from':'agent:'+row['agent'],'to':nid,'kind':'request'})
    for cid,c in calls.items():
        source='call:'+cid
        requests=[row for row in timeline if row['kind']=='model_request' and row['agent']==c['agent'] and row.get('seq') is not None and c.get('seq') is not None and row['seq']<c['seq']]
        if requests:edges.append({'from':'model:'+str(requests[-1]['seq']),'to':source,'kind':'proposal_after_request'})
        if c.get('verdict'):
            did='decision:'+cid
            add(did,'decision',c['verdict']+' '+str(c.get('rule_id')),3,rule_id=c.get('rule_id'),evidence_refs=c.get('evidence_refs',[]))
            edges.append({'from':source,'to':did,'kind':'decision'})
            if c.get('executed'):
                rid='result:'+cid
                add(rid,'execution_result',c.get('result_excerpt','执行结果待返回'),4,is_error=c.get('is_error'))
                edges.append({'from':did,'to':rid,'kind':'execution'})
        if c['op']=='mcp.call':
            mid='mcp:'+cid
            add(mid,'mcp',c['target'],3)
            edges.append({'from':source,'to':mid,'kind':'mcp_dispatch' if c.get('executed') else 'proposed_mcp'})
    for edge in edges:
        if edge['kind'].startswith('induce_'):edge['causal_strength']='association'
    graph['acyclic']=is_acyclic(ids,edges)
    graph['causality_note']='关联不等于诱导证实；未执行反事实重放。'


def upstream_sources(graph,call_id):
    """Reverse evidence reachability; association is not a causal claim."""
    reverse={}
    for edge in graph['edges']:reverse.setdefault(edge['to'],[]).append(edge['from'])
    todo=['call:'+call_id];seen=set()
    while todo:
        node=todo.pop()
        if node in seen:continue
        seen.add(node);todo.extend(reverse.get(node,[]))
    return sorted(node[4:] for node in seen if node.startswith('src:'))
