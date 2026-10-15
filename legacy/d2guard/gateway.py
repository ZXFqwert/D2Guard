"""Non-mutating disclosure filter at the final model request boundary."""
from __future__ import annotations
import json
import secrets
import time
from .llm_config import create_llm_client
from .models import CallLifecycleStage, D2Event

class ModelAPIGateway:
    def __init__(self, core, real_client=None, provider=None):
        self.core = core
        self.real_client = real_client or create_llm_client(provider=provider)[0]
        self._filter_cache_key, self._filter_cache = None, None

    def chat_completion(self, model, messages, tools=None, temperature=0.0, max_tokens=1000, **kwargs):
        if self.real_client is None:
            raise RuntimeError("No model credentials configured")
        request = dict(model=model, messages=messages, temperature=temperature,
                       max_tokens=max_tokens, **kwargs)
        if tools:
            request['tools'] = tools
        redactor = self.core.redactor()
        from .redaction import OutboundRedactor
        filter_key=(id(redactor),getattr(self.real_client,"api_key", ""))
        if self._filter_cache_key != filter_key:
            self._filter_cache=OutboundRedactor([*redactor.values,filter_key[1]])
            self._filter_cache_key=filter_key
        redactor=self._filter_cache
        safe = redactor.sanitize(request)
        self.core.handle_gateway_event(D2Event(event_id='gateway-out-' + secrets.token_hex(12),
            timestamp=time.time(), session_id=self.core.session_id, agent_id='main',
            stage=CallLifecycleStage.MODEL_PROPOSED, event_type='PROMPT_OUTBOUND',
            source_type='MODEL_CONTEXT', raw_content=json.dumps(safe, ensure_ascii=False)))
        response = self.real_client.chat.completions.create(**safe)
        msg = response.choices[0].message
        calls = getattr(msg, 'tool_calls', None) or []
        for call in calls:
            try:
                args = json.loads(call.function.arguments)
            except ValueError:
                args = {'invalid_arguments': True}
            self.core.handle_gateway_event(D2Event(event_id='gateway-in-' + secrets.token_hex(12),
                timestamp=time.time(), session_id=self.core.session_id, agent_id='main',
                call_id=call.id, stage=CallLifecycleStage.MODEL_PROPOSED,
                event_type='TOOL_CALL_PROPOSED', tool_name=call.function.name,
                tool_args=args, source_type='MODEL', raw_content=call.function.arguments))
        if not calls:
            self.core.handle_gateway_event(D2Event(event_id='gateway-in-' + secrets.token_hex(12),
                timestamp=time.time(), session_id=self.core.session_id, agent_id='main',
                stage=CallLifecycleStage.MODEL_PROPOSED, event_type='LLM_OUTPUT',
                source_type='MODEL', raw_content=msg.content or ''))
        return response
