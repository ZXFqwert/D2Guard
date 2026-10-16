"""Pi adapter for the isolated D2 kernel, with observable D1/D2 contributions.

No scenario metadata, replay runtime, desktop API or fixture oracle is imported.
ASK remains ASK: an unattended run cannot grant approval on the user's behalf.
"""
import hashlib
import json
import threading
import time
import uuid
import queue
from pathlib import Path

from d2core.extractor import extract
from d2core.mirrors import FastMirrorAdapter, SlowMirrorClient, slow_review_mode
from d2core.models import D2Event, ProposedAction, SecurityState
from d2core.policy_engine import PolicyEngine
from d2core.state_machine import build_security_chain_summary, update_state

TOOLS = {'fs_read': 'fs.read', 'fs_write': 'fs.write', 'net_fetch': 'net.fetch',
         'spawn_subagent': 'spawn_subagent'}


class CoreGuard:
    def __init__(self, enabled, folder, provider, emit):
        self.enabled, self.folder, self.emit = enabled, Path(folder), emit
        self.lock = threading.RLock()
        self.state = SecurityState(session_id=self.folder.name, armor_enabled=enabled)
        self.tasks = {}
        self.pending_approval = None
        root = Path(__file__).parent / 'd2core'
        weights = root / 'weights/laya_d2_distilled.json'
        self.fast = FastMirrorAdapter(model_path=str(weights), backend_type='laya-distilled')
        if not self.fast.model_loaded:
            raise RuntimeError('D1 checkpoint did not load; refusing silent heuristic-only deployment')
        self.slow = SlowMirrorClient(provider['base_url'], provider['api_key'], provider['main_model'],
                                     timeout=30, api_style=provider['api_style'])
        self.engine = PolicyEngine(root / 'policies.yaml', self.folder / 'workspace', self.fast, self.slow)
        self.reviews = queue.Queue(maxsize=8)
        threading.Thread(target=self._review_worker, name='d2-slow-audit', daemon=True).start()
        emit('core.jsonl', {'type': 'core_started', 'engine': 'd2core', 'protection': enabled,
                           'fast_checkpoint_sha256': hashlib.sha256(weights.read_bytes()).hexdigest(),
                           'fast_loaded': self.fast.model_loaded, 'slow_model': self.slow.model,
                           'slow_role': 'advisory_only', 'span_unit': 'regex_lexical_units_not_model_tokens'})

    def _review_worker(self):
        while True:
            state, verdict = self.reviews.get()
            start = time.perf_counter()
            slow_review_mode.set('not_triggered')
            try:
                self.engine.enrich_report(state, verdict)
                self.emit('core.jsonl', {'type': 'slow_review_completed', 'call_id': verdict.call_id,
                    'mode': slow_review_mode.get(), 'role': 'advisory_only',
                    'latency_ms': (time.perf_counter() - start) * 1000,
                    'report': verdict.explainable_report, 'changes_verdict': False})
            except Exception as exc:
                self.emit('core.jsonl', {'type': 'slow_review_failed', 'call_id': verdict.call_id,
                    'error_type': type(exc).__name__, 'changes_verdict': False})
            finally:
                self.reviews.task_done()

    def drain(self, timeout=32):
        """After Pi has finished, optionally retain outstanding advisory evidence."""
        deadline = time.monotonic() + timeout
        while self.reviews.unfinished_tasks and time.monotonic() < deadline:
            time.sleep(.05)
        pending = self.reviews.unfinished_tasks
        self.emit('core.jsonl', {'type': 'review_drain', 'pending_reviews': pending})
        return {'pending_reviews': pending}

    def chain(self, tool='', agent='main'):
        return build_security_chain_summary(self.state, tool_name=tool, agent_id=agent)

    def snapshot(self):
        data = self.state.telemetry().model_dump(mode='json', by_alias=True)
        data['outbound_semantics'] = 'attempted/proposed exposure, not collector receipts'
        data['span_unit'] = 'regex_lexical_units_not_model_tokens'
        (self.folder / 'core-telemetry.json').write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding='utf-8')

    def observe(self, event):
        with self.lock:
            kind, agent = event.get('type'), event.get('agent_id', 'main')
            if kind == 'agent_start':
                self.tasks[agent] = event['task']
                if agent != 'main':
                    return
                stage, event_type, source, uri, raw, tool, args = (
                    'MODEL_PROPOSED', 'USER_INPUT', 'USER', 'user://task', event['task'], '', {})
            elif kind == 'tool_result' and not event.get('is_error'):
                tool = TOOLS[event['tool']]
                args, raw = event['args'], event.get('text', '')
                stage, event_type = 'TOOL_POST_EXEC', 'TOOL_RETURN'
                source = 'WEB' if tool == 'net.fetch' else 'LOCAL_FILE'
                uri = args.get('path') or args.get('url') or 'agent://result'
            else:
                return
            call_id = event.get('call_id') or 'user-' + uuid.uuid4().hex
            parent = self.state.calls.get(event.get('parent_call_id'))
            dto = D2Event(event_id=uuid.uuid4().hex, session_id=self.state.session_id,
                timestamp=time.time(), agent_id=agent, parent_agent_id=parent.agent_id if parent else None,
                call_id=call_id, stage=stage, event_type=event_type, source_type=source,
                source_uri=uri, raw_content=raw, current_plan='', tool_name=tool, tool_args=args)
            before = self.chain(tool, agent)
            extracted = extract(dto, self.fast, before)
            self.state = update_state(self.state, extracted)
            after = self.chain(tool, agent)
            self.emit('core.jsonl', {'type': 'core_ingest', 'call_id': call_id, 'agent_id': agent,
                'source_uri': uri, 'source_type': source, 'event_type': event_type,
                'char_span': extracted.char_span, 'lexical_span': extracted.token_span,
                'raw_sha256': hashlib.sha256(raw.encode()).hexdigest(),
                'detected_secrets_count': extracted.detected_secrets_count,
                'fast': self.fast.last_trace, 'state_before': before, 'state_after': after})
            self.snapshot()

    def decide(self, tool, args, context):
        with self.lock:
            name, agent = TOOLS[tool], context.get('agent_id', 'main')
            action = ProposedAction(session_id=self.state.session_id, call_id=context['call_id'],
                agent_id=agent, tool_name=name, tool_args=args, current_plan='')
            before = self.chain(name, agent)
            if self.pending_approval:
                result = {**self.pending_approval, 'inherited_session_hold': True,
                          'slow': {'triggered': False, 'mode': 'not_triggered', 'role': 'advisory_only', 'synchronous_wait_ms': 0}}
                self.emit('core.jsonl', {'type': 'core_session_hold', 'call_id': action.call_id,
                    'agent_id': agent, 'tool': name, **result})
                return result
            verdict = self.engine.decide(self.state, action, review=False)
            fast = dict(self.fast.last_trace)
            local_report = verdict.explainable_report
            slow = {'triggered': verdict.slow_mirror_triggered, 'mode': 'not_triggered',
                    'role': 'advisory_only', 'synchronous_wait_ms': 0}
            if verdict.slow_mirror_triggered:
                try:
                    self.reviews.put_nowait((self.state.model_copy(deep=True), verdict.model_copy(deep=True)))
                    slow['mode'] = 'queued'
                except queue.Full:
                    slow['mode'] = 'queue_full_local_explanation'
            after = self.chain(name, agent)
            result = {'verdict': verdict.verdict.value, 'policy': verdict.matched_policy_id,
                'would_block': bool(verdict.matched_policy_id),
                'reason': verdict.explainable_report,
                'evidence': {'source_uri': verdict.source_uri, 'char_span': verdict.char_span,
                             'lexical_span': verdict.token_span, 'state_chain': after},
                'engine': 'd2core', 'fast': fast, 'slow': slow,
                'approval_status': 'pending' if verdict.verdict.value == 'ASK' else 'not_required'}
            if verdict.verdict.value == 'ASK':
                result['approval_origin_call_id'] = action.call_id
                self.pending_approval = dict(result)
            self.emit('core.jsonl', {'type': 'core_decision', 'call_id': action.call_id,
                'agent_id': agent, 'tool': name, 'state_before': before, 'state_after': after,
                'local_report': local_report, **result})
            self.snapshot()
            return result
