"""HMAC approvals bind a single pending action; SQLite makes consumption atomic."""
import base64
import hashlib
import hmac
import json
import os
import time
import uuid
from .store import encode


class Approvals:
    def __init__(self, store, clock=time.time):
        self.store=store;self.clock=clock
        self.pending_tokens={}
        row=store.db.execute("SELECT value FROM session_meta WHERE key='session_id'").fetchone()
        self.session=row[0] if row else uuid.uuid4().hex
        store.db.execute("INSERT OR IGNORE INTO session_meta VALUES('session_id',?)",(self.session,))
        private=store.folder/'.local';private.mkdir(exist_ok=True)
        path=private/'approval.key'
        if not path.exists():
            fd=os.open(path,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
            with os.fdopen(fd,'wb') as f:f.write(os.urandom(32))
        self.key=path.read_bytes()
        store.db.commit()

    def issue(self,call_id,args_hash,agent,ttl=300):
        if not 0<ttl<=900:raise ValueError('Approval TTL out of bounds')
        now=self.clock()
        body={'session':self.session,'call_id':call_id,'args_hash':args_hash,'agent':agent,
              'nonce':uuid.uuid4().hex,'issued':now,'expires':now+ttl}
        payload=base64.urlsafe_b64encode(encode(body).encode()).decode().rstrip('=')
        signature=hmac.new(self.key,payload.encode(),hashlib.sha256).hexdigest()
        self.store.db.execute('INSERT INTO approval_nonces VALUES(?,0)',(body['nonce'],))
        token=payload+'.'+signature
        self.pending_tokens[call_id]=token
        return token

    def summary(self, call_id):
        token=self.pending_tokens[call_id]
        payload=token.split('.')[0]
        body=json.loads(base64.urlsafe_b64decode(payload+'='*(-len(payload)%4)))
        return {'approval_token_sha256':hashlib.sha256(token.encode()).hexdigest(),
                'approval_nonce':body['nonce'],'approval_expires':body['expires']}

    def host_token(self, call_id):
        # Memory only; never returned by the Agent decision endpoint.
        if call_id not in self.pending_tokens:raise ValueError('Approval unavailable; restart requires a fresh host review')
        return self.pending_tokens[call_id]

    def consume(self,token,call_id,args_hash,agent):
        try:
            payload,signature=token.split('.')
            expected=hmac.new(self.key,payload.encode(),hashlib.sha256).hexdigest()
            if not hmac.compare_digest(signature,expected):raise ValueError('Invalid approval signature')
            body=json.loads(base64.urlsafe_b64decode(payload+'='*(-len(payload)%4)))
            if (body['session'],body['call_id'],body['args_hash'],body['agent'])!=(self.session,call_id,args_hash,agent):
                raise ValueError('Approval binding mismatch')
            if not body['issued']<=self.clock()<body['expires']:raise ValueError('Approval expired')
            changed=self.store.db.execute('UPDATE approval_nonces SET used=1 WHERE nonce=? AND used=0',(body['nonce'],)).rowcount
            if changed!=1:raise ValueError('Approval nonce missing or already consumed')
            self.pending_tokens.pop(call_id,None)
            return body
        except (KeyError,TypeError,json.JSONDecodeError) as exc:
            raise ValueError('Malformed approval token') from exc
