"""Pure session transitions; callers persist the returned state transactionally."""
from __future__ import annotations

import base64
import re
from urllib.parse import unquote, urlsplit

from extractor import normalize
from models import (
    AnchorIntent, CallRecord, DagEdge, DagNode, Evidence, ExtractedData, OutboundRecord,
    ProposedAction, SecretRecord, SecurityState, Verdict, digest, canonical_json,
)


class StateConflict(ValueError):
    pass


def domain_of(args: dict) -> str:
    url = args.get("url")
    if not isinstance(url, str):
        raise ValueError("net.fetch requires an HTTP(S) url")
    parsed = urlsplit(url)
    if parsed.scheme.casefold() not in {"http", "https"} or not parsed.hostname or parsed.username or parsed.password:
        raise ValueError("invalid outbound url")
    # Force invalid ports to raise as well.
    _ = parsed.port
    return parsed.hostname.rstrip(".").encode("idna").decode("ascii").casefold()


def is_trusted(domain: str, domains: list[str]) -> bool:
    for entry in domains:
        wildcard = entry.startswith("*.")
        entry = entry.removeprefix("*.").rstrip(".").encode("idna").decode("ascii").casefold()
        if (not wildcard and domain == entry) or (wildcard and domain.endswith("." + entry)):
            return True
    return False


def windows(value: bytes) -> list[str]:
    width = min(8, len(value))
    return sorted({value[i:i + width].hex() for i in range(len(value) - width + 1)}) if width else []


def payload_views(args: dict) -> list[bytes]:
    # JSON serialization alone escapes CR/LF and misses multi-line key contents.
    values = [canonical_json(args)]
    def walk(value):
        if isinstance(value, str):
            values.append(value)
        elif isinstance(value, dict):
            for key, item in value.items():
                values.append(key)
                walk(item)
        elif isinstance(value, list):
            for item in value:
                walk(item)
    walk(args)
    text = "\n".join(values)
    decoded = unquote(unquote(text))
    normalized, _ = normalize(decoded)
    return [v.encode("utf-8") for v in (text, decoded, normalized)]


def matches_for(secret: SecretRecord, views: list[bytes], fingerprints=None) -> dict[str, set[str]]:
    # Compare standard / URL-safe Base64 with and without padding.
    fingerprints = fingerprints or payload_fingerprints(views)
    if len(secret.plaintext.encode()) < 8:
        plain = {c for c in secret.sub_chunks if any(bytes.fromhex(c) in v for v in views)}
    else:
        plain = set(secret.sub_chunks) & fingerprints["plain"]
    if len(secret.base64_value.rstrip("=")) < 8:
        encoded = {c for c in secret.encoded_chunks if any(bytes.fromhex(c) in v for v in views)}
    else:
        encoded = set(secret.encoded_chunks) & fingerprints["base64"]
    return {"plain": plain, "base64": encoded}


def payload_fingerprints(views: list[bytes]) -> dict[str, set[str]]:
    return {kind: {v[i:i + 8].hex() for view in views for v in
                   [view if kind == "plain" else view.replace(b"-", b"+").replace(b"_", b"/")]
                   for i in range(max(0, len(v) - 7))} for kind in ("plain", "base64")}


def full_secret_match(secret: SecretRecord, views: list[bytes]) -> bool:
    variants = [secret.plaintext.encode(), secret.base64_value.encode(),
                secret.base64_value.rstrip("=").encode(),
                base64.urlsafe_b64encode(secret.plaintext.encode()).rstrip(b"=")]
    return any(item and item in view for item in variants for view in views)


def register_call(state: SecurityState, action: ProposedAction, stage=None, *, allow_empty_post=False):
    existing = state.calls.get(action.call_id)
    if existing:
        if allow_empty_post and not action.tool_args:
            if existing.agent_id != action.agent_id or existing.tool_name != action.tool_name:
                raise StateConflict("call_id owner/tool cannot change")
        elif existing.args_hash != action.args_hash():
            raise StateConflict("call_id reused with different tool arguments or agent")
        if stage:
            existing.stages.add(stage)
    else:
        state.calls[action.call_id] = CallRecord(args_hash=action.args_hash(), agent_id=action.agent_id,
                                                 tool_name=action.tool_name, tool_args=action.tool_args,
                                                 stages={stage} if stage else set())


