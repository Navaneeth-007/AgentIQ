"""Persistent local run history."""

import json
import sqlite3

from app.config import ROOT

DB = ROOT / "data" / "history.db"


def connection():
    DB.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB)
    conn.execute(
        "CREATE TABLE IF NOT EXISTS runs (id TEXT PRIMARY KEY, created TEXT DEFAULT CURRENT_TIMESTAMP, state TEXT NOT NULL)"
    )
    return conn


def save_run(state):
    with connection() as conn:
        conn.execute(
            "INSERT OR REPLACE INTO runs (id, state) VALUES (?, ?)",
            (state["session_id"], json.dumps(state, default=str)),
        )


def get_run(session_id):
    with connection() as conn:
        row = conn.execute(
            "SELECT state FROM runs WHERE id = ?", (session_id,)
        ).fetchone()
    return json.loads(row[0]) if row else None


def list_runs():
    with connection() as conn:
        rows = conn.execute(
            "SELECT id, created, state FROM runs ORDER BY created DESC, rowid DESC LIMIT 30"
        ).fetchall()
    return [
        {"session_id": r[0], "created": r[1], "question": json.loads(r[2])["question"]}
        for r in rows
    ]
