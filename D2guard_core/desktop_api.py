"""Additive desktop configuration/observability API; v1 audit contracts stay intact."""
from __future__ import annotations
import json
import threading
import time
from urllib.parse import urlsplit
from typing import Literal
import httpx
from fastapi import HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field, field_validator
from mirrors import SlowMirrorClient, response_text, slow_review_mode


class ModelConfiguration(BaseModel):
    model_config = ConfigDict(extra='forbid')
    base_url: str = Field(default='', max_length=2048)
    api_key: str | None = Field(default=None, max_length=4096)
    main_model: str = Field(default='deepseek-chat', max_length=256)
    slow_model: str = Field(default='deepseek-chat', max_length=256)
    clear_key: bool = False
    api_style: Literal["chat_completions", "responses"] = "chat_completions"
    timeout_seconds: float = Field(default=20, ge=1, le=25)

    @field_validator('base_url')
    @classmethod
    def valid_url(cls, value):
        value = value.strip().rstrip('/')
        if not value:
            return value
        url = urlsplit(value)
        if url.scheme not in {'http', 'https'} or not url.hostname or url.username or url.password or url.query or url.fragment:
            raise ValueError('Use an HTTP(S) API base URL without credentials, query or fragment')
        return value


class PlanInput(BaseModel):
    task: str = Field(min_length=1, max_length=16000)


class DesktopRuntime:
    def __init__(self, app, settings, engine):
        self.app, self.settings, self.engine = app, settings, engine
        self.lock = threading.RLock()
        self.transport = None  # Injectable HTTP transport for deterministic integration tests.
        with app.state.store.transaction() as conn:
            conn.execute('CREATE TABLE IF NOT EXISTS desktop_config (id INTEGER PRIMARY KEY, payload TEXT NOT NULL)')
            conn.execute('CREATE TABLE IF NOT EXISTS mirror_metrics (session_id TEXT, call_id TEXT, payload TEXT, PRIMARY KEY(session_id,call_id))')
            row = conn.execute('SELECT payload FROM desktop_config WHERE id=1').fetchone()
        self.config = ModelConfiguration(base_url=settings.slow_base_url or '', api_key=settings.slow_api_key,
                                         main_model=settings.slow_model, slow_model=settings.slow_model)
        if row:
            self.config = ModelConfiguration.model_validate_json(row[0])
            self.apply()

    def apply(self):
        c = self.config
        self.engine.slow = SlowMirrorClient(c.base_url, c.api_key, c.slow_model, c.timeout_seconds, self.transport, c.api_style)

    def public(self):
        c = self.config
        return {'base_url': c.base_url, 'main_model': c.main_model, 'slow_model': c.slow_model,
                'api_style': c.api_style, 'timeout_seconds': c.timeout_seconds, 'has_api_key': bool(c.api_key), 'mode': 'remote' if c.api_key and c.base_url else 'local', 'synced': True}

    def candidate(self, request):
        with self.lock:
            key = None if request.clear_key else (request.api_key if request.api_key is not None else self.config.api_key)
            return request.model_copy(update={'api_key': key, 'clear_key': False})

    def save(self, request):
        with self.lock:
            candidate = self.candidate(request)
            with self.app.state.store.transaction() as conn:
                conn.execute('INSERT OR REPLACE INTO desktop_config(id,payload) VALUES (1,?)', (candidate.model_dump_json(),))
            self.config = candidate
            self.apply()
            return self.public()

    def remote(self, c, path, payload=None):
        if not c.base_url or not c.api_key:
            raise HTTPException(400, '请填写 Base URL 与 API Key')
        try:
            with httpx.Client(timeout=c.timeout_seconds, transport=self.transport, trust_env=False, follow_redirects=False) as client:
                headers = {'Authorization': 'Bearer ' + c.api_key}
                with client.stream('POST' if payload is not None else 'GET', c.base_url + path, headers=headers, **({'json': payload} if payload is not None else {})) as response:
                    response.raise_for_status()
                    body = bytearray()
                    for chunk in response.iter_bytes():
                        body.extend(chunk)
                        if len(body) > 1024 * 1024:
                            raise ValueError('oversized model response')
                    return json.loads(body)
        except (httpx.HTTPError, ValueError, TypeError):
            # Never echo upstream responses or Authorization values.
            raise HTTPException(502, '模型服务连接失败、超时或响应格式无效，请检查地址与密钥') from None

    def record(self, session, verdict, elapsed):
        triggered = verdict.slow_mirror_triggered
        mode = slow_review_mode.get() if triggered else 'not_triggered'
        data = {'call_id': verdict.call_id, 'fast_latency_ms': verdict.fast_mirror_label.latency_ms,
                'slow_latency_ms': elapsed if triggered else None, 'slow_mode': mode, 'measured_at': time.time()}
        with self.app.state.store.transaction() as conn:
            conn.execute('INSERT OR REPLACE INTO mirror_metrics VALUES (?,?,?)', (session, verdict.call_id, json.dumps(data)))

    def health(self):
        fast = self.engine.fast
        return {'fast': {'backend': self.settings.fast_backend, 'model_loaded': bool(fast.backend),
                         'status': 'degraded' if fast.last_error else ('ready' if fast.backend else 'heuristic'),
                         'last_error': fast.last_error, 'busy': fast._busy.locked(), 'budget_ms': fast.budget_ms},
                'slow': {'configured': bool(self.config.base_url and self.config.api_key), 'model': self.config.slow_model,
                         'mode': 'remote' if self.config.base_url and self.config.api_key else 'local_fallback'}}


