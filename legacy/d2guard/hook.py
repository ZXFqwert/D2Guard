"""Tool brake: ASK suspends; only an atomically consumed grant resumes execution."""
from __future__ import annotations
import copy
import secrets
import threading
import time
from dataclasses import asdict
from .models import CallLifecycleStage, D2Event, VerdictType

class ToolHook:
    def __init__(self, core, agent_id="main", user_prompt_callback=None):
        self.core, self.agent_id = core, agent_id
        self.user_prompt_callback = user_prompt_callback
        self._pending, self._lock = {}, threading.RLock()

    def _reply(self, verdict):
        return {"success": False, "blocked": verdict.verdict == VerdictType.BLOCK,
                "pending": verdict.verdict == VerdictType.ASK, "verdict": verdict.verdict.value,
                "reason": verdict.reason, "policy_id": verdict.policy_id,
                "output": f"[D2Guard {verdict.verdict.value}] {verdict.reason}",
                "approval_token": asdict(verdict.approval_token) if verdict.approval_token else None,
                "fast_mirror": verdict.fast_mirror_signals,
                "slow_mirror": verdict.evidence_summary, "guard_latency_ms": verdict.guard_latency_ms}

    def _execute(self, event, func, verdict):
        start = time.perf_counter()
        try:
            result, success = func(**copy.deepcopy(event.tool_args)), True
        except Exception as exc:
            result, success = f"工具执行失败: {type(exc).__name__}: {exc}", False
        result = self.core.redactor().payload(result) if not success else result
        self.core.handle_hook_post_exec(D2Event(event_id="post-" + secrets.token_hex(12),
            timestamp=time.time(), session_id=self.core.session_id, agent_id=self.agent_id,
            call_id=event.call_id, stage=CallLifecycleStage.TOOL_POST_EXEC, event_type="TOOL_RETURN",
            tool_name=event.tool_name, tool_args=event.tool_args, tool_result=result,
            source_type=event.source_type, raw_content=str(result), parent_event_id=event.event_id,
            success=success))
        reply = self._reply(verdict)
        reply.update(success=success, blocked=False, pending=False, output=result,
                     execution_ms=(time.perf_counter() - start) * 1000)
        return reply

    def execute_with_guard(self, tool_name, tool_args, tool_func, call_id=None, source_type="LOCAL_FILE"):
        event = D2Event(event_id="pre-" + secrets.token_hex(12), timestamp=time.time(),
            session_id=self.core.session_id, agent_id=self.agent_id,
            call_id=call_id or secrets.token_hex(16), stage=CallLifecycleStage.TOOL_PRE_EXEC,
            event_type="TOOL_CALL", tool_name=tool_name, tool_args=copy.deepcopy(tool_args),
            source_type=source_type, raw_content=str(tool_args))
        verdict = self.core.handle_hook_pre_exec(event)
        if verdict.verdict == VerdictType.ASK:
            token = verdict.approval_token
            with self._lock:
                self._pending[token.token_id] = (copy.deepcopy(event), tool_func, copy.deepcopy(token))
            if self.user_prompt_callback:
                if self.user_prompt_callback(copy.deepcopy(token), verdict.reason):
                    self.core.approve_token(token.token_id, self.core.principal_id)
                    return self.resume(token.token_id, self.core.principal_id)
                self.core.reject_token(token.token_id, self.core.principal_id)
                with self._lock: self._pending.pop(token.token_id,None)
                verdict.verdict=VerdictType.BLOCK
                verdict.reason="操作员拒绝单次授权"
            return self._reply(verdict)
        if verdict.verdict == VerdictType.BLOCK:
            return self._reply(verdict)
        return self._execute(event, tool_func, verdict)

    def resume(self, token_id, principal_id):
        with self._lock:
            item = self._pending.get(token_id)
            snapshot = self.core.active_tokens.get(token_id)
            if not item or not snapshot or snapshot.status != "APPROVED" or principal_id != self.core.principal_id:
                return {"success": False, "blocked": True, "pending": False, "verdict": "BLOCK",
                        "output": "审批未批准、已拒绝/消费或主体不匹配"}
            event, func, token = item
            del self._pending[token_id]
            verdict = self.core.handle_hook_pre_exec(event, token, principal_id)
            if verdict.verdict != VerdictType.ALLOW:
                return self._reply(verdict)
            return self._execute(event, func, verdict)
