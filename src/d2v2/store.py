import hashlib
import json
import sqlite3
import time


def encode(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':'))


def digest(value):
    return hashlib.sha256(value.encode()).hexdigest()


class EvidenceStore:
    """SQLite is authoritative; JSONL is an export, not a second source of truth."""
    def __init__(self, folder):
        self.folder = folder
        self.db = sqlite3.connect(folder / 'state.sqlite3', check_same_thread=False)
        self.db.row_factory = sqlite3.Row
        self.db.executescript('''
        PRAGMA journal_mode=WAL;
        CREATE TABLE IF NOT EXISTS events(id TEXT PRIMARY KEY, agent TEXT, kind TEXT,
            source TEXT, uri TEXT, raw TEXT, sha TEXT, metadata TEXT, created REAL);
        CREATE TABLE IF NOT EXISTS deltas(event_id TEXT PRIMARY KEY, delta TEXT);
        CREATE TABLE IF NOT EXISTS taints(id TEXT PRIMARY KEY,event_id TEXT,op TEXT,target TEXT,data TEXT);
        CREATE INDEX IF NOT EXISTS taint_target ON taints(target,op);
        CREATE TABLE IF NOT EXISTS calls(id TEXT PRIMARY KEY,agent TEXT,args_hash TEXT,
            proposal_ref TEXT,decision TEXT,status TEXT);
        CREATE TABLE IF NOT EXISTS secret_chunks(secret_id TEXT, encoding TEXT, fp TEXT,
            PRIMARY KEY(secret_id,encoding,fp));
        CREATE INDEX IF NOT EXISTS fingerprint_lookup ON secret_chunks(fp);
        CREATE TABLE IF NOT EXISTS secrets(id TEXT PRIMARY KEY,event_id TEXT,source TEXT);
        CREATE TABLE IF NOT EXISTS exposure(domain TEXT,secret_id TEXT,encoding TEXT,phase TEXT,fp TEXT,
            PRIMARY KEY(domain,secret_id,encoding,phase,fp));
        CREATE TABLE IF NOT EXISTS steps(seq INTEGER PRIMARY KEY AUTOINCREMENT,data TEXT);
        CREATE TABLE IF NOT EXISTS grants(version INTEGER PRIMARY KEY AUTOINCREMENT,event_id TEXT,data TEXT);
        CREATE TABLE IF NOT EXISTS producer_events(agent TEXT,seq INTEGER,event_id TEXT,
            PRIMARY KEY(agent,seq));
        CREATE TABLE IF NOT EXISTS nodes(id TEXT PRIMARY KEY,kind TEXT,label TEXT);
        CREATE TABLE IF NOT EXISTS edges(source TEXT,target TEXT,kind TEXT,ref TEXT,
            PRIMARY KEY(source,target,kind,ref));
        CREATE TRIGGER IF NOT EXISTS immutable_events_update BEFORE UPDATE ON events
            BEGIN SELECT RAISE(ABORT,'evidence is immutable'); END;
        CREATE TRIGGER IF NOT EXISTS immutable_events_delete BEFORE DELETE ON events
            BEGIN SELECT RAISE(ABORT,'evidence is immutable'); END;
        ''')
        self.db.commit()

    def put(self, event_id, agent, kind, source, uri, raw, metadata=None):
        sha = digest(raw)
        old = self.db.execute('SELECT * FROM events WHERE id=?', (event_id,)).fetchone()
        metadata = metadata or {}
        if old:
            if (old['sha'],old['agent'],old['kind'],old['source'],old['uri'],old['metadata']) != (
                    sha,agent,kind,source,uri,encode(metadata)):
                raise ValueError('Event identity reused with different content')
            return {'event_id':event_id,'sha256':sha,'char_span':[0,len(raw)]}, False
        self.db.execute('INSERT INTO events VALUES(?,?,?,?,?,?,?,?,?)',
            (event_id,agent,kind,source,uri,raw,sha,encode(metadata),time.time()))
        self.node('event:'+event_id,'SOURCE',uri)
        self.node('agent:'+agent,'AGENT',agent)
        self.edge('event:'+event_id,'agent:'+agent,'OBSERVED',event_id)
        self.db.commit()
        with (self.folder/'evidence_store.jsonl').open('a',encoding='utf-8') as stream:
            stream.write(encode({'event_id':event_id,'agent_id':agent,'event_kind':kind,
                'source_type':source,'source_uri':uri,'raw':raw,'sha256':sha,'metadata':metadata})+'\n')
        return {'event_id':event_id,'sha256':sha,'char_span':[0,len(raw)]}, True

    def node(self,node_id,kind,label):
        self.db.execute('INSERT OR IGNORE INTO nodes VALUES(?,?,?)',(node_id,kind,label))

    def edge(self,source,target,kind,ref):
        self.db.execute('INSERT OR IGNORE INTO edges VALUES(?,?,?,?)',(source,target,kind,ref))

    def trace(self,limit=200):
        return {'nodes':[dict(r) for r in self.db.execute('SELECT * FROM nodes LIMIT ?',(limit,))],
            'edges':[dict(r) for r in self.db.execute('SELECT * FROM edges LIMIT ?',(limit,))],
            'truncated':self.db.execute('SELECT count(*) FROM nodes').fetchone()[0]>limit or self.db.execute('SELECT count(*) FROM edges').fetchone()[0]>limit,
            'attribution_semantics':'SUSPECTED_INDUCE and MODEL_ASSESSED are evidence associations, not proven causality'}

    def backtrack(self, ref, max_chars=1600):
        row = self.db.execute('SELECT * FROM events WHERE id=?',(ref['event_id'],)).fetchone()
        if not row or digest(row['raw']) != row['sha'] or row['sha'] != ref['sha256']:
            raise ValueError('Evidence hash or reference mismatch')
        a,b = ref['char_span']
        if not 0 <= a <= b <= len(row['raw']):
            raise ValueError('Evidence span out of bounds')
        return {'event_id':row['id'],'sha256':row['sha'],'source_type':row['source'],
            'source_uri':row['uri'],'char_span':[a,min(b,a+max_chars)],
            'excerpt':row['raw'][a:min(b,a+max_chars)],'truncated':b-a>max_chars}

    def save_delta(self, ref, delta):
        self.db.execute('INSERT INTO deltas VALUES(?,?)',(ref['event_id'],encode(delta)))
        self.db.commit()

    def step(self, value):
        self.db.execute('INSERT INTO steps(data) VALUES(?)',(encode(value),))
        self.db.commit()

    def recent(self, limit=8):
        return [json.loads(r[0]) for r in reversed(self.db.execute(
            'SELECT data FROM steps ORDER BY seq DESC LIMIT ?',(limit,)).fetchall())]
