"""Start the showcase API, creating sample data only if missing."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import uvicorn

from scripts.seed_database import DB_PATH, seed

if __name__ == "__main__":
    if not DB_PATH.exists():
        seed()
    uvicorn.run("app.main:app", host="0.0.0.0", port=8000)
