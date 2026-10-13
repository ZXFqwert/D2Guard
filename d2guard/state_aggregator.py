"""
接口二：update_state(state, extracted, event) -> SecurityState
安全状态聚合机职责：
1. 维护初始任务不可篡改锚点 (initial_task)，防止长文本与对抗提示稀释；
2. 敏感数据登记薄 (read_secrets)：记录已读敏感文件及内容、预存 Base64 与 8 字节分片滑动窗口；
3. 追踪各域名的累计外发分片记录 (accumulated_outbound)，实现多轮分片外发精准识别与熔断；
4. 维护因果拓扑图 (call_graph) 与未解决风险队列 (pending_risks)；
5. 内存防膨胀：仅存储特征、哈希、元数据与事件引用，内存控制在 < 100KB；
6. 支持消融控制 (enable_aggregation)，可切换“全量状态聚合”与“仅当前增量 (Delta-Only)”。
"""

from __future__ import annotations
import base64
import re
import time
from typing import Dict, List, Set, Optional
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
        chunk = text[i:i + chunk_size]
        if chunk.strip():
            chunks.add(chunk)
    return list(chunks)


def extract_potential_secrets_from_text(text: str) -> List[str]:
    """从读取的文本中提取高危机密特征词 (密码、Token、API Key、私钥)"""
    found = set()
    if not text:
        return []

    # 1. 键值对提取: password=..., key=..., secret=..., token=...
    kv_pattern = re.compile(
        r'(?i)(?:password|passwd|secret|api[_-]?key|token|access[_-]?key|private[_-]?key)\s*[:=]\s*["\']?([^\s"\'\r\n;]+)'
    )
    for m in kv_pattern.finditer(text):
        val = m.group(1).strip()
        if len(val) >= 6:
            found.add(val)

    # 2. 常见私钥/API Key 结构提取
    sk_pattern = re.compile(r'sk-[a-zA-Z0-9_\-]{16,}')
    for m in sk_pattern.finditer(text):
        found.add(m.group(0))

    # 3. AWS Key 提取
    aws_pattern = re.compile(r'AKIA[0-9A-Z]{16}')
    for m in aws_pattern.finditer(text):
        found.add(m.group(0))

    return list(found)


class StateAggregator:
    """安全状态聚合机"""

    @classmethod
    def create_initial_state(
        cls,
        session_id: str,
        initial_task: str,
        initial_task_type: str = "general",
        effective_permissions: Optional[dict] = None
    ) -> SecurityState:
        """根据用户第一条输入初始化安全状态锚点"""
        perms = effective_permissions or {
            "allowed_paths": ["./", "/workspace", "./dist", "./build", "tests/data"],
            "trusted_domains": ["api.trusted.com", "huggingface.co", "github.com", "pypi.org", "service-hub.trusted"]
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
        event: D2Event,
        enable_aggregation: bool = True
    ) -> SecurityState:
        """
        以增量事件与提取数据更新安全状态
        enable_aggregation: 消融实验控制开关 (False 时模拟 Delta-Only 无跨轮状态聚合)
        """
        state.metadata["event_count"] = state.metadata.get("event_count", 0) + 1

        # 若处于 Delta-Only 消融模式，不累积历史敏感数据和跨轮外发特征
        if not enable_aggregation:
            return state

        # 1. 过滤：若是网关上报的 MODEL_PROPOSED 阶段，仅做意图登记，不污染已读/已外发状态
        if event.stage == CallLifecycleStage.MODEL_PROPOSED:
            return state

        # 2. 登记敏感数据：若执行了 fs.read 且读取了敏感文件或发现了新私钥
        if event.tool_name == "fs.read" and event.stage == CallLifecycleStage.TOOL_POST_EXEC:
            ret_content = str(event.tool_result or event.raw_content)
            source_file = str(event.tool_args.get("path", "") or event.tool_args.get("file", ""))
            
            is_sensitive_file = any(
                s in source_file.lower()
                for s in [".env", "id_rsa", "config.json", "secret", "passwd", "database.ini", "credentials"]
            )

            # 聚合候选秘密
            candidates_to_record = set(extracted.found_secrets)
            if is_sensitive_file:
                # 进一步从内容中分析提取键值对与特征
                extracted_kv = extract_potential_secrets_from_text(ret_content)
                candidates_to_record.update(extracted_kv)
                if not candidates_to_record and len(ret_content.strip()) >= 8:
                    candidates_to_record.add(ret_content.strip()[:200])

            for sec in candidates_to_record:
                if len(sec) < 6:
                    continue
                # 防止重复登记
                exists = any(r.exact_text == sec for r in state.read_secrets.values())
                if exists:
                    continue

                sec_id = f"SEC-{len(state.read_secrets) + 1:03d}"
                b64_val = base64.b64encode(sec.encode()).decode()
                
                # 为明文生成 8 字节子片段
                plain_chunks = generate_sub_chunks(sec, chunk_size=8)
                # 为 Base64 编码也生成滑动子片段（防 Base64 绕过）
                b64_chunks = generate_sub_chunks(b64_val, chunk_size=8)
                all_chunks = list(set(plain_chunks + b64_chunks))

                record = SecretRecord(
                    secret_id=sec_id,
                    source_path=source_file or "unknown",
                    source_event_id=event.event_id,
                    exact_text=sec,
                    base64_text=b64_val,
                    sub_chunks=all_chunks
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
                history = state.accumulated_outbound.setdefault(domain, DomainOutboundHistory(domain=domain))
                history.request_count += 1
                history.last_timestamp = time.time()

        # 5. 更新未解决风险队列
        if extracted.fast_mirror_signals.get("risk_score", 0.0) >= 0.7:
            risk = RiskItem(
                risk_id=f"RISK-{len(state.pending_risks) + 1:03d}",
                level="HIGH" if extracted.fast_mirror_signals.get("risk_score", 0.0) >= 0.8 else "MEDIUM",
                description=f"快镜识别高危信号: {extracted.fast_mirror_signals.get('action_compliance')}",
                evidence_event_ids=[event.event_id]
            )
            state.pending_risks.append(risk)
            if len(state.pending_risks) > 50:
                state.pending_risks = state.pending_risks[-50:]

        return state
