"""
部件 1: 工具侧 Hook (执行刹车闸)
定位：挂在 Agent 底层工具分发入口，执行物理拦截。
职责：
1. 拦截各类底层操作：fs, net, exec, git, mcp, subagent；
2. 执行前申请裁决 (TOOL_PRE_EXEC)；
3. 执行阻断 (BLOCK)、放行 (ALLOW) 或挂起等待用户单次审批 (ASK)；
4. 执行完成后上报数据 (TOOL_POST_EXEC)，更新内核状态。
"""

from __future__ import annotations
import time
import uuid
from typing import Any, Callable, Dict, Optional

from .core import D2GuardCore
from .models import (
    ApprovalToken,
    CallLifecycleStage,
    D2Event,
    VerdictType,
)


class ToolHook:
    """工具侧 Hook 刹车闸"""

    def __init__(
        self,
        core: D2GuardCore,
        agent_id: str = "main",
        user_prompt_callback: Optional[Callable[[ApprovalToken, str], bool]] = None
    ):
        self.core = core
        self.agent_id = agent_id
        # user_prompt_callback 用于在 ASK 时与终端或用户前端交互 (token, reason) -> bool
        self.user_prompt_callback = user_prompt_callback

    def execute_with_guard(
        self,
        tool_name: str,
        tool_args: dict,
        tool_func: Callable[..., Any],
        call_id: Optional[str] = None,
        source_type: str = "LOCAL_FILE"
    ) -> Dict[str, Any]:
        """
        受 Hook 保护的工具执行入口
        """
        call_id = call_id or str(uuid.uuid4())
        pre_event_id = f"EVT-HOOK-PRE-{uuid.uuid4().hex[:6]}"

        # 1. 构建工具预执行事件 (TOOL_PRE_EXEC)
        pre_event = D2Event(
            event_id=pre_event_id,
            timestamp=time.time(),
            session_id=self.core.session_id,
            agent_id=self.agent_id,
            call_id=call_id,
            stage=CallLifecycleStage.TOOL_PRE_EXEC,
            event_type="TOOL_CALL",
            tool_name=tool_name,
            tool_args=tool_args,
            source_type=source_type,
            raw_content=str(tool_args)
        )

        # 2. 向内核申请裁决
        verdict = self.core.handle_hook_pre_exec(pre_event)

        # 3. 处理 BLOCK
        if verdict.verdict == VerdictType.BLOCK:
            return {
                "success": False,
                "blocked": True,
                "reason": verdict.reason,
                "policy_id": verdict.policy_id,
                "output": f"[D2Guard 阻断] 违反安全策略: {verdict.reason}"
            }

        # 4. 处理 ASK (挂起等待用户确认)
        if verdict.verdict == VerdictType.ASK and verdict.approval_token:
            token = verdict.approval_token
            approved = False

            # 若注册了交互回调函数，则唤起用户交互
            if self.user_prompt_callback:
                approved = self.user_prompt_callback(token, verdict.reason)
            else:
                # 默认模拟策略：在无交互前端时，根据 token 状态研判
                approved = (token.status == "APPROVED")

            if approved:
                token.status = "APPROVED"
                # 重新校验批准令牌后放行
                recheck = self.core.handle_hook_pre_exec(pre_event, approval_token=token)
                if recheck.verdict != VerdictType.ALLOW:
                    return {
                        "success": False,
                        "blocked": True,
                        "reason": f"授权校验失效: {recheck.reason}",
                        "output": f"[D2Guard 阻断] 授权令牌未通过最终核验"
                    }
            else:
                token.status = "REJECTED"
                return {
                    "success": False,
                    "blocked": True,
                    "reason": f"用户拒绝或响应超时: {verdict.reason}",
                    "output": f"[D2Guard 阻断] 用户未授权执行此破坏性操作"
                }

        # 5. 执行真实工具 (ALLOW 阶段)
        try:
            result = tool_func(**tool_args)
        except Exception as e:
            result = f"工具执行异常: {str(e)}"

        # 6. 构建并上报后执行事件 (TOOL_POST_EXEC)
        post_event_id = f"EVT-HOOK-POST-{uuid.uuid4().hex[:6]}"
        post_event = D2Event(
            event_id=post_event_id,
            timestamp=time.time(),
            session_id=self.core.session_id,
            agent_id=self.agent_id,
            call_id=call_id,
            stage=CallLifecycleStage.TOOL_POST_EXEC,
            event_type="TOOL_RETURN",
            tool_name=tool_name,
            tool_args=tool_args,
            tool_result=result,
            source_type=source_type,
            raw_content=str(result),
            parent_event_id=pre_event_id
        )
        self.core.handle_hook_post_exec(post_event)

        return {
            "success": True,
            "blocked": False,
            "output": result
        }
