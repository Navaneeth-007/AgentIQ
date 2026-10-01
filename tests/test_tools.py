"""Tests for individual tools."""

from __future__ import annotations

import pytest
from unittest.mock import patch, MagicMock


class TestSqlTool:
    def test_blocks_insert(self):
        from app.tools.sql_tool import run_sql_query
        with pytest.raises(ValueError, match="Only SELECT"):
            run_sql_query("INSERT INTO orders VALUES (1, 2, 3)")

    def test_blocks_drop(self):
        from app.tools.sql_tool import run_sql_query
        with pytest.raises(ValueError, match="Only SELECT"):
            run_sql_query("DROP TABLE orders")

    def test_blocks_delete(self):
        from app.tools.sql_tool import run_sql_query
        with pytest.raises(ValueError, match="Only SELECT"):
            run_sql_query("DELETE FROM orders WHERE 1=1")

    def test_allows_select(self, tmp_path):
        import sqlite3
        from app.tools.sql_tool import run_sql_query
        db = tmp_path / "test.db"
        conn = sqlite3.connect(db)
        conn.execute("CREATE TABLE t (id INTEGER, val TEXT)")
        conn.execute("INSERT INTO t VALUES (1, 'hello')")
        conn.commit()
        conn.close()
        result = run_sql_query("SELECT * FROM t", db_path=str(db))
        assert result["row_count"] == 1
        assert result["rows"][0]["val"] == "hello"

    def test_allows_cte(self, tmp_path):
        import sqlite3
        from app.tools.sql_tool import run_sql_query
        db = tmp_path / "test.db"
        conn = sqlite3.connect(db)
        conn.execute("CREATE TABLE t (id INTEGER)")
        conn.execute("INSERT INTO t VALUES (1)")
        conn.commit()
        conn.close()
        result = run_sql_query("WITH cte AS (SELECT id FROM t) SELECT * FROM cte", db_path=str(db))
        assert result["row_count"] == 1


class TestPythonRepl:
    def test_basic_execution(self):
        from app.tools.python_repl import run_python_repl
        result = run_python_repl("print('hello world')")
        assert "hello world" in result["stdout"]
        assert result["error"] is None

    def test_captures_error(self):
        from app.tools.python_repl import run_python_repl
        result = run_python_repl("raise ValueError('test error')")
        assert result["error"] is not None
        assert "ValueError" in result["error"]

    def test_pandas_available(self):
        from app.tools.python_repl import run_python_repl
        result = run_python_repl("print(pd.DataFrame({'a': [1,2,3]}).shape)")
        assert "(3, 1)" in result["stdout"]
        assert result["error"] is None


class TestFileTool:
    def test_rejects_unsupported_extension(self, tmp_path):
        from app.tools.file_tool import read_file
        f = tmp_path / "test.xlsx"
        f.write_bytes(b"fake")
        with pytest.raises(ValueError, match="Unsupported"):
            read_file(str(f))

    def test_reads_csv(self, tmp_path):
        from app.tools.file_tool import read_file
        f = tmp_path / "data.csv"
        f.write_text("name,age\nAlice,30\nBob,25")
        result = read_file(str(f))
        assert result["row_count"] == 2
        assert "name" in result["columns"]