def record_outbound(state: SecurityState, args: dict):
    domain = domain_of(args)
    views = payload_views(args)
    fingerprints = payload_fingerprints(views)
    domain_matches = state.outbound_matches.setdefault(domain, {})
    for secret in state.secret_ledger:
        matched = matches_for(secret, views, fingerprints)
        accumulated = domain_matches.setdefault(secret.secret_id, {"plain": set(), "base64": set()})
        for kind in matched:
            accumulated[kind].update(matched[kind])
    ratios, count = [], 0
    for secret in state.secret_ledger:
        matched = domain_matches.get(secret.secret_id, {})
        per_secret = []
        for kind, chunks in (("plain", secret.sub_chunks), ("base64", secret.encoded_chunks)):
            found = len(matched.get(kind, set()))
            # Sliding windows detect fragments; coverage measures the union of
            # credential byte positions, not the number of overlapping windows.
            value = (secret.plaintext if kind == "plain" else secret.base64_value.rstrip("=")).encode()
            width = min(8, len(value))
            covered = set()
            for offset in range(len(value) - width + 1):
                if value[offset:offset + width].hex() in matched.get(kind, set()):
                    covered.update(range(offset, offset + width))
            ratio = len(covered) / len(value) if value else 0
            ratios.append(ratio)
            per_secret.append(ratio)
        # Report plaintext-equivalent maximum, without counting representations twice.
        encoded_equivalent = round(len(matched.get("base64", set())) / len(secret.encoded_chunks) * len(secret.sub_chunks)) if secret.encoded_chunks else 0
        count += max(len(matched.get("plain", set())), encoded_equivalent)
    record = state.accumulated_outbound.setdefault(domain, OutboundRecord())
    record.matched_chunks_count = count
    record.coverage_ratio = max(ratios, default=0)


def add_node(state: SecurityState, node: DagNode):
    for i, current in enumerate(state.dag_nodes):
        if current.id == node.id:
            if current.verdict is not None and node.verdict is None:
                return
            state.dag_nodes[i] = node
            return
    state.dag_nodes.append(node)


def add_edge(state: SecurityState, source: str, target: str, kind: str):
    if source == target:
        raise StateConflict("DAG self edge")
    adjacency: dict[str, list[str]] = {}
    for edge in state.dag_edges:
        adjacency.setdefault(edge.from_, []).append(edge.to)
    todo, seen = [target], set()
    while todo:
        node = todo.pop()
        if node == source:
            raise StateConflict("DAG cycle rejected")
        if node not in seen:
            seen.add(node)
            todo.extend(adjacency.get(node, []))
    same = [e for e in state.dag_edges if e.from_ == source and e.to == target]
    if any(e.edge_type == "BLOCKED_ACTION" for e in same) and kind == "ACTUAL_CALL":
        return
    state.dag_edges = [e for e in state.dag_edges if not (e.from_ == source and e.to == target)]
    state.dag_edges.append(DagEdge(from_=source, to=target, edge_type=kind))


def unique_append(items: list, item):
    if item not in items:
        items.append(item)


def trace_action(state: SecurityState, action: ProposedAction, verdict: Verdict | None = None):
    agent = "agent:" + action.agent_id
    tool = "call:" + action.call_id
    add_node(state, DagNode(id=agent, type="AGENT", label=action.agent_id))
    add_node(state, DagNode(id=tool, type="TOOL", label=action.tool_name, verdict=verdict))
    parent = agent
    if action.tool_name.startswith("mcp."):
        server_name = action.tool_name.split(".")[1]
        parent = "mcp:" + action.call_id
        add_node(state, DagNode(id=parent, type="MCP_SERVER", label=server_name))
        add_edge(state, agent, parent, "ACTUAL_CALL")
    add_edge(state, parent, tool, "BLOCKED_ACTION" if verdict == Verdict.BLOCK else "ACTUAL_CALL")
    if action.tool_name == "spawn_subagent" and verdict != Verdict.BLOCK:
        child_id = action.tool_args.get("agent_id") or action.tool_args.get("child_agent_id")
        if isinstance(child_id, str):
            child = "agent:" + child_id
            add_node(state, DagNode(id=child, type="AGENT", label=child_id))
            add_edge(state, tool, child, "ACTUAL_CALL")


