"""Contract-only FastAPI routes. Run with `python server.py`."""
from contextlib import asynccontextmanager
import logging
import time

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from approval import ApprovalManager, InvalidApproval
from config import CONTRACT, Settings
from execution import SafeExecutor
from desktop_api import install_desktop_api
from extractor import extract
from mirrors import FastMirrorAdapter, SlowMirrorClient
from models import (
    ActionVerdict, ApproveRequest, ApproveResponse, ArmorRequest, ArmorResponse,
    D2Event, ExtractedSummary, IngestResponse, ProposedAction, TelemetrySnapshot, Verdict, digest,
)
from policy_engine import PolicyEngine
from state_machine import StateConflict, domain_of, trace_action, unique_append, update_state
from storage import Store

log = logging.getLogger(__name__)


def create_app(settings: Settings | None = None, *, fast=None, slow=None) -> FastAPI:
    settings = settings or Settings()
    store = Store(settings.db_path)
    fast = fast or FastMirrorAdapter(model_path=settings.fast_model_path, backend_type=settings.fast_backend)
    slow = slow or SlowMirrorClient(settings.slow_base_url, settings.slow_api_key, settings.slow_model, settings.slow_timeout)
    engine = PolicyEngine(settings.policy_path, settings.execution_root, fast, slow)
    key = settings.signing_key.encode() if settings.signing_key else store.signing_key()
    approvals = ApprovalManager(key)

    @asynccontextmanager
    async def lifespan(app):
        log.info("D2Guard contract=%s initialized", CONTRACT["contract_version"])
        yield

    app = FastAPI(title="d2guard_core", version=CONTRACT["contract_version"], lifespan=lifespan)
    app.state.store, app.state.engine, app.state.approvals = store, engine, approvals
    app.state.executor = SafeExecutor(settings.execution_root,
        engine.rules["POL-EXEC-RESTRICT"]["blocked_environment_markers"])
    if CONTRACT["network_config"]["enable_cors"]:
        app.add_middleware(CORSMiddleware, allow_origins=CONTRACT["network_config"]["cors_allow_origins"],
                           allow_credentials=False, allow_methods=["GET", "POST", "OPTIONS"], allow_headers=["*"])

    @app.exception_handler(StateConflict)
    async def conflict_handler(request: Request, exc: StateConflict):
        return JSONResponse(status_code=409, content={"detail": str(exc)})

    @app.exception_handler(InvalidApproval)
    async def approval_handler(request: Request, exc: InvalidApproval):
        return JSONResponse(status_code=403, content={"detail": str(exc)})

    @app.exception_handler(RequestValidationError)
    async def validation_handler(request: Request, exc: RequestValidationError):
        # Avoid echoing secret-bearing request payloads in error responses.
        return JSONResponse(status_code=422, content={"detail": [
            {"loc": list(error["loc"]), "type": error["type"], "msg": error["msg"]} for error in exc.errors()
        ]})

    desktop = install_desktop_api(app, settings, engine)

    paths = CONTRACT["endpoints"]

    @app.post(paths["1_ingest_event"]["path"], response_model=IngestResponse)
    def ingest(event: D2Event):
        fingerprint = digest(event.model_dump(mode="json"))
        extracted = extract(event, fast)
        summary = ExtractedSummary.model_validate(extracted.model_dump(include=set(ExtractedSummary.model_fields)))
        response = IngestResponse(event_id=event.event_id, extracted_summary=summary)
        with store.transaction() as conn:
            state = store.load(conn, event.session_id, create=True)
            previous = conn.execute("SELECT payload_hash,response_json FROM events WHERE session_id=? AND event_id=?",
                                    (event.session_id, event.event_id)).fetchone()
            if previous:
                if previous[0] != fingerprint:
                    raise StateConflict("event_id reused with different content")
                return IngestResponse.model_validate_json(previous[1])
            state = update_state(state, extracted)
            store.save(conn, state)
            conn.execute("""INSERT INTO events(session_id,event_id,payload_hash,payload_json,extracted_json,response_json)
                            VALUES (?,?,?,?,?,?)""", (event.session_id, event.event_id, fingerprint,
                                event.model_dump_json(), extracted.model_dump_json(), response.model_dump_json()))
        return response

    @app.post(paths["2_decide_action"]["path"], response_model=ActionVerdict)
    def decide_action(action: ProposedAction):
        with store.transaction() as conn:
            state = store.load(conn, action.session_id, create=True)
            verdict = engine.decide(state, action, review=False)
            store.save(conn, state)
            if verdict.verdict != Verdict.ASK:
                conn.execute("UPDATE approvals SET consumed=1 WHERE session_id=? AND call_id=? AND consumed=0",
                             (action.session_id, action.call_id))
            decision_id = conn.execute("INSERT INTO decisions(session_id,call_id,args_hash,verdict_json,created_at) VALUES (?,?,?,?,?)",
                         (action.session_id, action.call_id, action.args_hash(), verdict.model_dump_json(), time.time())).lastrowid
        # Remote calls must not hold SQLite's single-writer transaction lock.
        slow_start = time.perf_counter()
        slow_elapsed = 0.0
        if verdict.slow_mirror_triggered:
            engine.enrich_report(state, verdict)
            slow_elapsed = (time.perf_counter() - slow_start) * 1000
        if verdict.slow_mirror_triggered or verdict.verdict == Verdict.ASK:
            with store.transaction() as conn:
                # Start the full authorization window after remote review, not before it.
                if verdict.verdict == Verdict.ASK:
                    verdict.approval_token = approvals.issue(conn, action)
                conn.execute("UPDATE decisions SET verdict_json=? WHERE id=?", (verdict.model_dump_json(), decision_id))
        desktop.record(action.session_id, verdict, slow_elapsed)
        return verdict

    @app.post(paths["3_approve_action"]["path"], response_model=ApproveResponse)
    def approve_action(request: ApproveRequest):
        with store.transaction() as conn:
            state = store.load(conn, request.session_id)
            if state is None or request.call_id not in state.calls:
                raise InvalidApproval("unknown approval session/call")
            call = state.calls[request.call_id]
            action = approvals.verify_and_consume(conn, request.approval_token, request.session_id,
                                                  request.call_id, call.args_hash)
            # Re-evaluate hard restrictions against the latest secret registry/anchor.
            policy, _ = engine.hard_check(state, action)
            final = Verdict.ALLOW if request.user_approved and (not state.armor_enabled or not policy) else Verdict.BLOCK
            reason = ("用户已通过单次签名令牌确认放行" if final == Verdict.ALLOW else
                      "最新会话状态命中强制阻断策略，审批不能覆盖该策略" if request.user_approved and policy else
                      "用户已拒绝本次动作")
            trace_action(state, action, final)
            if final == Verdict.BLOCK and action.tool_name == "net.fetch":
                try:
                    domain = domain_of(action.tool_args)
                    state.accumulated_outbound[domain].blocked = True
                    unique_append(state.impact_scope.blocked_domains, domain)
                except (ValueError, KeyError):
                    pass
            store.save(conn, state)
            nonce = conn.execute("SELECT nonce FROM approvals WHERE token=?", (request.approval_token,)).fetchone()[0]
            conn.execute("INSERT INTO approval_audit(nonce,final_verdict,consumed_at) VALUES (?,?,?)",
                         (nonce, final.value, time.time()))
        return ApproveResponse(call_id=request.call_id, final_verdict=final, reason=reason)

    @app.get(paths["4_session_telemetry"]["path"], response_model=TelemetrySnapshot)
    def telemetry(session_id: str):
        conn = store.connect()
        try:
            state = store.load(conn, session_id)
        finally:
            conn.close()
        if state is None:
            raise HTTPException(status_code=404, detail="session not found")
        snapshot = state.telemetry()
        payload = snapshot.model_dump(mode="json", by_alias=True)
        payload["dag_nodes"] = [node.model_dump(mode="json", by_alias=True, exclude_none=True) for node in snapshot.dag_nodes]
        return JSONResponse(content=payload)

    @app.post(paths["5_toggle_armor"]["path"], response_model=ArmorResponse)
    def toggle_armor(session_id: str, request: ArmorRequest):
        with store.transaction() as conn:
            state = store.load(conn, session_id, create=True)
            state.armor_enabled = request.armor_enabled
            store.save(conn, state)
        return ArmorResponse(session_id=session_id, armor_enabled=request.armor_enabled)

    return app


app = create_app()

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=8765, access_log=False)
