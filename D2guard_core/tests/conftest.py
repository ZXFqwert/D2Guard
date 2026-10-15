import itertools
from pathlib import Path
import time

from fastapi.testclient import TestClient
import pytest

from config import ROOT, Settings
from server import create_app


@pytest.fixture
def settings(tmp_path):
    return Settings(db_path=tmp_path / "state.sqlite3", policy_path=ROOT / "policies.yaml",
                    execution_root=tmp_path, signing_key="test-only-approval-signing-key-32-bytes")


@pytest.fixture
def app(settings):
    return create_app(settings)


@pytest.fixture
def client(app):
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture
def events():
    sequence = itertools.count(1)
    def make(**kwargs):
        index = next(sequence)
        event = dict(event_id=f"evt-{index}", session_id="s1", timestamp=time.time(), agent_id="main",
                     parent_agent_id=None, call_id=f"event-call-{index}", stage="MODEL_PROPOSED",
                     event_type="USER_INPUT", source_type="USER", source_uri="user",
                     raw_content="检视项目代码并输出报告", current_plan="阅读代码并生成报告", tool_name="", tool_args={})
        event.update(kwargs)
        return event
    return make


@pytest.fixture
def actions():
    sequence = itertools.count(1)
    def make(tool_name="fs.read", tool_args=None, **kwargs):
        result = dict(session_id="s1", call_id=f"action-{next(sequence)}", agent_id="main", tool_name=tool_name,
                      tool_args=tool_args or {"path": "README.md"}, current_plan="阅读代码并生成报告")
        result.update(kwargs)
        return result
    return make


@pytest.fixture
def anchored(client, events):
    assert client.post("/api/v1/events/ingest", json=events()).status_code == 200
    return client


@pytest.fixture
def secret(anchored, events):
    value = "A1b2C3d4E5f6G7h8I9j0K1l2"
    response = anchored.post("/api/v1/events/ingest", json=events(
        stage="TOOL_POST_EXEC", event_type="TOOL_RETURN", source_type="LOCAL_FILE",
        source_uri=".env", raw_content=value, tool_name="fs.read", tool_args={"path": ".env"}))
    assert response.status_code == 200, response.text
    return value
