"""Shared, non-mutating redaction for every model-bound payload.

The guard operates on serialized content, including tool arguments and schemas.
It is a disclosure filter, not a substitute for destination authorization.
"""
from __future__ import annotations

import base64
import json
import os
import re
from collections.abc import Mapping
from urllib.parse import quote, quote_plus

_CAPABILITY_FIELDS = {"approval_token", "token_id", "access_token"}
REDACTED = "[D2GUARD_REDACTED_SECRET]"
_KEY = re.compile(r"(?i)(?:password|passwd|secret|token|(?:api|access|private)[_-]?key)$")
_VALUE = re.compile(r"(?i)(\b(?:password|passwd|secret|token|(?:api|access|private)[_-]?key)\s*[:=]\s*[\"']?)([^\s\"'\r\n;,}]+)")
_TOKEN = re.compile(r"(?<![\w])(?:sk-[A-Za-z0-9_-]{16,}|gh[pousr]_[A-Za-z0-9]{16,}|AKIA[0-9A-Z]{16})")
_PEM = re.compile(r"-----BEGIN (?:[A-Z ]*PRIVATE KEY)-----[\s\S]*?-----END (?:[A-Z ]*PRIVATE KEY)-----")


class OutboundRedactor:
    def __init__(self, secrets=(), detect_credentials=True):
        self.detect_credentials = detect_credentials
        values = {str(s) for s in secrets if s}
        values.update(v for k, v in os.environ.items() if _KEY.search(k) and v and len(v) >= 6)
        self.values = values
        variants = set()
        for value in values:
            raw = value.encode("utf-8")
            variants.update((value, base64.b64encode(raw).decode(), raw.hex(), quote(value, safe=""), quote_plus(value)))
        # Cover nested encoded forms, including percent encoding every byte.
        first = list(variants)
        for variant in first:
            raw = variant.encode("utf-8")
            variants.update((base64.b64encode(raw).decode(), raw.hex(), quote(variant, safe=""),
                             "".join(f"%{b:02X}" for b in raw)))
        self.variants = sorted((v for v in variants if len(v) >= 6), key=len, reverse=True)
        self._variant_pattern = re.compile("|".join(re.escape(v) for v in self.variants), re.IGNORECASE) if self.variants else None

    @classmethod
    def from_state(cls, state):
        values = []
        for record in state.read_secrets.values():
            values.extend((record.exact_text, record.base64_text))
            values.extend(record.sub_chunks)
        return cls(values)

    def text(self, value: str) -> str:
        # Parsing embedded JSON also protects nested tool-call arguments.
        if value.lstrip().startswith(("{", "[")):
            try:
                parsed = json.loads(value)
            except (ValueError, TypeError):
                pass
            else:
                if isinstance(parsed, (dict, list)):
                    return json.dumps(self.payload(parsed), ensure_ascii=False)
        result = value
        if self._variant_pattern:
            result=self._variant_pattern.sub(lambda _:REDACTED,result)
        # Inspect whole encoded fields too: Base64(prefix + secret) has different alignment.
        from .normalizer import AdversarialNormalizer
        def encoded_field(match):
            original = match.group(0)
            candidates = AdversarialNormalizer.recursive_decode(original)
            if any(any(secret in text for secret in self.values) or (self.detect_credentials and (_TOKEN.search(text) or _PEM.search(text)))
                   for text in candidates[1:]):
                return REDACTED
            return original
        result = re.sub(r"[A-Za-z0-9+/=_%-]{12,}", encoded_field, result)
        if self.detect_credentials:
            result = _PEM.sub(REDACTED, result)
            result = _TOKEN.sub(REDACTED, result)
            result = _VALUE.sub(lambda m: m.group(1) + REDACTED, result)
        return result

    def payload(self, value):
        if hasattr(value, "model_dump"):
            value = value.model_dump(exclude_none=True)
        if isinstance(value, Mapping):
            return {str(k): REDACTED if self.detect_credentials and _KEY.search(str(k)) and str(k) not in _CAPABILITY_FIELDS and isinstance(v, str) and v else self.payload(v) for k, v in value.items()}
        if isinstance(value, (list, tuple)):
            return [self.payload(v) for v in value]
        if isinstance(value, str):
            return self.text(value)
        if value is None or isinstance(value, (bool, int, float)):
            return value
        raise TypeError(f"Unsupported model payload type: {type(value).__name__}")

    def assert_clean(self, value):
        serialized = json.dumps(value, ensure_ascii=False)
        if any(s in serialized for s in self.variants) or (self.detect_credentials and (_TOKEN.search(serialized) or _PEM.search(serialized))):
            raise ValueError("Model-bound payload failed the final disclosure check")
        return value

    def sanitize(self, value):
        return self.assert_clean(self.payload(value))
