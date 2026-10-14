"""Shared decision kernel and atomic, subject-bound approval registry."""
from __future__ import annotations
import copy
import hashlib
import hmac
import json
import os
import secrets
import threading
import time
from dataclasses import asdict
from .decide import PolicyDecisionEngine
from .extract import EventExtractor
from .models import ActionVerdict, ApprovalToken, CallLifecycleStage, D2Event, VerdictType
from .redaction import OutboundRedactor
from .slow_mirror import SlowMirror
from .state_aggregator import StateAggregator

class D2GuardCore:
    def __init__(self, session_id="default_session", initial_task="默认任务",
                 initial_task_type="general", log_dir=None, enable_state_aggregation=True,
                 slow_mirror_provider=None, principal_id="operator", enable_slow_mirror=True,
                 slow_mirror=None):
        self.session_id, self.principal_id = session_id, principal_id
        self.log_dir = log_dir or os.path.join(os.path.dirname(__file__), "..", "logs")
        os.makedirs(self.log_dir, exist_ok=True)
        filename = hashlib.sha256(session_id.encode()).hexdigest()[:24]
        self.event_log_path = os.path.join(self.log_dir, f"events_{filename}.jsonl")
        self.enable_state_aggregation = enable_state_aggregation
        self.slow_mirror = slow_mirror or SlowMirror(provider=slow_mirror_provider)
        self.extractor, self.aggregator = EventExtractor(), StateAggregator()
        self.decision_engine = PolicyDecisionEngine(slow_mirror=self.slow_mirror,
            enable_state_aggregation=enable_state_aggregation)
        self.decision_engine.enable_slow_mirror = enable_slow_mirror
        self.decision_engine.outbound_redactor_provider = self.redactor
        self.state = self.aggregator.create_initial_state(session_id, initial_task, initial_task_type)
        self.events, self.active_tokens, self._tokens = [], {}, {}
        self._approval_key, self._lock = secrets.token_bytes(32), threading.RLock()
        self._redactor_cache_key, self._redactor_cache = None, None

    def redactor(self):
        # Registry updates invalidate the filter; reuse compiled matching on unchanged state.
        key=(tuple((s.secret_id,s.exact_text,tuple(s.sub_chunks)) for s in self.state.read_secrets.values()),
             tuple((k,v) for k,v in os.environ.items() if k.lower().endswith(('key','secret','token','password'))))
        if key != self._redactor_cache_key:
            self._redactor_cache=OutboundRedactor.from_state(self.state)
            self._redactor_cache_key=key
        return self._redactor_cache

    def _persist_event(self, event):
        with self._lock:
            self.events.append(event)
            record = self.redactor().sanitize(asdict(event))
            with open(self.event_log_path, "a", encoding="utf-8") as stream:
                stream.write(json.dumps(record, ensure_ascii=False) + "\n")

    def register_user_task(self, initial_task, task_type="general"):
        self.state.initial_task, self.state.initial_task_type = initial_task, task_type

    def handle_gateway_event(self, event):
        self._persist_event(event)
        extracted = self.extractor.extract(event, initial_task=self.state.initial_task)
        self.state = self.aggregator.update_state(self.state, extracted, event,
            enable_aggregation=self.enable_state_aggregation)
        return {"action": "PASS"}

    def _signature(self, token):
        binding = [token.token_id, token.call_id, token.args_hash, token.session_id,
                   token.agent_id, token.principal_id, token.tool_name,
                   token.created_at, token.ttl_seconds]
        return hmac.new(self._approval_key, json.dumps(binding).encode(), hashlib.sha256).hexdigest()

    def _issue(self, token, event):
        token.session_id, token.agent_id = self.session_id, event.agent_id
        token.principal_id, token.tool_name = self.principal_id, event.tool_name
        token.signature = self._signature(token)
        self._tokens[token.token_id] = copy.deepcopy(token)
        self.active_tokens[token.token_id] = copy.deepcopy(token)

    def _consume(self, token, event, principal_id):
        saved = self._tokens.get(token.token_id)
        if not saved or principal_id != self.principal_id:
            return False
        if not hmac.compare_digest(saved.signature, self._signature(token)):
            return False
        if not saved.is_valid_for(event.call_id, event.tool_args, session_id=self.session_id,
                agent_id=event.agent_id, principal_id=principal_id, tool_name=event.tool_name):
            self.active_tokens[saved.token_id] = copy.deepcopy(saved)
            return False
        saved.status, saved.consumed_at = "CONSUMED", time.time()
        self.active_tokens[saved.token_id] = copy.deepcopy(saved)
        del self._tokens[saved.token_id]
        return True

    def handle_hook_pre_exec(self, event, approval_token=None, principal_id=None):
        with self._lock:
            start = time.perf_counter()
            self._persist_event(event)
            if approval_token and not self._consume(approval_token, event, principal_id):
                verdict = ActionVerdict(VerdictType.BLOCK, reason="审批无效、主体/参数不匹配、过期或已消费")
                extracted = None
            else:
                extracted = self.extractor.extract(event, initial_task=self.state.initial_task)
                verdict = self.decision_engine.decide(self.state,
                    {"tool_name": event.tool_name, "tool_args": event.tool_args}, extracted, event)
                if approval_token and verdict.verdict == VerdictType.ASK:
                    verdict.verdict, verdict.approval_token = VerdictType.ALLOW, None
                    verdict.reason = "主体与参数校验通过；单次审批已消费"
                if verdict.verdict == VerdictType.ASK and verdict.approval_token:
                    self._issue(verdict.approval_token, event)
            verdict.fast_mirror_signals = extracted.fast_mirror_signals if extracted else {}
            verdict.guard_latency_ms = (time.perf_counter() - start) * 1000
            self._persist_event(D2Event(event_id="decision-" + secrets.token_hex(12),
                timestamp=time.time(), session_id=self.session_id, agent_id=event.agent_id,
                call_id=event.call_id, stage=CallLifecycleStage.DECISION, event_type="DECISION",
                tool_name=event.tool_name, tool_args=event.tool_args, parent_event_id=event.event_id,
                verdict=verdict.verdict.value, policy_id=verdict.policy_id, reason=verdict.reason))
            return verdict

    def handle_hook_post_exec(self, event):
        extracted = self.extractor.extract(event, initial_task=self.state.initial_task)
        if event.success is not False:
            self.state = self.aggregator.update_state(self.state, extracted, event,
                enable_aggregation=self.enable_state_aggregation)
        self._persist_event(event)

    def _set_approval(self, token_id, principal_id, status):
        with self._lock:
            token = self._tokens.get(token_id)
            if not token or principal_id != self.principal_id or token.status != "PENDING":
                return False
            if time.time() >= token.created_at + token.ttl_seconds:
                token.status = "EXPIRED"
                self.active_tokens[token_id] = copy.deepcopy(token)
                del self._tokens[token_id]
                return False
            token.status = status
            self.active_tokens[token_id] = copy.deepcopy(token)
            self._persist_event(D2Event(event_id="approval-" + secrets.token_hex(12),
                timestamp=time.time(), session_id=self.session_id, agent_id=token.agent_id,
                call_id=token.call_id, stage=CallLifecycleStage.APPROVAL, event_type=status,
                tool_name=token.tool_name, reason="操作员单次审批", verdict=status))
            if status == "REJECTED":
                del self._tokens[token_id]
            return True

    def approve_token(self, token_id, principal_id=None):
        return self._set_approval(token_id, principal_id, "APPROVED")

    def reject_token(self, token_id, principal_id=None):
        return self._set_approval(token_id, principal_id, "REJECTED")
