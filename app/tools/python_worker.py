"""Internal trusted-code worker. Communicates through JSON on stdin/stdout."""

import io
import json
import sys
import traceback
from contextlib import redirect_stdout
from pathlib import Path


def main():
    request = json.load(sys.stdin)
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    import numpy as np
    import pandas as pd

    # Model-chosen chart filenames must not overwrite another reviewer's chart.
    from matplotlib.figure import Figure

    original_savefig = Figure.savefig

    def save_chart(figure, filename, *args, **kwargs):
        kwargs["format"] = "png"
        return original_savefig(figure, request["chart_path"], *args, **kwargs)

    Figure.savefig = save_chart

    names = [
        "print",
        "len",
        "range",
        "enumerate",
        "zip",
        "list",
        "dict",
        "set",
        "tuple",
        "str",
        "int",
        "float",
        "bool",
        "min",
        "max",
        "sum",
        "abs",
        "round",
        "sorted",
        "reversed",
        "isinstance",
        "type",
        "Exception",
        "ValueError",
        "KeyError",
    ]
    import builtins

    def analysis_import(name, globals=None, locals=None, fromlist=(), level=0):
        allowed = {
            "pandas",
            "numpy",
            "matplotlib",
            "math",
            "datetime",
            "calendar",
            "json",
            "statistics",
            "collections",
            "itertools",
            "decimal",
        }
        if level or name.split(".", 1)[0] not in allowed:
            raise ImportError(f"Import of {name} is not enabled for analysis code.")
        return builtins.__import__(name, globals, locals, fromlist, level)

    namespace = {
        "__builtins__": {
            **{n: getattr(builtins, n) for n in names},
            "__import__": analysis_import,
        },
        "pd": pd,
        "np": np,
        "plt": plt,
        "chart_path": request["chart_path"],
        "sql_rows": request.get("sql_rows", []),
    }
    output = io.StringIO()
    error = None
    try:
        with redirect_stdout(output):
            exec(request["code"], namespace)  # noqa: S102
    except Exception:  # noqa: BLE001 — return generated-code errors as evidence
        error = traceback.format_exc()
    finally:
        plt.close("all")
    chart = Path(request["chart_path"])
    print(
        json.dumps(
            {
                "stdout": output.getvalue()[:20000],
                "error": error,
                "chart_paths": [str(chart)] if chart.exists() and not error else [],
            }
        )
    )


if __name__ == "__main__":
    main()