def update_state(state: SecurityState, extracted: ExtractedData) -> SecurityState:
    result = state.model_copy(deep=True)
    event = extracted.event
    if event.session_id != result.session_id:
        raise StateConflict("session mismatch")
    # Only authentic user input can create the immutable task anchor.
    if result.anchor_intent is None and event.event_type == "USER_INPUT" and event.source_type == "USER":
        task = event.raw_content
        readonly = bool(re.search(r"code[ _-]?review|review.{0,20}code|代码.{0,8}(检视|审查|审阅|评审)|"
                                  r"(检视|审查|审阅|评审).{0,20}代码|只读|read[ _-]?only", task, re.I))
        result.anchor_intent = AnchorIntent(initial_task=task, task_type="code_review_readonly" if readonly else "general")
    agent = "agent:" + event.agent_id
    add_node(result, DagNode(id=agent, type="AGENT", label=event.agent_id))
    if event.parent_agent_id:
        parent = "agent:" + event.parent_agent_id
        add_node(result, DagNode(id=parent, type="AGENT", label=event.parent_agent_id))
        add_edge(result, parent, agent, "ACTUAL_CALL")
    source = "source:" + event.event_id
    add_node(result, DagNode(id=source, type="SOURCE", label=event.source_uri,
                            source_type=event.source_type, token_span=extracted.token_span))
    edge_kind = "TAINT_INDUCE" if extracted.fast_mirror_label.content_nature == "directive" else "ACTUAL_CALL"
    if event.source_type in {"MCP_RET", "MCP_DESC"}:
        server = "mcp-source:" + event.event_id
        add_node(result, DagNode(id=server, type="MCP_SERVER", label=event.source_uri))
        add_edge(result, source, server, edge_kind)
        add_edge(result, server, agent, edge_kind)
    else:
        add_edge(result, source, agent, edge_kind)
    # Retain untrusted evidence across tool-call lifecycle events with empty content.
    if event.raw_content and event.event_type not in {"TOOL_CALL", "SUBAGENT_SPAWN"}:
        previous = result.evidence_by_agent.get(event.agent_id)
        if not previous and event.parent_agent_id:
            previous = result.evidence_by_agent.get(event.parent_agent_id)
        suspicious = extracted.fast_mirror_label.content_nature == "directive" or extracted.fast_mirror_label.action_alignment == "deviant"
        if suspicious or not previous or previous.fast_mirror_label.content_nature != "directive":
            result.evidence_by_agent[event.agent_id] = Evidence(source_uri=event.source_uri,
                char_span=extracted.char_span, token_span=extracted.token_span, fast_mirror_label=extracted.fast_mirror_label)
        elif previous:
            result.evidence_by_agent[event.agent_id] = previous.model_copy(deep=True)
    added_secret = False
    for candidate in extracted.secrets:
        secret_id = "SEC-" + digest({"source_path": candidate.source_path, "plaintext": candidate.plaintext})[:24]
        if any(s.secret_id == secret_id for s in result.secret_ledger):
            continue
        encoded = base64.b64encode(candidate.plaintext.encode()).decode()
        result.secret_ledger.append(SecretRecord(secret_id=secret_id, source_path=candidate.source_path,
            plaintext=candidate.plaintext, base64_value=encoded, sub_chunks=windows(candidate.plaintext.encode()),
            encoded_chunks=windows(encoded.rstrip("=").encode())))
        added_secret = True
        unique_append(result.impact_scope.protected_files, candidate.source_path)
        unique_append(result.impact_scope.accessed_credentials, secret_id)
    if event.tool_name:
        action = ProposedAction(session_id=event.session_id, call_id=event.call_id, agent_id=event.agent_id,
                                tool_name=event.tool_name, tool_args=event.tool_args, current_plan=event.current_plan)
        register_call(result, action, event.stage, allow_empty_post=event.stage == "TOOL_POST_EXEC")
        trace_action(result, action)
    # Backfill if a return registers secrets after an earlier outgoing proposal.
    outgoing = result.calls.values() if added_secret else [result.calls[event.call_id]] if event.tool_name == "net.fetch" else []
    for call in outgoing:
        if call.tool_name == "net.fetch" and (not call.stages or call.stages - {"MODEL_PROPOSED"}):
            try:
                record_outbound(result, call.tool_args)
            except ValueError:
                pass  # Malformed network actions are blocked by the policy engine.
    return result


def build_security_chain_summary(
    state: SecurityState | None,
    *,
    tool_name: str = "",
    current_plan: str = "",
    agent_id: str = "main",
) -> dict[str, object]:
    """Compress long-horizon session state S_{t-1} into bounded security components."""
    if state is None:
        return {
            "anchor_type": "unanchored",
            "intent_locked": False,
            "taint_active": False,
            "taint_nature": "informational",
            "taint_alignment": "expected",
            "taint_token_span": [0, 0],
            "secret_ledger_count": 0,
            "max_coverage_ratio": 0.0,
            "dag_node_count": 0,
            "prior_call_chain": [],
            "proposed_tool": tool_name or "none",
            "has_plan": bool(current_plan.strip()),
        }
    anchor_type = state.anchor_intent.task_type if state.anchor_intent else "unanchored"
    evidence = state.evidence_by_agent.get(agent_id)
    if not evidence and state.evidence_by_agent:
        evidence = next(iter(state.evidence_by_agent.values()))
    taint_active = bool(
        evidence
        and (
            evidence.fast_mirror_label.content_nature == "directive"
            or evidence.fast_mirror_label.action_alignment == "deviant"
        )
    )
    prior_chain = [
        f"{rec.agent_id}:{rec.tool_name}"
        for rec in list(state.calls.values())[-6:]
    ]
    max_cov = round(
        max((r.coverage_ratio for r in state.accumulated_outbound.values()), default=0.0),
        4,
    )
    return {
        "anchor_type": anchor_type,
        "intent_locked": state.anchor_intent is not None,
        "taint_active": taint_active,
        "taint_nature": evidence.fast_mirror_label.content_nature.value if evidence else "informational",
        "taint_alignment": evidence.fast_mirror_label.action_alignment.value if evidence else "expected",
        "taint_token_span": list(evidence.token_span) if evidence else [0, 0],
        "secret_ledger_count": len(state.secret_ledger),
        "max_coverage_ratio": max_cov,
        "dag_node_count": len(state.dag_nodes),
        "prior_call_chain": prior_chain,
        "proposed_tool": tool_name or "none",
        "has_plan": bool(current_plan.strip()),
    }

