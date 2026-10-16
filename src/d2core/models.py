"""Strict contract DTOs and private persisted runtime state (Pydantic v2)."""
from __future__ import annotations

import hashlib
import json
from enum import StrEnum
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, JsonValue, StrictBool, field_validator


class Model(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True, allow_inf_nan=False)


class CallLifecycleStage(StrEnum):
    MODEL_PROPOSED = "MODEL_PROPOSED"
    TOOL_PRE_EXEC = "TOOL_PRE_EXEC"
    TOOL_POST_EXEC = "TOOL_POST_EXEC"


class EventType(StrEnum):
    USER_INPUT = "USER_INPUT"
    TOOL_CALL = "TOOL_CALL"
    TOOL_RETURN = "TOOL_RETURN"
    SUBAGENT_SPAWN = "SUBAGENT_SPAWN"
    MEMORY_RECALL = "MEMORY_RECALL"


class SourceType(StrEnum):
    USER = "USER"
    WEB = "WEB"
    LOCAL_FILE = "LOCAL_FILE"
    CODE_ISSUE = "CODE_ISSUE"
    MCP_DESC = "MCP_DESC"
    MCP_RET = "MCP_RET"
    MEMORY = "MEMORY"


class Verdict(StrEnum):
    ALLOW = "ALLOW"
    ASK = "ASK"
    BLOCK = "BLOCK"


class ContentNature(StrEnum):
    informational = "informational"
    directive = "directive"
    example = "example"
    uncertain = "uncertain"


class ActionAlignment(StrEnum):
    expected = "expected"
    ancillary = "ancillary"
    deviant = "deviant"
    insufficient = "insufficient"


class DagNodeType(StrEnum):
    SOURCE = "SOURCE"
    AGENT = "AGENT"
    MCP_SERVER = "MCP_SERVER"
    TOOL = "TOOL"


class DagEdgeType(StrEnum):
    ACTUAL_CALL = "ACTUAL_CALL"
    TAINT_INDUCE = "TAINT_INDUCE"
    BLOCKED_ACTION = "BLOCKED_ACTION"


Identifier = Annotated[str, Field(min_length=1, max_length=256)]
Text = Annotated[str, Field(max_length=65536)]
Span = tuple[Annotated[int, Field(ge=0)], Annotated[int, Field(ge=0)]]


def canonical_json(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)


def digest(value: object) -> str:
    return hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()


def bounded_args(value):
    if len(canonical_json(value).encode("utf-8")) > 131072:
        raise ValueError("tool_args exceeds 128 KiB")
    return value


class D2Event(Model):
    event_id: Identifier
    session_id: Identifier
    timestamp: Annotated[float, Field(ge=0)]
    agent_id: Identifier
    parent_agent_id: Identifier | None
    call_id: Identifier
    stage: CallLifecycleStage
    event_type: EventType
    source_type: SourceType
    source_uri: Text
    raw_content: Text
    current_plan: Text
    tool_name: Annotated[str, Field(max_length=256)]
    tool_args: dict[str, JsonValue]
    _bounded = field_validator("tool_args")(bounded_args)


class ProposedAction(Model):
    session_id: Identifier
    call_id: Identifier
    agent_id: Identifier
    tool_name: Identifier
    tool_args: dict[str, JsonValue]
    current_plan: Text
    _bounded = field_validator("tool_args")(bounded_args)

    def args_hash(self) -> str:
        return digest({"agent_id": self.agent_id, "tool_name": self.tool_name, "tool_args": self.tool_args})


class FastMirrorLabel(Model):
    content_nature: ContentNature
    action_alignment: ActionAlignment
    latency_ms: float = Field(ge=0)


def needs_review(label: FastMirrorLabel) -> bool:
    """Instruction-like content alone is not an attack when action alignment is expected."""
    return label.action_alignment == ActionAlignment.deviant or (
        label.content_nature == ContentNature.directive and
        label.action_alignment in {ActionAlignment.ancillary, ActionAlignment.insufficient})


class OffsetMapping(Model):
    char_to_raw: list[Span]
    raw_tokens: list[Span]
    normalized_tokens: list[Span]
    token_to_raw: list[Span]


class SecretCandidate(Model):
    source_path: str
    plaintext: str


class ExtractedSummary(Model):
    normalized_text: str
    char_span: Span
    token_span: Span
    detected_secrets_count: int
    fast_mirror_label: FastMirrorLabel


class ExtractedData(ExtractedSummary):
    event: D2Event
    offset_mapping: OffsetMapping
    secrets: list[SecretCandidate] = Field(default_factory=list)


class IngestResponse(Model):
    status: Literal["ok"] = "ok"
    event_id: str
    extracted_summary: ExtractedSummary


