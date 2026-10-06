"""
SQL query tool — read-only, injection-safe.

Design decisions:
- Only SELECT statements allowed (no INSERT/UPDATE/DELETE/DROP).
- Parameterised via sqlite3 (no f-string SQL).
- Row limit enforced to prevent runaway result sets.
- Supports both the bundled SQLite sample DB and external Postgres (via env var).
"""

from __future__ import annotations

import os
import re
import sqlite3
from pathlib import Path

MAX_ROWS = 500
SAMPLE_DB_PATH = Path(__file__).resolve().parents[2] / "data/sample_db/agentiq.db"


def _is_safe_query(query: str) -> bool:
    """Reject anything that isn't a SELECT."""
    stripped = query.strip().upper()
    # Must start with SELECT or WITH (CTEs)
    if not re.match(r"^(SELECT|WITH)\b", stripped):
        return False
    # Block dangerous keywords
    forbidden = [
        "INSERT",
        "UPDATE",
        "DELETE",
        "DROP",
        "ALTER",
        "CREATE",
        "TRUNCATE",
        "EXEC",
    ]
    for kw in forbidden:
        if re.search(rf"\b{kw}\b", stripped):
            return False
    return True


def _rows_to_json(cursor: sqlite3.Cursor) -> list[dict]:
    cols = [d[0] for d in cursor.description] if cursor.description else []
    return [dict(zip(cols, row)) for row in cursor.fetchmany(MAX_ROWS)]


def inspect_schema(db_path: str = "default") -> dict:
    """Return SQLite tables and columns without exposing raw PRAGMA syntax to the model."""
    resolved = str(SAMPLE_DB_PATH) if db_path == "default" else db_path
    if not Path(resolved).exists():
        raise FileNotFoundError(
            f"Database not found: {resolved}. "
            "Run `python scripts/seed_database.py` to create the sample DB."
        )

    conn = sqlite3.connect(Path(resolved).resolve().as_uri() + "?mode=ro", uri=True)
    try:
        tables = []
        for table_name, create_sql in conn.execute(
            "SELECT name, sql FROM sqlite_master "
            "WHERE type = 'table' AND name NOT LIKE 'sqlite_%' ORDER BY name"
        ):
            columns = [
                {"name": row[1], "type": row[2], "primary_key": bool(row[5])}
                for row in conn.execute(f'PRAGMA table_info("{table_name}")')
            ]
            tables.append({"name": table_name, "sql": create_sql, "columns": columns})
        return {"tables": tables}
    finally:
        conn.close()


def run_sql_query(query: str, db_path: str = "default") -> dict:
    """
    Execute a read-only SQL query and return results as JSON.

    Args:
        query:   A SELECT or WITH ... SELECT statement.
        db_path: "default" uses the bundled SQLite sample DB.
                 Any other value is treated as a file path to a SQLite DB.
                 Set env var POSTGRES_URL for Postgres support.

    Returns:
        {"rows": [...], "row_count": N, "columns": [...], "truncated": bool}
    """
    if not _is_safe_query(query):
        raise ValueError(
            "Only SELECT queries are allowed. "
            "INSERT/UPDATE/DELETE/DROP are blocked for safety."
        )

    # Resolve DB path
    if db_path == "default":
        resolved = str(SAMPLE_DB_PATH)
    else:
        resolved = db_path

    # Postgres path (optional)
    postgres_url = os.getenv("POSTGRES_URL")
    if postgres_url and db_path == "default":
        return _run_postgres(query, postgres_url)

    # SQLite path
    if not Path(resolved).exists():
        raise FileNotFoundError(
            f"Database not found: {resolved}. "
            "Run `python scripts/seed_database.py` to create the sample DB."
        )

    conn = sqlite3.connect(Path(resolved).resolve().as_uri() + "?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    try:
        cursor = conn.execute(query)
        rows = _rows_to_json(cursor)
        cols = [d[0] for d in cursor.description] if cursor.description else []
        return {
            "rows": rows,
            "row_count": len(rows),
            "columns": cols,
            "truncated": len(rows) == MAX_ROWS,
        }
    finally:
        conn.close()


def _run_postgres(query: str, url: str) -> dict:
    """Postgres backend (requires psycopg2)."""
    try:
        import psycopg2
        import psycopg2.extras
    except ImportError:
        raise ImportError("psycopg2 not installed. Run: pip install psycopg2-binary")

    conn = psycopg2.connect(url)
    try:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(query)
            rows = [dict(r) for r in cur.fetchmany(MAX_ROWS)]
            cols = [d.name for d in cur.description] if cur.description else []
            return {
                "rows": rows,
                "row_count": len(rows),
                "columns": cols,
                "truncated": len(rows) == MAX_ROWS,
            }
    finally:
        conn.close()
