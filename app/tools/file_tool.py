"""File reader for CSV, JSON, and Parquet."""

from __future__ import annotations

from pathlib import Path

ALLOWED_EXTENSIONS = {".csv", ".json", ".parquet"}
MAX_PREVIEW_ROWS = 100


def read_file(path: str) -> dict:
    """
    Read a data file and return a preview.

    Args:
        path: Path to CSV, JSON, or Parquet file.

    Returns:
        {"columns": [...], "row_count": N, "preview": "markdown table", "path": path}
    """
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(f"File not found: {path}")
    if p.suffix not in ALLOWED_EXTENSIONS:
        raise ValueError(
            f"Unsupported file type: {p.suffix}. Allowed: {ALLOWED_EXTENSIONS}"
        )

    try:
        import pandas as pd
    except ImportError:
        raise ImportError("pandas not installed. Run: pip install pandas")

    if p.suffix == ".csv":
        df = pd.read_csv(p, nrows=MAX_PREVIEW_ROWS)
    elif p.suffix == ".json":
        df = pd.read_json(p).head(MAX_PREVIEW_ROWS)
    elif p.suffix == ".parquet":
        df = pd.read_parquet(p).head(MAX_PREVIEW_ROWS)

    return {
        "columns": list(df.columns),
        "row_count": len(df),
        "preview": df.to_markdown(index=False),
        "path": path,
    }
