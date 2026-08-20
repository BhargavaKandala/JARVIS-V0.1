import os
import sqlite3
import json
from datetime import datetime, date

DATA_DIR = os.path.join(os.path.dirname(__file__), '..', 'data')
DB_PATH = os.path.join(DATA_DIR, 'jarvis.db')

_conn = None


def _get_conn():
    global _conn
    if _conn is None:
        os.makedirs(DATA_DIR, exist_ok=True)
        _conn = sqlite3.connect(DB_PATH, check_same_thread=False)
        _conn.row_factory = sqlite3.Row
        _conn.execute("PRAGMA foreign_keys = ON")
        init_db()
    return _conn


def _now():
    return datetime.now().isoformat()


def init_db():
    conn = sqlite3.connect(DB_PATH, check_same_thread=False) if _conn is None else _conn
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS entities (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            type TEXT NOT NULL,
            name TEXT NOT NULL,
            metadata_json TEXT DEFAULT '{}',
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            UNIQUE(type, name)
        );

        CREATE TABLE IF NOT EXISTS relationships (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            from_entity_id INTEGER NOT NULL REFERENCES entities(id),
            to_entity_id INTEGER NOT NULL REFERENCES entities(id),
            relation_type TEXT NOT NULL,
            metadata_json TEXT DEFAULT '{}',
            created_at TEXT NOT NULL,
            UNIQUE(from_entity_id, to_entity_id, relation_type)
        );

        CREATE TABLE IF NOT EXISTS memories (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            kind TEXT NOT NULL,
            title TEXT,
            content TEXT NOT NULL,
            entity_id INTEGER REFERENCES entities(id),
            obsidian_path TEXT,
            tags_json TEXT DEFAULT '[]',
            source TEXT DEFAULT 'voice',
            created_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS embeddings (
            memory_id INTEGER PRIMARY KEY REFERENCES memories(id),
            vector BLOB NOT NULL,
            dim INTEGER NOT NULL,
            model TEXT NOT NULL,
            created_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS daily_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            log_date TEXT NOT NULL UNIQUE,
            summary TEXT,
            tasks_json TEXT DEFAULT '[]',
            created_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS projects (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL UNIQUE,
            status TEXT DEFAULT 'active',
            progress_pct INTEGER DEFAULT 0,
            priority TEXT DEFAULT 'medium',
            deadline TEXT,
            next_task TEXT,
            risks_json TEXT DEFAULT '[]',
            github_repo TEXT,
            entity_id INTEGER REFERENCES entities(id),
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS tasks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            project_id INTEGER REFERENCES projects(id),
            title TEXT NOT NULL,
            status TEXT DEFAULT 'open',
            due_date TEXT,
            source_text TEXT,
            created_at TEXT NOT NULL,
            completed_at TEXT
        );

        CREATE TABLE IF NOT EXISTS decisions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            project_id INTEGER REFERENCES projects(id),
            decision_text TEXT NOT NULL,
            rationale TEXT,
            created_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS preferences (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS conversation_summaries (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id TEXT NOT NULL,
            summary TEXT NOT NULL,
            created_at TEXT NOT NULL
        );
    """)
    conn.commit()
    if _conn is None:
        conn.close()


def _row_to_dict(row):
    return dict(row) if row is not None else None


# --- memories ---

def add_memory(kind, content, title=None, entity_id=None, obsidian_path=None, tags=None, source="voice"):
    conn = _get_conn()
    cur = conn.execute(
        "INSERT INTO memories (kind, title, content, entity_id, obsidian_path, tags_json, source, created_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        (kind, title, content, entity_id, obsidian_path, json.dumps(tags or []), source, _now()),
    )
    conn.commit()
    return cur.lastrowid


def get_memory(memory_id):
    conn = _get_conn()
    row = conn.execute("SELECT * FROM memories WHERE id = ?", (memory_id,)).fetchone()
    return _row_to_dict(row)


def find_memory_by_obsidian_path(obsidian_path):
    conn = _get_conn()
    row = conn.execute(
        "SELECT * FROM memories WHERE obsidian_path = ? ORDER BY created_at DESC LIMIT 1",
        (obsidian_path,),
    ).fetchone()
    return _row_to_dict(row)


def list_memories(kind=None, limit=20):
    conn = _get_conn()
    if kind:
        rows = conn.execute(
            "SELECT * FROM memories WHERE kind = ? ORDER BY created_at DESC LIMIT ?", (kind, limit)
        ).fetchall()
    else:
        rows = conn.execute(
            "SELECT * FROM memories ORDER BY created_at DESC LIMIT ?", (limit,)
        ).fetchall()
    return [dict(r) for r in rows]


# --- entities / relationships (knowledge graph) ---

def get_or_create_entity(type_, name, metadata=None):
    conn = _get_conn()
    row = conn.execute(
        "SELECT id FROM entities WHERE type = ? AND name = ?", (type_, name)
    ).fetchone()
    if row:
        return row["id"]
    cur = conn.execute(
        "INSERT INTO entities (type, name, metadata_json, created_at, updated_at) VALUES (?, ?, ?, ?, ?)",
        (type_, name, json.dumps(metadata or {}), _now(), _now()),
    )
    conn.commit()
    return cur.lastrowid


def add_relationship(from_entity_id, to_entity_id, relation_type, metadata=None):
    conn = _get_conn()
    cur = conn.execute(
        "INSERT OR IGNORE INTO relationships (from_entity_id, to_entity_id, relation_type, metadata_json, created_at) "
        "VALUES (?, ?, ?, ?, ?)",
        (from_entity_id, to_entity_id, relation_type, json.dumps(metadata or {}), _now()),
    )
    conn.commit()
    return cur.lastrowid


def get_related_entities(entity_id, relation_type=None):
    conn = _get_conn()
    if relation_type:
        rows = conn.execute(
            "SELECT e.* FROM entities e JOIN relationships r ON e.id = r.to_entity_id "
            "WHERE r.from_entity_id = ? AND r.relation_type = ?",
            (entity_id, relation_type),
        ).fetchall()
    else:
        rows = conn.execute(
            "SELECT e.* FROM entities e JOIN relationships r ON e.id = r.to_entity_id "
            "WHERE r.from_entity_id = ?",
            (entity_id,),
        ).fetchall()
    return [dict(r) for r in rows]


# --- projects ---

def upsert_project(name, **fields):
    conn = _get_conn()
    existing = get_project(name)
    if existing is None:
        entity_id = get_or_create_entity("project", name)
        cols = ["name", "entity_id", "created_at", "updated_at"]
        vals = [name, entity_id, _now(), _now()]
        for k, v in fields.items():
            cols.append(k)
            vals.append(v)
        placeholders = ", ".join("?" for _ in cols)
        conn.execute(f"INSERT INTO projects ({', '.join(cols)}) VALUES ({placeholders})", vals)
    else:
        if fields:
            set_clause = ", ".join(f"{k} = ?" for k in fields)
            vals = list(fields.values()) + [_now(), name]
            conn.execute(
                f"UPDATE projects SET {set_clause}, updated_at = ? WHERE name = ?", vals
            )
        else:
            conn.execute("UPDATE projects SET updated_at = ? WHERE name = ?", (_now(), name))
    conn.commit()
    return get_project(name)["id"]


def get_project(name):
    conn = _get_conn()
    row = conn.execute("SELECT * FROM projects WHERE name = ?", (name,)).fetchone()
    return _row_to_dict(row)


def list_projects(status=None):
    conn = _get_conn()
    if status:
        rows = conn.execute("SELECT * FROM projects WHERE status = ? ORDER BY updated_at DESC", (status,)).fetchall()
    else:
        rows = conn.execute("SELECT * FROM projects ORDER BY updated_at DESC").fetchall()
    return [dict(r) for r in rows]


# --- tasks ---

def add_task(project_name, title, due_date=None, source_text=None):
    conn = _get_conn()
    project = get_project(project_name)
    project_id = project["id"] if project else upsert_project(project_name)
    cur = conn.execute(
        "INSERT INTO tasks (project_id, title, due_date, source_text, created_at) VALUES (?, ?, ?, ?, ?)",
        (project_id, title, due_date, source_text, _now()),
    )
    conn.commit()
    return cur.lastrowid


def complete_task(task_id):
    conn = _get_conn()
    conn.execute(
        "UPDATE tasks SET status = 'done', completed_at = ? WHERE id = ?", (_now(), task_id)
    )
    conn.commit()


def find_open_task_by_title(project_name, title):
    conn = _get_conn()
    project = get_project(project_name)
    if not project:
        return None
    row = conn.execute(
        "SELECT * FROM tasks WHERE project_id = ? AND title LIKE ? AND status = 'open' "
        "ORDER BY created_at DESC LIMIT 1",
        (project["id"], f"%{title}%"),
    ).fetchone()
    return _row_to_dict(row)


def list_open_tasks(project_name=None):
    conn = _get_conn()
    if project_name:
        project = get_project(project_name)
        if not project:
            return []
        rows = conn.execute(
            "SELECT * FROM tasks WHERE project_id = ? AND status = 'open' ORDER BY due_date IS NULL, due_date",
            (project["id"],),
        ).fetchall()
    else:
        rows = conn.execute(
            "SELECT * FROM tasks WHERE status = 'open' ORDER BY due_date IS NULL, due_date"
        ).fetchall()
    return [dict(r) for r in rows]


def list_overdue_tasks(as_of=None):
    conn = _get_conn()
    as_of = as_of or date.today().isoformat()
    rows = conn.execute(
        "SELECT * FROM tasks WHERE status = 'open' AND due_date IS NOT NULL AND due_date < ? "
        "ORDER BY due_date",
        (as_of,),
    ).fetchall()
    return [dict(r) for r in rows]


# --- decisions ---

def add_decision(project_name, decision_text, rationale=None):
    conn = _get_conn()
    project = get_project(project_name) if project_name else None
    project_id = project["id"] if project else None
    cur = conn.execute(
        "INSERT INTO decisions (project_id, decision_text, rationale, created_at) VALUES (?, ?, ?, ?)",
        (project_id, decision_text, rationale, _now()),
    )
    conn.commit()
    return cur.lastrowid


def list_decisions(project_name=None, limit=10):
    conn = _get_conn()
    if project_name:
        project = get_project(project_name)
        if not project:
            return []
        rows = conn.execute(
            "SELECT * FROM decisions WHERE project_id = ? ORDER BY created_at DESC LIMIT ?",
            (project["id"], limit),
        ).fetchall()
    else:
        rows = conn.execute(
            "SELECT * FROM decisions ORDER BY created_at DESC LIMIT ?", (limit,)
        ).fetchall()
    return [dict(r) for r in rows]


# --- preferences ---

def set_preference(key, value):
    conn = _get_conn()
    conn.execute(
        "INSERT INTO preferences (key, value, updated_at) VALUES (?, ?, ?) "
        "ON CONFLICT(key) DO UPDATE SET value = excluded.value, updated_at = excluded.updated_at",
        (key, value, _now()),
    )
    conn.commit()


def get_preference(key):
    conn = _get_conn()
    row = conn.execute("SELECT value FROM preferences WHERE key = ?", (key,)).fetchone()
    return row["value"] if row else None


# --- daily logs ---

def upsert_daily_log(log_date, summary=None, tasks=None):
    conn = _get_conn()
    conn.execute(
        "INSERT INTO daily_logs (log_date, summary, tasks_json, created_at) VALUES (?, ?, ?, ?) "
        "ON CONFLICT(log_date) DO UPDATE SET summary = excluded.summary, tasks_json = excluded.tasks_json",
        (log_date, summary, json.dumps(tasks or []), _now()),
    )
    conn.commit()


def get_daily_log(log_date):
    conn = _get_conn()
    row = conn.execute("SELECT * FROM daily_logs WHERE log_date = ?", (log_date,)).fetchone()
    return _row_to_dict(row)


# --- conversation summaries ---

def add_conversation_summary(session_id, summary):
    conn = _get_conn()
    cur = conn.execute(
        "INSERT INTO conversation_summaries (session_id, summary, created_at) VALUES (?, ?, ?)",
        (session_id, summary, _now()),
    )
    conn.commit()
    return cur.lastrowid
