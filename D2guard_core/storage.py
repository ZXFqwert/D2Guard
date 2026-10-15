"""SQLite WAL persistence and cross-thread/process atomic state transitions."""
from contextlib import closing, contextmanager
from pathlib import Path
import json
import secrets
import sqlite3

from models import SecurityState, digest


class Store:
    def __init__(self, path: Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with closing(self.connect()) as conn:
            conn.execute("PRAGMA journal_mode=WAL")
            conn.executescript("""
                CREATE TABLE IF NOT EXISTS sessions (
                    session_id TEXT PRIMARY KEY, state_json TEXT NOT NULL, revision INTEGER NOT NULL DEFAULT 0
                );
                CREATE TABLE IF NOT EXISTS events (
                    session_id TEXT NOT NULL, event_id TEXT NOT NULL, payload_hash TEXT NOT NULL,
                    payload_json TEXT NOT NULL, extracted_json TEXT NOT NULL, response_json TEXT NOT NULL,
                    PRIMARY KEY(session_id,event_id), FOREIGN KEY(session_id) REFERENCES sessions(session_id)
                );
                CREATE TABLE IF NOT EXISTS approvals (
                    nonce TEXT PRIMARY KEY, session_id TEXT NOT NULL, call_id TEXT NOT NULL,
                    args_hash TEXT NOT NULL, action_json TEXT NOT NULL, token TEXT NOT NULL,
                    expires_at REAL NOT NULL, consumed INTEGER NOT NULL DEFAULT 0,
                    FOREIGN KEY(session_id) REFERENCES sessions(session_id)
                );
                CREATE INDEX IF NOT EXISTS approvals_call ON approvals(session_id,call_id);
                CREATE TABLE IF NOT EXISTS decisions (
                    id INTEGER PRIMARY KEY, session_id TEXT NOT NULL, call_id TEXT NOT NULL,
                    args_hash TEXT NOT NULL, verdict_json TEXT NOT NULL, created_at REAL NOT NULL
                );
                CREATE TABLE IF NOT EXISTS approval_audit (
                    nonce TEXT PRIMARY KEY, final_verdict TEXT NOT NULL, consumed_at REAL NOT NULL
                );
                CREATE TABLE IF NOT EXISTS metadata (key TEXT PRIMARY KEY, value TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS state_migration_backup (
                    session_id TEXT NOT NULL, version TEXT NOT NULL, state_json TEXT NOT NULL,
                    PRIMARY KEY(session_id,version)
                );
                INSERT OR IGNORE INTO metadata(key,value) VALUES ('schema_version','1');
            """)
            self._migrate(conn)

    @staticmethod
    def _migrate(conn):
        # The parallel prototype stored a private `risk` DAG property and bound
        # only arguments in call hashes. Preserve its entire state before upgrade.
        conn.execute("BEGIN IMMEDIATE")
        try:
            version = conn.execute("SELECT value FROM metadata WHERE key='schema_version'").fetchone()[0]
            if version == "1":
                for row in conn.execute("SELECT session_id,state_json FROM sessions").fetchall():
                    payload = json.loads(row["state_json"])
                    original = row["state_json"]
                    for node in payload.get("dag_nodes", []):
                        node.pop("risk", None)
                    for call_id, call in payload.get("calls", {}).items():
                        bound = digest({"agent_id": call["agent_id"], "tool_name": call["tool_name"], "tool_args": call["tool_args"]})
                        if call["args_hash"] != bound:
                            if call["args_hash"] != digest(call["tool_args"]):
                                raise ValueError("unrecognized legacy call fingerprint")
                            call["args_hash"] = bound
                            conn.execute("UPDATE approvals SET consumed=1 WHERE session_id=? AND call_id=? AND consumed=0",
                                         (row["session_id"], call_id))
                    state = SecurityState.model_validate(payload)
                    conn.execute("INSERT OR IGNORE INTO state_migration_backup VALUES (?,?,?)", (row["session_id"], version, original))
                    conn.execute("UPDATE sessions SET state_json=?,revision=revision+1 WHERE session_id=?",
                                 (state.model_dump_json(by_alias=True), row["session_id"]))
                conn.execute("UPDATE metadata SET value='2' WHERE key='schema_version'")
            elif version != "2":
                raise ValueError("unsupported database schema version")
            conn.commit()
        except BaseException:
            conn.rollback()
            raise

    def connect(self):
        conn = sqlite3.connect(str(self.path), timeout=30, isolation_level=None)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys=ON")
        conn.execute("PRAGMA busy_timeout=30000")
        conn.execute("PRAGMA synchronous=FULL")
        return conn

    @contextmanager
    def transaction(self):
        conn = self.connect()
        try:
            conn.execute("BEGIN IMMEDIATE")
            yield conn
            conn.commit()
        except BaseException:
            conn.rollback()
            raise
        finally:
            conn.close()

    def load(self, conn, session_id: str, *, create=False) -> SecurityState | None:
        row = conn.execute("SELECT state_json FROM sessions WHERE session_id=?", (session_id,)).fetchone()
        if row:
            return SecurityState.model_validate_json(row[0])
        if create:
            state = SecurityState(session_id=session_id)
            self.save(conn, state)
            return state
        return None

    def save(self, conn, state: SecurityState):
        conn.execute("""INSERT INTO sessions(session_id,state_json) VALUES (?,?)
                        ON CONFLICT(session_id) DO UPDATE SET state_json=excluded.state_json,revision=revision+1""",
                     (state.session_id, state.model_dump_json(by_alias=True)))

    def signing_key(self) -> bytes:
        with self.transaction() as conn:
            conn.execute("INSERT OR IGNORE INTO metadata(key,value) VALUES ('signing_key',?)", (secrets.token_hex(32),))
            return bytes.fromhex(conn.execute("SELECT value FROM metadata WHERE key='signing_key'").fetchone()[0])
