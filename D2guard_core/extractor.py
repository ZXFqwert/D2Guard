"""Non-destructive detection view. All intervals refer to original Unicode text."""
from __future__ import annotations

import base64
import binascii
import re
import unicodedata
from pathlib import PurePosixPath

import regex

from models import D2Event, ExtractedData, OffsetMapping, SecretCandidate
from mirrors import FastMirrorAdapter

HOMOGLYPHS = str.maketrans({
    "а": "a", "е": "e", "о": "o", "р": "p", "с": "c", "х": "x", "у": "y",
    "і": "i", "ј": "j", "ѕ": "s", "ԁ": "d", "ԛ": "q", "ԝ": "w", "ӏ": "l",
    "А": "A", "В": "B", "Е": "E", "К": "K", "М": "M", "Н": "H", "О": "O",
    "Р": "P", "С": "C", "Т": "T", "Х": "X", "І": "I", "Ј": "J", "Ѕ": "S",
})
TOKENS = re.compile(r"\w+|[^\w\s]", re.UNICODE)
B64 = re.compile(r"(?<![A-Za-z0-9_+/-])([A-Za-z0-9_+/-]{6,}={0,2})(?![A-Za-z0-9_+/=-])")
SECRET_ASSIGNMENT = re.compile(
    r"(?im)^\s*(?:export\s+)?['\"]?[\w.-]*(?:API[_-]?KEY|SECRET|TOKEN|PASSWORD|PASSWD|PRIVATE[_-]?KEY|ACCESS[_-]?KEY)[\w.-]*['\"]?\s*[:=]\s*['\"]?([^\r\n'\",]+)"
)
INLINE_SECRET = re.compile(
    r"(?i)['\"]?(?:API[_-]?KEY|SECRET|TOKEN|PASSWORD|PASSWD|PRIVATE[_-]?KEY|ACCESS[_-]?KEY)[\w.-]*['\"]?\s*[:=]\s*['\"]?([A-Za-z0-9_.-]+)"
)
KEY_PATTERNS = re.compile(
    r"\b(sk-[A-Za-z0-9_-]{8,}|ghp_[A-Za-z0-9]{20,}|AKIA[0-9A-Z]{16})\b"
)



def _sub(text, mapping, pattern, replacement):
    parts, spans, cursor = [], [], 0
    for match in re.finditer(pattern, text, flags=re.DOTALL):
        parts.append(text[cursor:match.start()])
        spans.extend(mapping[cursor:match.start()])
        value = replacement(match)
        parts.append(value)
        original = mapping[match.start():match.end()]
        if original:
            bounds = (min(s[0] for s in original), max(s[1] for s in original))
            spans.extend([bounds] * len(value))
        cursor = match.end()
    parts.append(text[cursor:])
    spans.extend(mapping[cursor:])
    return "".join(parts), spans


def normalize(raw: str, *, decode_base64: bool = True) -> tuple[str, OffsetMapping]:
    chars, mapping = [], []
    # Grapheme boundaries retain NFKC composition, including combining marks/Jamo.
    for match in regex.finditer(r"\X", raw):
        normalized = unicodedata.normalize("NFKC", match.group()).translate(HOMOGLYPHS)
        for char in normalized:
            if not "\u200b" <= char <= "\u200f" and char not in "\ufeff\u2060":
                chars.append(char)
                mapping.append(match.span())
    text = "".join(chars)
    text, mapping = _sub(text, mapping, r"/\*.*?\*/", lambda _: "")
    text, mapping = _sub(text, mapping, r"\$\{IFS\}|\$IFS", lambda _: " ")
    # Quote concatenation only changes the detection view, never executable input.
    text, mapping = _sub(text, mapping, r"(?<=[\w'\"])[\"']+(?=[\w'\"]|\s|$)", lambda _: "")
    if decode_base64:
        for _ in range(2):
            additions, extra_maps = [], []
            # Bounded number and size prevent encoding bombs / unbounded recursion.
            for match in list(B64.finditer(text))[:8]:
                encoded = match.group(1)
                if len(encoded) > 16384:
                    continue
                try:
                    payload = base64.b64decode(encoded + "=" * (-len(encoded) % 4), altchars=b"-_", validate=True)
                    decoded = payload.decode("utf-8")
                except (ValueError, UnicodeDecodeError, binascii.Error):
                    continue
                if not decoded or sum(c.isprintable() or c in "\n\t\r" for c in decoded) / len(decoded) < .95:
                    continue
                decoded, _ = normalize(decoded, decode_base64=False)
                if decoded in text:
                    continue
                original = mapping[match.start(1):match.end(1)]
                bounds = (min(s[0] for s in original), max(s[1] for s in original))
                value = "\n[base64] " + decoded
                additions.append(value)
                extra_maps.extend([bounds] * len(value))
            if not additions:
                break
            text += "".join(additions)
            mapping.extend(extra_maps)
    raw_tokens = [m.span() for m in TOKENS.finditer(raw)]
    norm_tokens = [m.span() for m in TOKENS.finditer(text)]
    token_map = []
    for start, end in norm_tokens:
        relevant = mapping[start:end]
        token_map.append((min(s[0] for s in relevant), max(s[1] for s in relevant)))
    return text, OffsetMapping(char_to_raw=mapping, raw_tokens=raw_tokens,
                               normalized_tokens=norm_tokens, token_to_raw=token_map)