def install_desktop_api(app, settings, engine):
    runtime = DesktopRuntime(app, settings, engine)
    app.state.desktop = runtime

    def local(request: Request):
        origin = request.headers.get('origin')
        if origin and origin not in {'http://127.0.0.1:5173', 'http://localhost:5173', 'null'}:
            raise HTTPException(403, '配置接口仅允许本地桌面来源')

    @app.get('/api/desktop/models/config')
    def get_config(request: Request):
        local(request)
        return runtime.public()

    @app.post('/api/desktop/models/config')
    def set_config(config: ModelConfiguration, request: Request):
        local(request)
        return runtime.save(config)

    @app.post('/api/desktop/models/test')
    def test_models(config: ModelConfiguration, request: Request):
        local(request)
        c = runtime.candidate(config)
        if not c.api_key or not c.base_url:
            return {'models': [], 'mode': 'local', 'message': '未配置密钥，使用本地启发式与结构化复核'}
        result = runtime.remote(c, '/models')
        data = result.get('data') if isinstance(result, dict) else None
        if not isinstance(data, list):
            raise HTTPException(502, '模型列表格式无效')
        models = list(dict.fromkeys(item['id'] for item in data if isinstance(item, dict) and isinstance(item.get('id'), str) and item['id']))[:500]
        if not models:
            raise HTTPException(502, '模型服务未返回可用模型')
        return {'models': models, 'mode': 'remote', 'message': '已连接模型服务并取得可用模型'}

    @app.post('/api/desktop/models/plan')
    def plan_task(payload: PlanInput, request: Request):
        local(request)
        with runtime.lock:
            c = runtime.config.model_copy()
        if not c.api_key or not c.base_url:
            return {'mode': 'local', 'task': payload.task}
        messages = [{'role': 'system', 'content': '为用户任务建议一个待审计的工具动作。只输出 JSON 对象，字段 tool_name、tool_args。可用工具 fs.read、fs.write、net.fetch、exec、git.push、spawn_subagent。不声称已执行。'}, {'role': 'user', 'content': payload.task}]
        body = {'model': c.main_model, 'input': messages, 'max_output_tokens': 800, 'store': False, 'reasoning': {'effort': 'none'}} if c.api_style == 'responses' else {'model': c.main_model, 'messages': messages, 'temperature': 0, 'max_tokens': 800}
        result = runtime.remote(c, '/responses' if c.api_style == 'responses' else '/chat/completions', body)
        try:
            raw = response_text(result, c.api_style).strip()
            if raw.startswith('```'):
                raw = raw.split('\n', 1)[1].rsplit('```', 1)[0]
            action = json.loads(raw)
            if action['tool_name'] not in {'fs.read', 'fs.write', 'net.fetch', 'exec', 'git.push', 'spawn_subagent'} or not isinstance(action['tool_args'], dict):
                raise ValueError()
        except (KeyError, IndexError, TypeError, ValueError, AttributeError):
            raise HTTPException(502, '主模型未返回有效工具申请，未执行任何动作') from None
        return {'mode': 'remote', 'task': json.dumps({'initial_task': payload.task, 'tool_name': action['tool_name'], 'tool_args': action['tool_args']}, ensure_ascii=False)}

    @app.get('/api/desktop/runtime/health')
    def health():
        return runtime.health()

    @app.get('/api/desktop/sessions/{session_id}/metrics')
    def metrics(session_id: str):
        with app.state.store.transaction() as conn:
            rows = conn.execute('SELECT payload FROM mirror_metrics WHERE session_id=? ORDER BY rowid', (session_id,)).fetchall()
        return {'session_id': session_id, 'calls': [json.loads(row[0]) for row in rows]}

    @app.get('/api/desktop/sessions/{session_id}/evidence')
    def evidence(session_id: str):
        with app.state.store.transaction() as conn:
            rows = conn.execute('SELECT payload_json,extracted_json FROM events WHERE session_id=? ORDER BY rowid', (session_id,)).fetchall()
        items = []
        for row in rows:
            event, extracted = json.loads(row[0]), json.loads(row[1])
            items.append({'event_id': event['event_id'], 'uri': event['source_uri'], 'raw': event['raw_content'],
                          'summary': {key: extracted[key] for key in ['normalized_text', 'char_span', 'token_span', 'detected_secrets_count', 'fast_mirror_label']},
                          'raw_tokens': extracted['offset_mapping']['raw_tokens']})
        return {'items': items}

    @app.get('/api/desktop/policies')
    def policies():
        return {'yaml': settings.policy_path.read_text(encoding='utf-8'), 'rules': list(engine.rules.values())}

    return runtime
