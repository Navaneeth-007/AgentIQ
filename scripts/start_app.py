"""Run the public Streamlit UI and a private API in one hosting service."""

import os
import secrets
import signal
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app import config  # noqa: F401
from scripts.seed_database import DB_PATH, seed


def main():
    if not DB_PATH.exists():
        seed()
    environment = os.environ.copy()
    environment.setdefault("AGENTIQ_API_TOKEN", secrets.token_urlsafe(32))
    if not environment["AGENTIQ_API_TOKEN"]:
        environment["AGENTIQ_API_TOKEN"] = secrets.token_urlsafe(32)
    environment["API_BASE"] = "http://127.0.0.1:8000"
    children = []

    def stop(*_):
        raise SystemExit(0)

    signal.signal(signal.SIGTERM, stop)
    signal.signal(signal.SIGINT, stop)
    try:
        api = subprocess.Popen(
            [
                sys.executable,
                "-m",
                "uvicorn",
                "app.main:app",
                "--host",
                "127.0.0.1",
                "--port",
                "8000",
            ],
            cwd=ROOT,
            env=environment,
        )
        children.append(api)
        for _ in range(60):
            if api.poll() is not None:
                raise RuntimeError("Analysis service exited during startup")
            try:
                with urllib.request.urlopen(
                    environment["API_BASE"] + "/health", timeout=1
                ):
                    break
            except OSError:
                time.sleep(0.5)
        else:
            raise RuntimeError("Analysis service did not become ready")
        ui = subprocess.Popen(
            [
                sys.executable,
                "-m",
                "streamlit",
                "run",
                "frontend/streamlit_app.py",
                "--server.address",
                "0.0.0.0",
                "--server.port",
                environment.get("PORT", "8501"),
                "--server.headless",
                "true",
                "--browser.gatherUsageStats",
                "false",
            ],
            cwd=ROOT,
            env=environment,
        )
        children.append(ui)
        while all(child.poll() is None for child in children):
            time.sleep(0.5)
        raise RuntimeError("An application service exited unexpectedly")
    finally:
        for child in children:
            if child.poll() is None:
                child.terminate()
        for child in children:
            try:
                child.wait(timeout=10)
            except subprocess.TimeoutExpired:
                child.kill()
                child.wait()


if __name__ == "__main__":
    main()
