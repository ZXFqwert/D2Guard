import hashlib
import json
import sqlite3
import time
import posixpath
from urllib.parse import urlsplit, urlunsplit


def encode(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':'))


def digest(value):
    return hashlib.sha256(value.encode()).hexdigest()


def source_identity(source_type, uri, sha):
    if '://' in uri:
        u=urlsplit(uri)
        uri=urlunsplit((u.scheme.lower(),u.netloc.lower(),posixpath.normpath(u.path) if u.path else '/',u.query,''))
    else:
        uri=posixpath.normpath(uri.replace('\\','/'))
    return 'SRC-'+digest(encode([source_type,uri,sha])),uri


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
        CREATE INDEX IF NOT EXISTS latest_agent_event ON events(agent,kind,created DESC);
        CREATE TABLE IF NOT EXISTS deltas(event_id TEXT PRIMARY KEY, delta TEXT);
        CREATE TABLE IF NOT EXISTS taints(id TEXT PRIMARY KEY,event_id TEXT,op TEXT,target TEXT,data TEXT);
        CREATE INDEX IF NOT EXISTS taint_target ON taints(target,op);
        CREATE TABLE IF NOT EXISTS directives(key TEXT,id TEXT,event_id TEXT,data TEXT,
            PRIMARY KEY(key,id));
        CREATE TABLE IF NOT EXISTS contexts(agent TEXT PRIMARY KEY,parent TEXT,spawned_at TEXT);
        CREATE TABLE IF NOT EXISTS context_labels(agent TEXT,kind TEXT,label TEXT,
            PRIMARY KEY(agent,kind,label));
        CREATE TABLE IF NOT EXISTS sources(id TEXT PRIMARY KEY,type TEXT,uri TEXT,sha TEXT);
        CREATE TABLE IF NOT EXISTS source_events(source_id TEXT,event_id TEXT,
            PRIMARY KEY(source_id,event_id));
        CREATE TABLE IF NOT EXISTS label_aliases(old_label TEXT PRIMARY KEY,source_id TEXT);
        CREATE TABLE IF NOT EXISTS unknowns(id TEXT PRIMARY KEY,source_id TEXT,data TEXT);
        CREATE INDEX IF NOT EXISTS unknown_source ON unknowns(source_id);
        CREATE TABLE IF NOT EXISTS normalized_evidence(event_id TEXT PRIMARY KEY,data TEXT);
        CREATE TABLE IF NOT EXISTS source_analysis(source_id TEXT PRIMARY KEY,data TEXT);
        CREATE TABLE IF NOT EXISTS tool_dispatches(call_id TEXT PRIMARY KEY);
        CREATE TABLE IF NOT EXISTS memory_entries(id TEXT PRIMARY KEY,data TEXT);
        CREATE TABLE IF NOT EXISTS approval_nonces(nonce TEXT PRIMARY KEY,used INTEGER NOT NULL);
        CREATE TABLE IF NOT EXISTS session_meta(key TEXT PRIMARY KEY,value TEXT);
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
        # Migrate historical indexes without dropping their audit representation.
        self.db.execute('''INSERT OR IGNORE INTO directives
            SELECT op || '|' || target,id,event_id,data FROM taints
            WHERE json_extract(data,'$.clause_kind')='candidate_instruction' ''')
        # Append mappings for old event-ID labels. Never delete their audit rows.
        for row in self.db.execute('''SELECT DISTINCT e.* FROM events e JOIN context_labels c
                ON c.label=e.id WHERE c.kind='integrity' ''').fetchall():
            sid=self.register_source(row['source'],row['uri'],row['sha'],row['id'])
            self.db.execute('INSERT OR IGNORE INTO label_aliases VALUES(?,?)',(row['id'],sid))
            self.db.execute("INSERT OR IGNORE INTO context_labels SELECT agent,kind,? FROM context_labels WHERE kind='integrity' AND label=?",(sid,row['id']))
        self.db.commit()

    def register_source(self, source_type, uri, sha, event_id):
        sid,normalized=source_identity(source_type,uri,sha)
        self.db.execute('INSERT OR IGNORE INTO sources VALUES(?,?,?,?)',(sid,source_type,normalized,sha))
        self.db.execute('INSERT OR IGNORE INTO source_events VALUES(?,?)',(sid,event_id))
        self.node(sid,'SOURCE_ID',normalized)
        self.edge(sid,'event:'+event_id,'SOURCE_OBSERVED',event_id)
        return sid

    def source_records(self, ids):
        result=[]
        for sid in ids:
            row=self.db.execute('SELECT * FROM sources WHERE id=?',(sid,)).fetchone()
            if row:result.append(dict(row))
        return result

    def add_unknown(self, source_id, item):
        value={**item,'src':source_id}
        uid='UNK-'+digest(encode([source_id,item['evidence_ref']['char_span'],item['reason']]))
        self.db.execute('INSERT OR IGNORE INTO unknowns VALUES(?,?,?)',(uid,source_id,encode(value)))

    def relevant_unknowns(self, agent, limit=8):
        return [json.loads(row[0]) for row in self.db.execute('''SELECT DISTINCT u.data FROM unknowns u
            JOIN context_labels c ON c.label=u.source_id WHERE c.agent=? AND c.kind='integrity' LIMIT ?''',(agent,limit))]

    def context(self, agent):
        row = self.db.execute('SELECT parent,spawned_at FROM contexts WHERE agent=?',(agent,)).fetchone()
        result = {'integrity': [], 'confidentiality': []}
        for item in self.db.execute('SELECT kind,label FROM context_labels WHERE agent=? ORDER BY kind,label',(agent,)):
            alias=self.db.execute('SELECT source_id FROM label_aliases WHERE old_label=?',(item['label'],)).fetchone() if item['kind']=='integrity' else None
            label=alias[0] if alias else item['label']
            if label not in result[item['kind']]:result[item['kind']].append(label)
        if row and row['parent']:
            result.update(parent=row['parent'], spawned_at=row['spawned_at'])
        return result

    def add_labels(self, agent, integrity=(), confidentiality=()):
        self.db.execute('INSERT OR IGNORE INTO contexts(agent) VALUES(?)',(agent,))
        for kind, labels in (('integrity',integrity),('confidentiality',confidentiality)):
            self.db.executemany('INSERT OR IGNORE INTO context_labels VALUES(?,?,?)',
                               ((agent,kind,label) for label in labels))

    def inherit_context(self, agent, parent, event_id):
        old = self.db.execute('SELECT parent FROM contexts WHERE agent=?',(agent,)).fetchone()
        if old and old['parent'] and old['parent'] != parent:
            raise ValueError('Agent parent identity changed')
        self.db.execute('INSERT INTO contexts VALUES(?,?,?) ON CONFLICT(agent) DO UPDATE SET '
                        'parent=excluded.parent,spawned_at=COALESCE(contexts.spawned_at,excluded.spawned_at)',
                        (agent,parent,event_id))
        labels = self.context(parent)
        self.add_labels(agent, labels['integrity'], labels['confidentiality'])

    def add_directive(self, op, target, item):
        item_id = digest(encode([item.get('source_id',item['taint_id']),item['evidence_ref']['char_span'],op,target]))
        self.db.execute('INSERT OR IGNORE INTO directives VALUES(?,?,?,?)',
                        (op+'|'+target,item_id,item['evidence_ref']['event_id'],encode(item)))
        self.db.execute('INSERT OR IGNORE INTO taints VALUES(?,?,?,?,?)',
                        (item_id,item['evidence_ref']['event_id'],op,target,encode(item)))

    def matching_directives(self, op, target, limit=8):
        return [json.loads(row[0]) for row in self.db.execute(
            'SELECT data FROM directives WHERE key=? ORDER BY id LIMIT ?', (op+'|'+target,limit))]

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
            'token_span':ref.get('token_span') if b-a<=max_chars else None,
            'tokenizer':ref.get('tokenizer') if b-a<=max_chars else None,
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