class AnchorIntent(Model):
    initial_task: str
    task_type: Literal["code_review_readonly", "general"]
    intent_version: Literal[1] = 1


class SecretRecord(Model):
    secret_id: str
    source_path: str
    plaintext: str
    base64_value: str
    sub_chunks: list[str]
    encoded_chunks: list[str]


class OutboundRecord(Model):
    matched_chunks_count: int = 0
    coverage_ratio: float = 0
    blocked: bool = False


class DagNode(Model):
    id: str
    type: DagNodeType
    label: str
    source_type: SourceType | None = None
    token_span: Span | None = None
    verdict: Verdict | None = None


class DagEdge(Model):
    from_: str = Field(alias="from")
    to: str
    edge_type: DagEdgeType


class ImpactScope(Model):
    protected_files: list[str] = Field(default_factory=list)
    blocked_domains: list[str] = Field(default_factory=list)
    blocked_git_repos: list[str] = Field(default_factory=list)
    accessed_credentials: list[str] = Field(default_factory=list)


class SecretLedgerEntry(Model):
    secret_id: str
    source_path: str
    chunks_total: int


class TelemetrySnapshot(Model):
    session_id: str
    armor_enabled: bool
    anchor_intent: AnchorIntent | None
    secret_ledger: list[SecretLedgerEntry]
    accumulated_outbound: dict[str, OutboundRecord]
    dag_nodes: list[DagNode]
    dag_edges: list[DagEdge]
    impact_scope: ImpactScope


class CallRecord(Model):
    args_hash: str
    agent_id: str
    tool_name: str
    tool_args: dict[str, JsonValue]
    stages: set[CallLifecycleStage] = Field(default_factory=set)


class Evidence(Model):
    source_uri: str
    char_span: Span
    token_span: Span
    fast_mirror_label: FastMirrorLabel


class SecurityState(Model):
    session_id: str
    armor_enabled: bool = True
    anchor_intent: AnchorIntent | None = None
    secret_ledger: list[SecretRecord] = Field(default_factory=list)
    accumulated_outbound: dict[str, OutboundRecord] = Field(default_factory=dict)
    outbound_matches: dict[str, dict[str, dict[str, set[str]]]] = Field(default_factory=dict)
    calls: dict[str, CallRecord] = Field(default_factory=dict)
    evidence_by_agent: dict[str, Evidence] = Field(default_factory=dict)
    dag_nodes: list[DagNode] = Field(default_factory=list)
    dag_edges: list[DagEdge] = Field(default_factory=list)
    impact_scope: ImpactScope = Field(default_factory=ImpactScope)

    def telemetry(self) -> TelemetrySnapshot:
        return TelemetrySnapshot(
            session_id=self.session_id, armor_enabled=self.armor_enabled, anchor_intent=self.anchor_intent,
            secret_ledger=[SecretLedgerEntry(secret_id=s.secret_id, source_path=s.source_path,
                                            chunks_total=len(s.sub_chunks)) for s in self.secret_ledger],
            accumulated_outbound=self.accumulated_outbound, dag_nodes=self.dag_nodes,
            dag_edges=self.dag_edges, impact_scope=self.impact_scope,
        )


class ActionVerdict(Model):
    call_id: str
    verdict: Verdict
    risk_score: float = Field(ge=0, le=1)
    matched_policy_id: str | None
    fast_mirror_label: FastMirrorLabel
    slow_mirror_triggered: bool
    explainable_report: str
    approval_token: str | None
    source_uri: str
    char_span: Span
    token_span: Span


class ApprovalToken(Model):
    session_id: str
    call_id: str
    args_hash: str
    nonce: str
    issued_at: float
    expires_at: float


class ApproveRequest(Model):
    session_id: Identifier
    call_id: Identifier
    approval_token: Annotated[str, Field(min_length=1, max_length=4096)]
    user_approved: StrictBool


class ApproveResponse(Model):
    call_id: str
    final_verdict: Verdict
    reason: str


class ArmorRequest(Model):
    armor_enabled: StrictBool


class ArmorResponse(Model):
    session_id: str
    armor_enabled: bool


# Compatibility imports used by the other implementation; no wire-field aliases.
IngestEventRequest = D2Event
IngestEventResponse = IngestResponse
DecideActionRequest = ProposedAction
ActionVerdictResponse = ActionVerdict
ApproveActionRequest = ApproveRequest
ApproveActionResponse = ApproveResponse
ToggleArmorRequest = ArmorRequest
ToggleArmorResponse = ArmorResponse
TelemetrySnapshotResponse = TelemetrySnapshot
SecretRecordItem = SecretLedgerEntry
OutboundDomainRecord = OutboundRecord
