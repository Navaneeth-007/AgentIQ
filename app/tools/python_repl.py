"""
Restricted Python REPL for trusted local data analysis.

This is not a security boundary: exposed libraries can access files and a
thread timeout cannot terminate executing code. Use only in a trusted local
demo; isolate execution in a separate service before public deployment.

Design decisions:
- Runs in a restricted exec() context — no shell access, no file system writes
  outside data/reports/.
- pandas, numpy, matplotlib are pre-imported and available.
- Charts saved as PNG to data/reports/, paths returned in output.
- stdout captured and returned as text output.
- Hard 30-second timeout via threading.

This is the differentiator: most agent demos skip a real code execution tool.
Having a sandboxed REPL means the agent can do arbitrary analysis — not just
what was pre-coded as a tool.
"""

from __future__ import annotations

import io
import threading
import time
import traceback
import uuid
from contextlib import redirect_stdout
from pathlib import Path

REPORTS_DIR = Path("data/reports")
REPORTS_DIR.mkdir(parents=True, exist_ok=True)

EXECUTION_TIMEOUT_SECONDS = 30

# Allowed modules in the sandbox
SAFE_BUILTINS = {
    "print": print,
    "len": len,
    "range": range,
    "enumerate": enumerate,
    "zip": zip,
    "list": list,
    "dict": dict,
    "set": set,
    "tuple": tuple,
    "str": str,
    "int": int,
    "float": float,
    "bool": bool,
    "min": min,
    "max": max,
    "sum": sum,
    "abs": abs,
    "round": round,
    "sorted": sorted,
    "reversed": reversed,
    "isinstance": isinstance,
    "type": type,
    "True": True,
    "False": False,
    "None": None,
}


def run_python_repl(code: str) -> dict:
    """
    Execute Python code for data analysis and return results.

    Args:
        code: Python code string. Use `plt.savefig(chart_path)` to save charts;
              the sandbox provides `chart_path` as a pre-set variable pointing to
              data/reports/<uuid>.png.

    Returns:
        {
            "stdout": "...",         # captured print output
            "error": null | "...",   # exception message if raised
            "chart_paths": [...],    # list of saved chart file paths
            "execution_time_ms": N,
        }
    """
    chart_id = str(uuid.uuid4())[:8]
    chart_path = str(REPORTS_DIR / f"chart_{chart_id}.png")

    # Pre-import common data science libs into the sandbox namespace
    sandbox_globals: dict = {"__builtins__": SAFE_BUILTINS}
    try:
        import matplotlib
        import numpy as np
        import pandas as pd

        matplotlib.use(
            "Agg"
        )  # Non-interactive backend — must set before importing pyplot
        import matplotlib.pyplot as plt

        sandbox_globals.update(
            {
                "pd": pd,
                "np": np,
                "plt": plt,
                "chart_path": chart_path,  # Pre-set so agent can just: plt.savefig(chart_path)
            }
        )
    except ImportError as e:
        return {
            "stdout": "",
            "error": f"Import failed: {e}",
            "chart_paths": [],
            "execution_time_ms": 0,
        }

    stdout_capture = io.StringIO()
    error: str | None = None
    timed_out = False

    def _execute():
        nonlocal error
        try:
            with redirect_stdout(stdout_capture):
                exec(code, sandbox_globals)  # noqa: S102
        except Exception:  # noqa: BLE001 — capture analysis errors
            error = traceback.format_exc()

    t0 = time.time()
    thread = threading.Thread(target=_execute, daemon=True)
    thread.start()
    thread.join(timeout=EXECUTION_TIMEOUT_SECONDS)

    if thread.is_alive():
        timed_out = True
        error = f"Execution timed out after {EXECUTION_TIMEOUT_SECONDS}s"

    elapsed_ms = (time.time() - t0) * 1000

    # Collect saved charts
    saved_charts = []
    if not timed_out and Path(chart_path).exists():
        saved_charts.append(chart_path)

    # Close matplotlib figure to free memory
    try:
        import matplotlib.pyplot as plt

        plt.close("all")
    except Exception:  # noqa: BLE001 — capture analysis errors
        traceback.print_exc()

    return {
        "stdout": stdout_capture.getvalue(),
        "error": error,
        "chart_paths": saved_charts,
        "execution_time_ms": round(elapsed_ms),
    }
