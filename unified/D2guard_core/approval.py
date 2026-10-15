"""HMAC-SHA256 token binding with persistent one-time nonces."""
import base64
import hashlib
import hmac
import json
import secrets
import time

from models import ApprovalToken, ProposedAction, canonical_json


class InvalidApproval(ValueError):
    pass


def encode(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).rstrip(b"=").decode("ascii")


def decode(value: str) -> bytes:
    return base64.b64decode(value + "=" * (-len(value) % 4), altchars=b"-_", validate=True)


class ApprovalManager:
    TTL = 60

    def __init__(self, key: bytes, clock=time.time):
        if len(key) < 32:
            raise ValueError("approval signing key must contain at least 32 bytes")
        self.key, self.clock = key, clock

    def issue(self, conn, action: ProposedAction) -> str:
        now = self.clock()
        existing = conn.execute("""SELECT token FROM approvals WHERE session_id=? AND call_id=?
                                   AND args_hash=? AND consumed=0 AND expires_at>?""",
                                (action.session_id, action.call_id, action.args_hash(), now)).fetchone()
        if existing:
            return existing[0]
        token = ApprovalToken(session_id=action.session_id, call_id=action.call_id, args_hash=action.args_hash(),
                              nonce=secrets.token_urlsafe(24), issued_at=now, expires_at=now + self.TTL)
        payload = encode(canonical_json(token.model_dump()).encode())
        signed = payload + "." + encode(hmac.new(self.key, payload.encode(), hashlib.sha256).digest())
        conn.execute("""INSERT INTO approvals(nonce,session_id,call_id,args_hash,action_json,token,expires_at)
                        VALUES (?,?,?,?,?,?,?)""", (token.nonce, action.session_id, action.call_id, action.args_hash(),
                                                    action.model_dump_json(), signed, token.expires_at))
        return signed

    def verify_and_consume(self, conn, signed: str, session_id: str, call_id: str, args_hash: str) -> ProposedAction:
        try:
            payload, signature = signed.split(".")
            expected = hmac.new(self.key, payload.encode("ascii"), hashlib.sha256).digest()
            if not hmac.compare_digest(expected, decode(signature)):
                raise InvalidApproval("invalid approval signature")
            token = ApprovalToken.model_validate(json.loads(decode(payload)))
        except (ValueError, TypeError, UnicodeError) as exc:
            raise InvalidApproval("malformed or invalid approval token") from exc
        now = self.clock()
        if (token.session_id, token.call_id, token.args_hash) != (session_id, call_id, args_hash):
            raise InvalidApproval("approval is bound to a different session/call/arguments")
        if token.issued_at > now or token.expires_at <= now or token.expires_at - token.issued_at != self.TTL:
            raise InvalidApproval("approval token expired or invalid TTL")
        row = conn.execute("SELECT * FROM approvals WHERE nonce=?", (token.nonce,)).fetchone()
        if not row or row["token"] != signed or row["args_hash"] != args_hash:
            raise InvalidApproval("unknown approval token")
        changed = conn.execute("""UPDATE approvals SET consumed=1 WHERE nonce=? AND consumed=0 AND expires_at>?""",
                               (token.nonce, now)).rowcount
        if changed != 1:
            raise InvalidApproval("approval token already consumed or expired")
        return ProposedAction.model_validate_json(row["action_json"])
