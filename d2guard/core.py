"""
部件 3: 共享防护内核 (D²Guard Core)
定位：中央决策大脑与数据状态中枢。
职责：
1. 增量事件流持久化 (EventStore)；
2. 调度三大接口：extract(event) -> update_state(state, extracted) -> decide(state, proposed_action)；
3. 处理网关上报的 Prompt 与候选调用；
4. 处理 Hook 上报的工具预执行裁决与后执行状态回填；
5. 管理 ASK 机制的一次性审批令牌；
6. 支持消融实验配置 (enable_state_aggregation) 与多 LLM 提供方配置。
"""

from __future__ import annotations
import json
import os
import time
from typing import Any, Dict, List, Optional

from .decide import PolicyDecisionEngine
from .extract import EventExtractor
from .models import (
    ActionVerdict,
    ApprovalToken,
    CallLifecycleStage,
    D2Event,
    ExtractedData,
    SecurityState,
    VerdictType,
)
from .slow_mirror import SlowMirror
from .state_aggregator import StateAggregator


class D2GuardCore:
    """D²Guard 共享防护内核"""

    def __init__(
        self,
        session_id: str = "default_session",
        initial_task: str = "默认任务",
        initial_task_type: str = "general",
        log_dir: Optional[str] = None,
        enable_state_aggregation: bool = True,
        slow_mirror_provider: Optional[str] = None
    ):
        self.session_id = session_id
        self.log_dir = log_dir or os.path.join(os.path.dirname(__file__), "..", "logs")
        os.makedirs(self.log_dir, exist_ok=True)
        self.event_log_path = os.path.join(self.log_dir, f"events_{session_id}.jsonl")
        self.enable_state_aggregation = enable_state_aggregation

        # 慢镜裁判
        self.slow_mirror = SlowMirror(provider=slow_mirror_provider)

        # 核心三大接口实例
        self.extractor = EventExtractor()
        self.aggregator = StateAggregator()
        self.decision_engine = PolicyDecisionEngine(
            slow_mirror=self.slow_mirror,
            enable_state_aggregation=enable_state_aggregation
        )

        # 初始化安全状态
        self.state = self.aggregator.create_initial_state(
            session_id=session_id,
            initial_task=initial_task,
            initial_task_type=initial_task_type
        )

        # 增量事件流历史
        self.events: List[D2Event] = []

        # 待处理与生效中的审批令牌
        self.active_tokens: Dict[str, ApprovalToken] = {}

    def _persist_event(self, event: D2Event) -> None:
        """事件持久化落盘"""
        self.events.append(event)
        record = {
            "event_id": event.event_id,
            "timestamp": event.timestamp,
            "session_id": event.session_id,
            "agent_id": event.agent_id,
            "call_id": event.call_id,
            "stage": event.stage.value if hasattr(event.stage, "value") else str(event.stage),
            "event_type": event.event_type,
            "tool_name": event.tool_name,
            "tool_args": event.tool_args,
            "source_type": event.source_type,
            "char_span": event.char_span,
            "token_span": event.token_span,
            "parent_event_id": event.parent_event_id
        }
        with open(self.event_log_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")

    def register_user_task(self, initial_task: str, task_type: str = "general") -> None:
        """更新/重设初始任务锚点（必须由合法用户通道发起）"""
        self.state.initial_task = initial_task
        self.state.initial_task_type = task_type

    def handle_gateway_event(self, event: D2Event) -> Dict[str, Any]:
        """
        部件 2 (网关) 上报的事件处理
        阶段: MODEL_PROPOSED (模型生成了新的意图/提示)
        """
        self._persist_event(event)
        extracted = self.extractor.extract(event, initial_task=self.state.initial_task)

        # 审计是否存在敏感凭据直接回传给模型（防止出境泄漏）
        has_secret_leak, _, leak_desc = self.decision_engine.check_secrets_and_chunks(
            self.state, event.raw_content
        )
        if has_secret_leak:
            return {
                "action": "SANITIZE",
                "reason": f"网关截获送往外部大模型的敏感数据: {leak_desc}",
                "sanitized_content": "[D2GUARD_REDACTED_SECRET]"
            }

        # 更新状态 (MODEL_PROPOSED 不污染敏感数据薄)
        self.state = self.aggregator.update_state(
            self.state, extracted, event,
            enable_aggregation=self.enable_state_aggregation
        )
        return {"action": "PASS"}

    def handle_hook_pre_exec(
        self,
        event: D2Event,
        approval_token: Optional[ApprovalToken] = None
    ) -> ActionVerdict:
        """
        部件 1 (Hook) 在工具执行前发起裁决申请
        阶段: TOOL_PRE_EXEC
        """
        self._persist_event(event)

        # 1. 抽取结构化事实与快镜信号
        extracted = self.extractor.extract(event, initial_task=self.state.initial_task)

        # 2. 决策中枢综合裁决
        proposed_action = {
            "tool_name": event.tool_name,
            "tool_args": event.tool_args
        }
        verdict = self.decision_engine.decide(
            state=self.state,
            proposed_action=proposed_action,
            extracted=extracted,
            event=event,
            approval_token=approval_token
        )

        # 3. 若触发 ASK，记录生成的 ApprovalToken
        if verdict.verdict == VerdictType.ASK and verdict.approval_token:
            self.active_tokens[verdict.approval_token.token_id] = verdict.approval_token

        return verdict

    def handle_hook_post_exec(self, event: D2Event) -> None:
        """
        部件 1 (Hook) 在工具执行完成后上报真实执行结果
        阶段: TOOL_POST_EXEC
        """
        self._persist_event(event)

        # 抽取并更新状态机
        extracted = self.extractor.extract(event, initial_task=self.state.initial_task)
        self.state = self.aggregator.update_state(
            self.state, extracted, event,
            enable_aggregation=self.enable_state_aggregation
        )

    def approve_token(self, token_id: str) -> bool:
        """用户人工批准单次操作令牌"""
        token = self.active_tokens.get(token_id)
        if token:
            token.status = "APPROVED"
            return True
        return False

    def reject_token(self, token_id: str) -> bool:
        """用户人工拒绝单次操作令牌"""
        token = self.active_tokens.get(token_id)
        if token:
            token.status = "REJECTED"
            return True
        return False
