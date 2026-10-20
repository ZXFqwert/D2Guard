"""Read-only verification of a memory entry against its original writer run."""
import json
import hashlib
import sqlite3
from contextlib import closing

_sessions={}


def memory_origin(folder,entry):
    """Independently find the actual writer's committed memory call, not just metadata."""
    session=entry['writer_session'];root=folder.parent.resolve()
    key=(str(root),session)
    if key not in _sessions:
        for path in root.glob('*/state.sqlite3'):
            try:
                with closing(sqlite3.connect(path.resolve().as_uri()+'?mode=ro',uri=True)) as writer:
                    row=writer.execute("SELECT value FROM session_meta WHERE key='session_id'").fetchone()
                    if row:_sessions[(str(root),row[0])]=path.parent
            except sqlite3.OperationalError:continue
    writer_folder=_sessions.get(key)
    if not writer_folder:return {'writer_run_id':None,'native_write_verified':False}
    with closing(sqlite3.connect((writer_folder/'state.sqlite3').resolve().as_uri()+'?mode=ro',uri=True)) as writer:
        calls=writer.execute('SELECT call_id FROM tool_dispatches').fetchall()
        matched=False
        for cid, in calls:
            row=writer.execute('SELECT raw FROM events WHERE id=?',('pre-'+hashlib.sha256(cid.encode()).hexdigest(),)).fetchone()
            if not row:continue
            action=json.loads(row[0]);args=action['args']
            if action['tool']=='memory_write' and args.get('key')==entry['key'] and hashlib.sha256(args.get('content','').encode()).hexdigest()==entry['content_sha256']:
                matched=True
        source_ids={r[0] for r in writer.execute('SELECT id FROM sources')}
    return {'writer_run_id':writer_folder.name,'native_write_verified':matched and set(entry.get('integrity',[]))<=source_ids}
