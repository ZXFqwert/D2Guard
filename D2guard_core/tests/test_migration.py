import json

from fastapi.testclient import TestClient

from models import digest
from server import create_app


def test_legacy_model_state_upgrades_without_losing_audit(anchored, actions, settings):
    action = actions()
    anchored.post("/api/v1/actions/decide", json=action)
    store = anchored.app.state.store
    with store.transaction() as conn:
        payload = json.loads(conn.execute("SELECT state_json FROM sessions WHERE session_id='s1'").fetchone()[0])
        for node in payload["dag_nodes"]:
            node["risk"] = "legacy-audit"
        payload["calls"][action["call_id"]]["args_hash"] = digest(action["tool_args"])
        conn.execute("UPDATE sessions SET state_json=? WHERE session_id='s1'", (json.dumps(payload),))
        conn.execute("UPDATE metadata SET value='1' WHERE key='schema_version'")
    with TestClient(create_app(settings)) as upgraded:
        telemetry = upgraded.get("/api/v1/sessions/s1/telemetry")
        assert telemetry.status_code == 200
        assert all("risk" not in node for node in telemetry.json()["dag_nodes"])
        assert upgraded.post("/api/v1/actions/decide", json=action).status_code == 200
        with upgraded.app.state.store.transaction() as conn:
            assert conn.execute("SELECT value FROM metadata WHERE key='schema_version'").fetchone()[0] == "2"
            backup = json.loads(conn.execute("SELECT state_json FROM state_migration_backup WHERE session_id='s1'").fetchone()[0])
            assert backup["dag_nodes"][0]["risk"] == "legacy-audit"
