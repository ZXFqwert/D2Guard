import pytest

import models
from config import CONTRACT


def test_all_enum_values_match_contract():
    for name, values in CONTRACT["enums"].items():
        assert [x.value for x in getattr(models, name)] == values


def test_routes_and_dto_field_names(app):
    documented = app.openapi()["paths"]
    for key, endpoint in CONTRACT["endpoints"].items():
        route = documented[endpoint["path"]][endpoint["method"].lower()]
        if "request_schema" in endpoint:
            schema = route["requestBody"]["content"]["application/json"]["schema"]
            props = app.openapi()["components"]["schemas"][schema["$ref"].split("/")[-1]]["properties"]
            assert set(props) == set(endpoint["request_schema"])
        schema = route["responses"]["200"]["content"]["application/json"]["schema"]
        props = app.openapi()["components"]["schemas"][schema["$ref"].split("/")[-1]]["properties"]
        assert set(props) == set(endpoint["response_schema"])


def test_ingest_and_verdict_exact_wire_shape(anchored, events, actions):
    endpoint = CONTRACT["endpoints"]["1_ingest_event"]
    response = anchored.post(endpoint["path"], json=events(raw_content="Read the README"))
    body = response.json()
    assert set(body) == set(endpoint["response_schema"])
    assert set(body["extracted_summary"]) == set(endpoint["response_schema"]["extracted_summary"])
    assert set(body["extracted_summary"]["fast_mirror_label"]) == {"content_nature", "action_alignment", "latency_ms"}
    result = anchored.post("/api/v1/actions/decide", json=actions()).json()
    assert set(result) == set(CONTRACT["endpoints"]["2_decide_action"]["response_schema"])
    assert result["approval_token"] is None


def test_cors_enabled(client):
    response = client.options("/api/v1/actions/decide", headers={"Origin": "http://localhost:5173",
        "Access-Control-Request-Method": "POST", "Access-Control-Request-Headers": "content-type"})
    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == "*"


@pytest.mark.parametrize("field,value", [("stage", "PRE_EXEC"), ("source_type", "user"),
                                        ("event_type", "tool_call"), ("renamed_field", "invalid")])
def test_invalid_enum_or_field_rejected(client, events, field, value):
    event = events(**{field: value})
    response = client.post("/api/v1/events/ingest", json=event)
    assert response.status_code == 422
    assert all("input" not in item for item in response.json()["detail"])


def test_missing_and_oversized_requests(client, events):
    assert client.post("/api/v1/events/ingest", json={"session_id": "s1"}).status_code == 422
    assert client.post("/api/v1/events/ingest", json=events(raw_content="x" * 65537)).status_code == 422


def test_armor_toggle_and_telemetry(anchored, actions):
    path = "/api/v1/sessions/s1/armor"
    assert anchored.post(path, json={"armor_enabled": False}).json() == {"session_id": "s1", "armor_enabled": False}
    assert anchored.post("/api/v1/actions/decide", json=actions("git.push")).json()["verdict"] == "ALLOW"
    assert anchored.post(path, json={"armor_enabled": True}).status_code == 200
    assert anchored.post("/api/v1/actions/decide", json=actions("git.push")).json()["verdict"] == "BLOCK"
    telemetry = anchored.get("/api/v1/sessions/s1/telemetry").json()
    assert set(telemetry) == set(CONTRACT["endpoints"]["4_session_telemetry"]["response_schema"])
    assert telemetry["armor_enabled"] is True
    assert telemetry["anchor_intent"]["task_type"] == "code_review_readonly"
    assert "from_" not in str(telemetry["dag_edges"])
    assert anchored.post(path, json={"armor_enabled": "false"}).status_code == 422
    assert anchored.get("/api/v1/sessions/unknown/telemetry").status_code == 404
