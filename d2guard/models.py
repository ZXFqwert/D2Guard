"""
D²Guard 核心数据结构模型规范
包含事件定义、状态聚合结构、提取数据、三态裁决与审批令牌
"""

from __future__ import annotations
import hashlib
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional, Set, Tuple


class CallLifecycleStage(str, Enum):
    """调用生命周期阶段（用于网关与Hook对齐与去重）"""
    MODEL_PROPOSED = "MODEL_PROPOSED"  # 网关记录: 模型提出的候选意图，尚未执行
    TOOL_PRE_EXEC = "TOOL_PRE_EXEC"    # Hook 记录: 实际准备执行，申请内核决策
    TOOL_POST_EXEC = "TOOL_POST_EXEC"  # Hook 记录: 工具真实执行结束返回数据


class VerdictType(str, Enum):
    """三态裁决"""
    ALLOW = "ALLOW"
    ASK = "ASK"
    BLOCK = "BLOCK"


@dataclass
class ApprovalToken:
    """ASK 机制单次授权令牌（单次单动作绑定，防扩散）"""
    token_id: str
    call_id: str
    args_hash: str
    created_at: float = field(default_factory=time.time)
    ttl_seconds: float = 60.0
    status: str = "PENDING"  # PENDING, APPROVED, REJECTED, EXPIRED

    def is_valid_for(self, call_id: str, tool_args: dict) -> bool:
        if self.status != "APPROVED":
            return False
        if time.time() - self.created_at > self.ttl_seconds:
            self.status = "EXPIRED"
            return False
        curr_hash = hashlib.sha256(str(sorted(tool_args.items())).encode()).hexdigest()
        return self.call_id == call_id and self.args_hash == curr_hash


@dataclass
class D2Event:
    """增量事件规范 (D2Event Schema)"""
    event_id: str                          # 全局唯一编号 (EVT-001)
    timestamp: float                       # 事件产生时间戳
    session_id: str                        # 会话 ID
    agent_id: str                          # "main" 或 "sub_1"
    call_id: Optional[str] = None          # 工具调用唯一 ID
    stage: CallLifecycleStage = CallLifecycleStage.TOOL_PRE_EXEC
    event_type: str = "TOOL_CALL"          # USER_INPUT / TOOL_CALL / TOOL_RETURN / SUBAGENT_SPAWN
    tool_name: Optional[str] = None
    tool_args: dict = field(default_factory=dict)
    tool_result: Optional[Any] = None
    source_type: str = "USER"              # USER / WEB / LOCAL_FILE / MCP / MEMORY / MODEL
    raw_content: str = ""
    char_span: Tuple[int, int] = (0, 0)    # 原始字符区间 (start, end)
    token_span: Tuple[int, int] = (0, 0)   # 分词器 Token 序号区间 (token_start, token_end)
    parent_event_id: Optional[str] = None  # 上游因果父事件 ID


@dataclass
class SecretRecord:
    """敏感数据登记薄条目（明文、Base64 与滑动分片）"""
    secret_id: str                         # SEC-001
    source_path: str                       # ".env", "id_rsa"
    source_event_id: str                   # 读入该秘密的事件 ID
    exact_text: str                        # 完整明文 (如 "sk-1234567890abcdef")
    base64_text: str                       # 预存 Base64 编码
    sub_chunks: List[str]                  # 8 字节滑动子片段列表


@dataclass
class DomainOutboundHistory:
    """域名累计外发记录（用于多轮分片外发追踪）"""
    domain: str
    matched_chunk_set: Set[str] = field(default_factory=set)
    request_count: int = 0
    last_timestamp: float = field(default_factory=time.time)
    accumulated_bytes: int = 0


@dataclass
class CallRelation:
    """调用拓扑边"""
    caller: str
    callee: str
    call_id: str
    action: str
    timestamp: float = field(default_factory=time.time)


@dataclass
class RiskItem:
    """未解决风险疑点"""
    risk_id: str
    level: str  # LOW, MEDIUM, HIGH, CRITICAL
    description: str
    evidence_event_ids: List[str] = field(default_factory=list)


@dataclass
class SecurityState:
    """安全状态聚合机核心状态 (轻量防膨胀，内存目标 < 100KB)"""
    session_id: str
    initial_task: str                                          # 用户初始任务原话 (不可篡改锚点)
    initial_task_type: str = "general"                         # 任务类型: general / code_review / deploy 等
    effective_permissions: Dict[str, Any] = field(default_factory=dict)  # 白名单路径、白名单域名等
    read_secrets: Dict[str, SecretRecord] = field(default_factory=dict)  # 已读敏感数据登记薄
    call_graph: List[CallRelation] = field(default_factory=list)         # 因果拓扑图
    accumulated_outbound: Dict[str, DomainOutboundHistory] = field(default_factory=dict) # 累计外发分片记录
    pending_risks: List[RiskItem] = field(default_factory=list)         # 未解决风险
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class ExtractedData:
    """接口一 extract(event) 输出的结构化数据"""
    event_id: str
    file_paths: List[str] = field(default_factory=list)
    domains: List[str] = field(default_factory=list)
    ast_info: Optional[Dict[str, Any]] = None
    found_secrets: List[str] = field(default_factory=list)
    fast_mirror_signals: Dict[str, Any] = field(default_factory=dict)
    # fast_mirror_signals 包含:
    # - text_nature: 'informational' | 'directive' | 'example' | 'uncertain'
    # - action_compliance: 'expected' | 'ancillary' | 'deviant' | 'insufficient'
    # - risk_score: float (0.0 - 1.0)


@dataclass
class ActionVerdict:
    """接口三 decide(state, proposed_action) 裁决结果"""
    verdict: VerdictType
    policy_id: Optional[str] = None
    reason: str = ""
    approval_token: Optional[ApprovalToken] = None
    evidence_summary: Optional[Dict[str, Any]] = None
    is_chunked_leak: bool = False
    is_partial_leak: bool = False
