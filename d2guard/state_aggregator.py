"""
接口二：update_state(state, extracted, event) -> SecurityState
安全状态聚合机职责：
1. 维护初始任务不可篡改锚点 (initial_task)，防止长文本与对抗提示稀释；
2. 敏感数据登记薄 (read_secrets)：记录已读敏感文件及内容、预存 Base64 与 8 字节分片滑动窗口；
3. 追踪各域名的累计外发分片记录 (accumulated_outbound)，实现多轮分片外发精准识别与熔断；
4. 维护因果拓扑图 (call_graph) 与未解决风险队列 (pending_risks)；
5. 内存防膨胀：仅存储特征、哈希、元数据与事件引用，内存控制在 < 100KB。
"""

from __future__ import annotations
import base64
import time
from typing import Dict, List, Set
from .models import (
    CallLifecycleStage,
    CallRelation,
    D2Event,
    DomainOutboundHistory,
    ExtractedData,
    RiskItem,
    SecretRecord,
    SecurityState,
)


def generate_sub_chunks(text: str, chunk_size: int = 8) -> List[str]:
    """生成滑动子片段（用于多轮分片外发检测）"""
    if not text or len(text) < chunk_size:
        return [text] if text else []
    chunks = set()
    for i in range(len(text) - chunk_size + 1):
        chunks.add(text[i:i + chunk_size])
    return list(chunks)


class StateAggregator:
    """安全状态聚合机"""

    @classmethod
    def create_initial_state(
        cls,
        session_id: str,
        initial_task: str,
        initial_task_type: str = "general",
        effective_permissions: dict = None
    ) -> SecurityState:
        """根据用户第一条输入初始化安全状态锚点"""
        perms = effective_permissions or {
            "allowed_paths": ["./", "/workspace", "./dist", "./build"],
            "trusted_domains": ["api.trusted.com", "huggingface.co", "github.com", "pypi.org"]
        }
        return SecurityState(
            session_id=session_id,
            initial_task=initial_task,
            initial_task_type=initial_task_type,
            effective_permissions=perms,
            read_secrets={},
            call_graph=[],
            accumulated_outbound={},
            pending_risks=[],
            metadata={"created_at": time.time(), "event_count": 0}
        )

    @classmethod
    def update_state(
        cls,
        state: SecurityState,
        extracted: ExtractedData,
        event: D2Event
    ) -> SecurityState:
        """以增量事件与提取数据更新安全状态"""
        state.metadata["event_count"] = state.metadata.get("event_count", 0) + 1

        # 1. 过滤：若是网关上报的 MODEL_PROPOSED 阶段，仅做意图登记，不污染已读/已外发状态
        if event.stage == CallLifecycleStage.MODEL_PROPOSED:
            return state

        # 2. 登记敏感数据：若执行了 fs.read 且读取了敏感文件或发现了新私钥
        if event.tool_name == "fs.read" and event.stage == CallLifecycleStage.TOOL_POST_EXEC:
            # 工具执行返回内容在 event.tool_result 或 event.raw_content
            ret_content = str(event.tool_result or event.raw_content)
            source_file = event.tool_args.get("path", "") or event.tool_args.get("file", "")
            
            # 若包含敏感路径特征或提取出新私钥
            is_sensitive_file = any(s in source_file.lower() for s in [".env", "id_rsa", "config.json", "secret", "passwd"])
            if is_sensitive_file or extracted.found_secrets:
                # 记录登记薄
                secrets_to_record = extracted.found_secrets if extracted.found_secrets else [ret_content.strip()]
                for idx, sec in enumerate(secrets_to_record):
                    if len(sec) < 8:
                        continue
                    sec_id = f"SEC-{len(state.read_secrets) + 1:03d}"
                    b64_val = base64.b64encode(sec.encode()).decode()
                    sub_chunks = generate_sub_chunks(sec, chunk_size=8)
                    record = SecretRecord(
                        secret_id=sec_id,
                        source_path=source_file or "unknown",
                        source_event_id=event.event_id,
                        exact_text=sec,
                        base64_text=b64_val,
                        sub_chunks=sub_chunks
                    )
                    state.read_secrets[sec_id] = record

        # 3. 维护调用因果图 (Call Graph)
        if event.call_id:
            caller = event.agent_id
            callee = event.tool_name or "unknown"
            relation = CallRelation(
                caller=caller,
                callee=callee,
                call_id=event.call_id,
                action=event.event_type
            )
            state.call_graph.append(relation)
            # 防膨胀：保留最近 100 条调用关系
            if len(state.call_graph) > 100:
                state.call_graph = state.call_graph[-100:]

        # 4. 若为真实外发成功 (net.fetch TOOL_POST_EXEC)，更新累计外发记录
        if event.tool_name == "net.fetch" and event.stage == CallLifecycleStage.TOOL_POST_EXEC:
            for domain in extracted.domains:
                history = state.accumulated_outbound.get(domain)
                if not history:
                    history = DomainOutboundHistory(domain=domain)
                    state.accumulated_outbound[domain] = history
                history.request_count += 1
                history.last_timestamp = time.time()

        # 5. 更新未解决风险队列
        if extracted.fast_mirror_signals.get("risk_score", 0.0) >= 0.7:
            risk = RiskItem(
                risk_id=f"RISK-{len(state.pending_risks) + 1:03d}",
                level="HIGH" if extracted.fast_mirror_signals["risk_score"] >= 0.8 else "MEDIUM",
                description=f"快镜识别高危信号: {extracted.fast_mirror_signals.get('action_compliance')}",
                evidence_event_ids=[event.event_id]
            )
            state.pending_risks.append(risk)
            if len(state.pending_risks) > 50:
                state.pending_risks = state.pending_risks[-50:]

        return state
