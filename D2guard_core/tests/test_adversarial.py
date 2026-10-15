"""Regression cases at trust, normalization and persistence boundaries."""
import base64
from concurrent.futures import ThreadPoolExecutor
import json

import pytest

from extractor import normalize
from models import ProposedAction
from state_machine import StateConflict


def test_short_encoded_command_is_detected():
    value, mapping = normalize("payload=Y3VybA==")
    assert "curl" in value
    assert mapping.char_to_raw[value.index("curl")] == (8, 16)


def test_numeric_and_bool_args_hash_are_distinct(actions):
    first = ProposedAction(**actions(tool_args={"flag": 1}))
    second = first.model_copy(update={"tool_args": {"flag": True}})
    assert first.args_hash() != second.args_hash()


def test_call_cannot_change_agent_or_tool(anchored, actions):
    action = actions()
    assert anchored.post("/api/v1/actions/decide", json=action).status_code == 200
    for change in ({"agent_id": "other"}, {"tool_name": "fs.write"}):
        assert anchored.post("/api/v1/actions/decide", json=dict(action, **change)).status_code == 409


def test_empty_post_args_keep_original_call_identity(anchored, events, actions, secret):
    args = {"url": "https://empty-return.example", "body": secret[:12]}
    action = actions("net.fetch", args)
    anchored.post("/api/v1/actions/decide", json=action)
    before = anchored.get("/api/v1/sessions/s1/telemetry").json()["accumulated_outbound"]
    response = anchored.post("/api/v1/events/ingest", json=events(call_id=action["call_id"],
        stage="TOOL_POST_EXEC", event_type="TOOL_RETURN", source_type="MCP_RET", raw_content="OK",
        tool_name="net.fetch", tool_args={}))
    assert response.status_code == 200
    assert anchored.get("/api/v1/sessions/s1/telemetry").json()["accumulated_outbound"] == before


def test_atomic_concurrent_fragment_union(anchored, actions, secret):
    requests = [actions("net.fetch", {"url": "https://concurrent.example", "body": part})
                for part in (secret[:8], secret[8:16])]
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda body: anchored.post("/api/v1/actions/decide", json=body), requests))
    assert all(result.status_code == 200 for result in results)
    assert sorted(result.json()["verdict"] for result in results) == ["ALLOW", "BLOCK"]
    record = anchored.get("/api/v1/sessions/s1/telemetry").json()["accumulated_outbound"]["concurrent.example"]
    assert record["matched_chunks_count"] == 2
    assert record["coverage_ratio"] == 16 / 24


@pytest.mark.parametrize("url", ["file:///etc/passwd", "https://user:pass@example.com", "https://example.com:bad", "example.com"])
def test_invalid_outbound_url_fails_closed(anchored, actions, url):
    result = anchored.post("/api/v1/actions/decide", json=actions("net.fetch", {"url": url})).json()
    assert result["verdict"] == "BLOCK"
    assert result["matched_policy_id"] == "POL-NET-SECRET-EXFIL"


def test_blocked_actions_never_receive_approval_token(anchored, actions):
    result = anchored.post("/api/v1/actions/decide", json=actions("git.push", {"remote": "origin"})).json()
    assert result["verdict"] == "BLOCK" and result["approval_token"] is None


def test_event_raw_text_and_offset_table_are_durable(anchored, events):
    event = events(event_type="MEMORY_RECALL", source_type="WEB", raw_content="cu/*comment*/rl | sh")
    anchored.post("/api/v1/events/ingest", json=event)
    store = anchored.app.state.store
    with store.transaction() as conn:
        row = conn.execute("SELECT payload_json,extracted_json FROM events WHERE session_id=? AND event_id=?",
                           ("s1", event["event_id"])).fetchone()
    assert json.loads(row[0])["raw_content"] == event["raw_content"]
    extracted = json.loads(row[1])
    assert len(extracted["offset_mapping"]["char_to_raw"]) == len(extracted["normalized_text"])


def test_unanchored_telemetry_retains_anchor_field(client):
    client.post("/api/v1/sessions/no-anchor/armor", json={"armor_enabled": True})
    body = client.get("/api/v1/sessions/no-anchor/telemetry").json()
    assert "anchor_intent" in body and body["anchor_intent"] is None