def sensitive_path(path: str) -> bool:
    name = PurePosixPath(path.replace("\\", "/")).name.casefold()
    return (name == ".env" or name.startswith(".env.") or name in
            {"id_rsa", "id_ed25519", "id_ecdsa", "credentials", "credentials.json", ".npmrc", ".pypirc"}
            or name.endswith((".pem", ".key"))
            or any(k in name for k in ("secret", "credential", "token", "password", "schema", "records", "spec", "migration", "config", "setting")))


def secret_candidates(event: D2Event) -> list[SecretCandidate]:
    # A proposed fs.read contains instructions, not the file's contents.
    if event.stage != "TOOL_POST_EXEC" and event.event_type not in {"TOOL_RETURN", "MEMORY_RECALL"}:
        return []
    if event.event_type == "TOOL_RETURN" and event.tool_name in {"fs.read", "read_file", "file.read"}:
        path = str(event.tool_args.get("path", event.source_uri))
        raw = event.raw_content
        if not raw.strip():
            return []
        if not sensitive_path(path) and not bool(KEY_PATTERNS.search(raw)):
            return []
        raw = event.raw_content
        values = [raw]  # Include complete config and separately register each credential value.
        values += [m.group(1).strip() for m in SECRET_ASSIGNMENT.finditer(raw)]
        values += [m.group(1).strip() for m in INLINE_SECRET.finditer(raw)]
        values += [m.group(1).strip() for m in KEY_PATTERNS.finditer(raw)]
        return [SecretCandidate(source_path=path, plaintext=v) for v in dict.fromkeys(values) if v]
    if event.event_type in {"TOOL_RETURN", "MEMORY_RECALL"} and (
        event.tool_name in {"memory.recall", "memory.read"} or event.source_type == "MEMORY"
    ):
        raw = event.raw_content.strip()
        if not raw:
            return []
        values = []
        values += [m.group(1).strip() for m in SECRET_ASSIGNMENT.finditer(raw)]
        values += [m.group(1).strip() for m in INLINE_SECRET.finditer(raw)]
        values += [m.group(1).strip() for m in KEY_PATTERNS.finditer(raw)]
        uri = event.source_uri or f"memory://{event.tool_args.get('query', '')}"
        return [SecretCandidate(source_path=uri, plaintext=v) for v in dict.fromkeys(values) if v]
    return []



_DEFAULT_MIRROR = FastMirrorAdapter()


def extract(event: D2Event, mirror: FastMirrorAdapter | None = None, state_chain: dict | None = None) -> ExtractedData:
    text, offsets = normalize(event.raw_content)
    secrets = secret_candidates(event)
    label = (mirror or _DEFAULT_MIRROR).classify(text, event.current_plan, state_chain=state_chain)
    # Highlight suspect normalized token(s), projected back through all transforms.
    suspect = re.search(r"ignore.{0,24}instructions|忽略.{0,16}指令|curl|wget|exfil|泄露|上传|id_rsa", text, re.I)
    if suspect:
        selected = offsets.char_to_raw[suspect.start():suspect.end()]
        char_span = (min(s[0] for s in selected), max(s[1] for s in selected))
    else:
        char_span = (0, len(event.raw_content))
    overlap = [i for i, (a, b) in enumerate(offsets.raw_tokens) if a < char_span[1] and b > char_span[0]]
    token_span = (min(overlap), max(overlap) + 1) if overlap else (0, 0)
    return ExtractedData(event=event, normalized_text=text, offset_mapping=offsets,
                         char_span=char_span, token_span=token_span, secrets=secrets,
                         detected_secrets_count=len(secrets), fast_mirror_label=label)
