"""Run trusted analysis code in a disposable process with a real timeout.

Process separation stops timed-out work and keeps plotting/output state out of
other requests. It is not an OS sandbox: analysis libraries can still access
files and the network. Access must be restricted to trusted reviewers.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import time
import uuid

from app.config import ROOT

REPORTS_DIR = ROOT / "data" / "reports"
EXECUTION_TIMEOUT_SECONDS = 30


def run_python_repl(code: str, sql_rows: list[dict] | None = None) -> dict:
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    chart_path = str(REPORTS_DIR / f"chart_{uuid.uuid4().hex}.png")
    t0 = time.monotonic()
    # Do not pass model, email, database, or access credentials into the worker.
    worker_env = {
        k: v
        for k, v in os.environ.items()
        if k in {"PATH", "SYSTEMROOT", "LANG", "TMPDIR"}
    }
    worker_env["MPLCONFIGDIR"] = str(REPORTS_DIR / ".matplotlib")
    try:
        process = subprocess.run(
            [sys.executable, "-m", "app.tools.python_worker"],
            input=json.dumps(
                {"code": code, "chart_path": chart_path, "sql_rows": sql_rows or []},
                default=str,
            ),
            text=True,
            capture_output=True,
            cwd=ROOT,
            env=worker_env,
            check=False,
            timeout=EXECUTION_TIMEOUT_SECONDS,
        )
        if process.returncode:
            result = {
                "stdout": "",
                "error": "Analysis worker exited unexpectedly.",
                "chart_paths": [],
            }
        else:
            result = json.loads(process.stdout)
    except subprocess.TimeoutExpired:
        result = {
            "stdout": "",
            "error": f"Execution timed out after {EXECUTION_TIMEOUT_SECONDS}s",
            "chart_paths": [],
        }
    except (ValueError, OSError) as exc:
        result = {
            "stdout": "",
            "error": f"Analysis worker failed: {exc}",
            "chart_paths": [],
        }
    result["execution_time_ms"] = round((time.monotonic() - t0) * 1000)
    return result
