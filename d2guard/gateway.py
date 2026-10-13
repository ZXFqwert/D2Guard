"""
部件 2: API 侧网关 (模型进出观测哨)
定位：Agent 与外部大模型 API (DeepSeek-v3.2) 之间的透明代理与审计网关。
职责：
1. 拦截出境 Prompt 请求，防止本地敏感密钥通过对话泄露给模型服务商；
2. 捕获模型回传的响应及候选工具调用 (MODEL_PROPOSED 阶段)；
3. 将包含 call_id 的模型意图上报防护内核进行预登记与生命周期对齐；
4. 保障透明转发，不改变模型标准接口协议。
"""

from __future__ import annotations
import json
import os
import time
import uuid
from typing import Any, Dict, List, Optional
from openai import OpenAI

from .core import D2GuardCore
from .models import CallLifecycleStage, D2Event


class ModelAPIGateway:
    """API 侧观测哨网关"""

    def __init__(
        self,
        core: D2GuardCore,
        real_client: Optional[OpenAI] = None
    ):
        self.core = core
        self.real_client = real_client or OpenAI(
            api_key=os.getenv("LLM_API_KEY"),
            base_url=os.getenv("LLM_BASE_URL", "https://api.huiyan-ai.cn/v1")
        )

    def chat_completion(
        self,
        model: str,
        messages: List[Dict[str, str]],
        tools: Optional[List[dict]] = None,
        temperature: float = 0.0,
        max_tokens: int = 1000,
        **kwargs
    ) -> Any:
        """
        中继转发与进出审计
        """
        # 1. 审计出境消息中的敏感信息
        prompt_parts = []
        for m in messages:
            if isinstance(m, dict):
                c = m.get("content", "") or ""
            else:
                c = getattr(m, "content", "") or ""
            if isinstance(c, str):
                prompt_parts.append(c)
        all_prompt_text = " ".join(prompt_parts)

        outbound_event = D2Event(
            event_id=f"EVT-GW-OUT-{uuid.uuid4().hex[:6]}",
            timestamp=time.time(),
            session_id=self.core.session_id,
            agent_id="main",
            stage=CallLifecycleStage.MODEL_PROPOSED,
            event_type="PROMPT_OUTBOUND",
            source_type="USER",
            raw_content=all_prompt_text
        )
        gw_check = self.core.handle_gateway_event(outbound_event)

        # 若网关要求脱敏，替换请求内容
        if gw_check.get("action") == "SANITIZE":
            redacted_content = gw_check.get("sanitized_content", "[REDACTED]")
            for m in messages:
                for sec in self.core.state.read_secrets.values():
                    if isinstance(m, dict):
                        if sec.exact_text in m.get("content", ""):
                            m["content"] = m["content"].replace(sec.exact_text, redacted_content)
                    else:
                        if hasattr(m, "content") and m.content and sec.exact_text in m.content:
                            m.content = m.content.replace(sec.exact_text, redacted_content)

        # 2. 调用外部大模型
        response = self.real_client.chat.completions.create(
            model=model,
            messages=messages,
            tools=tools if tools else None,
            temperature=temperature,
            max_tokens=max_tokens,
            **kwargs
        )

        # 3. 审计模型回传内容及候选工具调用
        choice = response.choices[0]
        msg = choice.message
        content = msg.content or ""
        tool_calls = getattr(msg, "tool_calls", None)

        if tool_calls:
            for tc in tool_calls:
                fn_name = tc.function.name
                try:
                    fn_args = json.loads(tc.function.arguments)
                except Exception:
                    fn_args = {"raw_args": tc.function.arguments}

                # 记录 MODEL_PROPOSED 阶段事件
                model_proposed_event = D2Event(
                    event_id=f"EVT-GW-IN-{uuid.uuid4().hex[:6]}",
                    timestamp=time.time(),
                    session_id=self.core.session_id,
                    agent_id="main",
                    call_id=tc.id,
                    stage=CallLifecycleStage.MODEL_PROPOSED,
                    event_type="TOOL_CALL_PROPOSED",
                    tool_name=fn_name,
                    tool_args=fn_args,
                    source_type="MODEL",
                    raw_content=tc.function.arguments
                )
                self.core.handle_gateway_event(model_proposed_event)
        elif content:
            # 记录模型纯文本响应
            model_resp_event = D2Event(
                event_id=f"EVT-GW-IN-{uuid.uuid4().hex[:6]}",
                timestamp=time.time(),
                session_id=self.core.session_id,
                agent_id="main",
                stage=CallLifecycleStage.MODEL_PROPOSED,
                event_type="LLM_OUTPUT",
                source_type="MODEL",
                raw_content=content
            )
            self.core.handle_gateway_event(model_resp_event)

        return response
