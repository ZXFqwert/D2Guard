"""Session-keyed fingerprints on disk; plaintext exists only in the evidence archive."""
import base64
import hashlib
import hmac
import json
import os
import re
from urllib.parse import unquote, urlsplit
from d2core.extractor import SECRET_ASSIGNMENT, INLINE_SECRET, KEY_PATTERNS
from .normalization import normalize
from .store import digest, encode


def values(raw):
    found=[m.group(1).strip() for m in SECRET_ASSIGNMENT.finditer(raw)]
    found += [m.group(1).strip() for m in INLINE_SECRET.finditer(raw)]
    found += [m.group(1).strip() for m in KEY_PATTERNS.finditer(raw)]
    found += re.findall(r'-----BEGIN [A-Z ]*PRIVATE KEY-----[\s\S]+?-----END [A-Z ]*PRIVATE KEY-----',raw)
    return list(dict.fromkeys(v for v in found if len(v)>=8))


class FingerprintLedger:
    def __init__(self, store):
        self.store=store
        key_path=store.folder/'fingerprint.key'
        if not key_path.exists():key_path.write_bytes(os.urandom(32))
        self.key=key_path.read_bytes()

    def windows(self, data):
        # Short secrets also have a full-value keyed fingerprint.
        return {hmac.digest(self.key,data[i:i+8],'sha256').hex() for i in range(max(0,len(data)-7))}

    def register(self, raw, ref, source):
        ids=[]
        for value in values(raw):
            sid='SEC-'+hmac.digest(self.key,value.encode(),'sha256').hex()[:20]
            self.store.db.execute('INSERT OR IGNORE INTO secrets VALUES(?,?,?)',(sid,ref['event_id'],source))
            for encoding,data in [('plain',value.encode()),('base64',base64.b64encode(value.encode()).rstrip(b'='))]:
                self.store.db.executemany('INSERT OR IGNORE INTO secret_chunks VALUES(?,?,?)',
                    ((sid,encoding,fp) for fp in self.windows(data)))
            ids.append(sid)
        self.store.db.commit()
        return ids

    def match(self, value, domain=''):
        text=value if isinstance(value,str) else encode(value)
        normalized,_=normalize(unquote(unquote(text)))
        # Decode JSON escaping by walking actual strings, not serialized wire bytes alone.
        pieces=[text,normalized]
        def walk(obj):
            if isinstance(obj,str):pieces.append(obj)
            elif isinstance(obj,dict):
                for item in obj.values():walk(item)
            elif isinstance(obj,list):
                for item in obj:walk(item)
        if not isinstance(value,str):walk(value)
        fps=set()
        for piece in pieces:fps.update(self.windows(piece.encode()))
        db=self.store.db
        db.execute('CREATE TEMP TABLE IF NOT EXISTS candidate_fps(fp TEXT PRIMARY KEY)')
        db.execute('DELETE FROM candidate_fps')
        db.executemany('INSERT OR IGNORE INTO candidate_fps VALUES(?)',((fp,) for fp in fps))
        rows=db.execute('SELECT s.secret_id,s.encoding,s.fp FROM secret_chunks s JOIN candidate_fps c ON s.fp=c.fp').fetchall()
        groups={}
        for r in rows:groups.setdefault((r['secret_id'],r['encoding']),set()).add(r['fp'])
        summary=[]
        for (sid,enc),matched in groups.items():
            total=db.execute('SELECT count(*) FROM secret_chunks WHERE secret_id=? AND encoding=?',(sid,enc)).fetchone()[0]
            previous={r[0] for r in db.execute('SELECT fp FROM exposure WHERE domain=? AND secret_id=? AND encoding=? AND phase IN (?,?)',
                (domain,sid,enc,'confirmed_delivery','execution_started'))}
            summary.append({'secret_id':sid,'encoding':enc,'current_coverage':len(matched)/total,
                'projected_coverage':len(previous|matched)/total})
        db.commit()
        return summary,groups

    def record(self, domain, groups, phase):
        for (sid,enc),fps in groups.items():
            self.store.db.executemany('INSERT OR IGNORE INTO exposure VALUES(?,?,?,?,?)',
                ((domain,sid,enc,phase,fp) for fp in fps))
        self.store.db.commit()

    def redact(self, text):
        result=text
        # Retrieve one bounded evidence item at a time; do not keep all plaintext in state.
        for row in self.store.db.execute('SELECT DISTINCT e.raw FROM secrets s JOIN events e ON e.id=s.event_id'):
            for value in values(row[0]):
                for variant in (value,base64.b64encode(value.encode()).decode(),base64.urlsafe_b64encode(value.encode()).decode()):
                    result=result.replace(variant,'<REDACTED_SECRET>')
        result=SECRET_ASSIGNMENT.sub(lambda m:m.group().replace(m.group(1),'<REDACTED_SECRET>'),result)
        result=KEY_PATTERNS.sub('<REDACTED_SECRET>',result)
        # Reject remaining registered fragments before any cloud submission.
        matches,_=self.match(result)
        return '<REDACTED_FRAGMENT_BEARING_EXCERPT>' if matches else result

    def summary(self):
        db=self.store.db
        return {'loaded_count':db.execute('SELECT count(*) FROM secrets').fetchone()[0],
            'exposure_phases':{r[0]:r[1] for r in db.execute('SELECT phase,count(DISTINCT domain || secret_id) FROM exposure GROUP BY phase')},
            'actual_leakage_semantics':'Only independent receipts establish experiment leakage; started/allowed is not delivery.'}
