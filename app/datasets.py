"""Import bounded CSV uploads into SQLite for exact SQL analysis."""

import io
import sqlite3
import uuid
from pathlib import Path

import pandas as pd

from app.config import ROOT

UPLOADS = ROOT / "data" / "uploads"
MAX_BYTES = 5 * 1024 * 1024


def import_csv(content: bytes, filename: str) -> dict:
    if len(content) > MAX_BYTES:
        raise ValueError("CSV files must be 5 MB or smaller.")
    if not filename.lower().endswith(".csv"):
        raise ValueError("Upload a CSV file.")
    try:
        frame = pd.read_csv(io.BytesIO(content), nrows=50001)
    except (ValueError, UnicodeError) as exc:
        raise ValueError(
            "Could not read the CSV. Use UTF-8 text with a header row."
        ) from exc
    if frame.empty or len(frame) > 50000 or len(frame.columns) > 100:
        raise ValueError("CSV must contain 1–50,000 rows and at most 100 columns.")
    dataset_id = str(uuid.uuid4())
    UPLOADS.mkdir(parents=True, exist_ok=True)
    path = UPLOADS / f"{dataset_id}.db"
    with sqlite3.connect(path) as connection:
        frame.to_sql("uploaded_data", connection, index=False)
    return {
        "dataset_id": dataset_id,
        "filename": Path(filename).name,
        "table": "uploaded_data",
        "row_count": len(frame),
        "columns": list(frame.columns),
    }


def dataset_path(dataset_id: str) -> str:
    try:
        parsed = str(uuid.UUID(dataset_id))
    except ValueError as exc:
        raise ValueError("Invalid dataset ID.") from exc
    path = UPLOADS / f"{parsed}.db"
    if not path.is_file():
        raise ValueError("Uploaded dataset not found. Upload the CSV again.")
    return str(path)
