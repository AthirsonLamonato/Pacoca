from __future__ import annotations

import json
from pathlib import Path
import sqlite3
import threading
from datetime import datetime, timezone, timedelta
import uuid


def now():
    return datetime.now(timezone.utc).isoformat()


class Store:
    def __init__(self, path: Path):
        self.lock = threading.RLock()
        self.db = sqlite3.connect(path, check_same_thread=False)
        self.db.row_factory = sqlite3.Row
        self.db.executescript("""
        PRAGMA journal_mode=WAL;
        PRAGMA foreign_keys=ON;
        CREATE TABLE IF NOT EXISTS conversations(id TEXT PRIMARY KEY,title TEXT NOT NULL,created TEXT,updated TEXT,summary TEXT DEFAULT '');
        CREATE TABLE IF NOT EXISTS messages(id TEXT PRIMARY KEY,conversation_id TEXT REFERENCES conversations(id) ON DELETE CASCADE,role TEXT,content TEXT,created TEXT,interrupted INTEGER DEFAULT 0);
        CREATE INDEX IF NOT EXISTS message_conversation ON messages(conversation_id,created);
        CREATE TABLE IF NOT EXISTS memories(id TEXT PRIMARY KEY,content TEXT NOT NULL,source TEXT,created TEXT,updated TEXT);
        CREATE TABLE IF NOT EXISTS tasks(id TEXT PRIMARY KEY,conversation_id TEXT,request TEXT,status TEXT,created TEXT,updated TEXT,output TEXT DEFAULT '');
        CREATE TABLE IF NOT EXISTS events(id INTEGER PRIMARY KEY AUTOINCREMENT,task_id TEXT,kind TEXT,data TEXT,created TEXT);
        CREATE TABLE IF NOT EXISTS documents(id TEXT PRIMARY KEY,path TEXT UNIQUE,title TEXT,content TEXT,modified REAL);
        CREATE VIRTUAL TABLE IF NOT EXISTS document_search USING fts5(title,content,document_id UNINDEXED,tokenize='unicode61 remove_diacritics 2');
        CREATE TABLE IF NOT EXISTS reminders(id TEXT PRIMARY KEY,text TEXT,due TEXT,done INTEGER DEFAULT 0);
        CREATE TABLE IF NOT EXISTS alexa_requests(id TEXT PRIMARY KEY,task_id TEXT,created TEXT);
        """)
        self.db.commit()

    def query(self, sql, args=()):
        with self.lock:
            return [dict(row) for row in self.db.execute(sql, args).fetchall()]

    def execute(self, sql, args=()):
        with self.lock:
            self.db.execute(sql, args)
            self.db.commit()

    def backup(self,path):
        with self.lock:
            with sqlite3.connect(path) as target:
                self.db.backup(target)

    def conversation(self, title="Nova conversa"):
        id = uuid.uuid4().hex
        stamp = now()
        self.execute("INSERT INTO conversations(id,title,created,updated) VALUES(?,?,?,?)", (id,title,stamp,stamp))
        return self.query("SELECT * FROM conversations WHERE id=?", (id,))[0]

    def conversations(self):
        return self.query("SELECT * FROM conversations ORDER BY updated DESC LIMIT 100")

    def messages(self, id, limit=60):
        return self.query("SELECT * FROM (SELECT * FROM messages WHERE conversation_id=? ORDER BY rowid DESC LIMIT ?) ORDER BY created,id", (id,limit))

    def message(self, conversation_id, role, content, *, interrupted=False):
        id = uuid.uuid4().hex
        stamp = now()
        with self.lock:
            self.db.execute("INSERT INTO messages VALUES(?,?,?,?,?,?)", (id,conversation_id,role,content,stamp,int(interrupted)))
            self.db.execute("UPDATE conversations SET updated=? WHERE id=?", (stamp,conversation_id))
            if role == "user":
                self.db.execute("UPDATE conversations SET title=? WHERE id=? AND title='Nova conversa'", (content[:55],conversation_id))
            self.db.commit()
        return id

    def remember(self, content, source="usuário"):
        id = uuid.uuid4().hex
        stamp = now()
        self.execute("INSERT INTO memories VALUES(?,?,?,?,?)", (id,content,source,stamp,stamp))
        return id

    def memories(self):
        return self.query("SELECT * FROM memories ORDER BY updated DESC LIMIT 200")

    def task(self, conversation_id, request):
        id = uuid.uuid4().hex
        stamp = now()
        self.execute("INSERT INTO tasks VALUES(?,?,?,?,?,?,?)", (id,conversation_id,request,"running",stamp,stamp,""))
        return id

    def finish_task(self, id, status, output=""):
        self.execute("UPDATE tasks SET status=?,output=?,updated=? WHERE id=?", (status,output,now(),id))

    def event(self, task_id, kind, data):
        self.execute("INSERT INTO events(task_id,kind,data,created) VALUES(?,?,?,?)", (task_id,kind,json.dumps(data,ensure_ascii=False),now()))

    def index_document(self, path, text, modified):
        existing = self.query("SELECT id FROM documents WHERE path=?", (str(path),))
        id = existing[0]["id"] if existing else uuid.uuid4().hex
        with self.lock:
            self.db.execute("INSERT OR REPLACE INTO documents VALUES(?,?,?,?,?)", (id,str(path),path.name,text[:200000],modified))
            self.db.execute("DELETE FROM document_search WHERE document_id=?", (id,))
            self.db.execute("INSERT INTO document_search VALUES(?,?,?)", (path.name,text[:200000],id))
            self.db.commit()

    def search(self, text):
        import re
        terms = re.findall(r"\w{2,}", text)[:12]
        if not terms:
            return []
        match = " OR ".join('"' + w.replace('"','') + '"' for w in terms)
        return self.query("""SELECT d.id,d.path,d.title,snippet(document_search,1,'','', ' … ',45) AS excerpt
            FROM document_search JOIN documents d ON d.id=document_search.document_id
            WHERE document_search MATCH ? ORDER BY rank LIMIT 6""", (match,))

    def recover(self):
        self.execute("UPDATE tasks SET status='interrupted',updated=? WHERE status IN ('running','waiting_approval')", (now(),))

    def cleanup(self, days):
        cutoff = (datetime.now(timezone.utc) - timedelta(days=max(1,days))).isoformat()
        self.execute("DELETE FROM events WHERE created<?", (cutoff,))
        self.execute("DELETE FROM tasks WHERE updated<? AND status NOT IN ('running','waiting_approval')",(cutoff,))

    def close(self):
        self.db.close()
