"""
AgentIQ FastAPI entrypoint.

Endpoints:
  POST /run     — Run a data analysis task
  GET  /health  — Health check
  GET  /trace/{session_id} — Fetch the full step trace for a past run
"""

from __future__ import annotations

import asyncio
import logging
import os
import secrets
import threading
import time
import uuid
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any, Literal

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse
from pydantic import BaseModel

from app.agent.graph import run_agent
from app.capabilities import capabilities
from app.config import ROOT
from app.datasets import MAX_BYTES, dataset_path, import_csv
from app.demo import run_demo
from app.errors import safe_error
from app.guardrails import GuardrailViolation, check_pii, check_question
from app.memory.long_term import get_run, list_runs, save_run

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s — %(message)s"
)
logger = logging.getLogger(__name__)

# In-memory trace store (swap for Redis/Postgres in production)
trace_store: dict[str, Any] = {}
analysis_lock = threading.Lock()


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("AgentIQ starting up")
    yield
    logger.info("AgentIQ shutting down")


app = FastAPI(title="AgentIQ", version="1.0.0", lifespan=lifespan)


@app.middleware("http")
async def protect_access(request: Request, call_next):
    token = os.getenv("AGENTIQ_API_TOKEN", "")
    if token and request.url.path != "/health":
        supplied = request.headers.get("Authorization", "")
        if not secrets.compare_digest(supplied.encode(), f"Bearer {token}".encode()):
            return JSONResponse(
                {"detail": "Enter a valid access code."}, status_code=401
            )
    return await call_next(request)


@app.get("/capabilities")
def feature_status():
    return capabilities()


app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


class RunRequest(BaseModel):
    question: str
    session_id: str | None = None
    mode: Literal["live", "demo"] = "live"
    dataset_id: str | None = None


class RunResponse(BaseModel):
    session_id: str
    final_answer: str
    report_markdown: str
    chart_paths: list[str]
    total_tokens: int
    total_cost_usd: float
    step_count: int
    latency_ms: float


@app.post("/run", response_model=RunResponse)
async def run_task(req: RunRequest):
    session_id = str(uuid.uuid4())

    # Guardrails
    try:
        check_question(req.question)
    except GuardrailViolation as e:
        raise HTTPException(status_code=400, detail=str(e))

    pii = check_pii(req.question)
    if pii:
        logger.warning("PII detected in question for session %s: %s", session_id, pii)

    t0 = time.time()
    run_kwargs = {"question": req.question, "session_id": session_id}
    if req.dataset_id:
        if req.mode != "live":
            raise HTTPException(
                status_code=400, detail="Uploaded CSV analysis requires Live AI mode."
            )
        try:
            run_kwargs["db_path"] = dataset_path(req.dataset_id)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
    if not analysis_lock.acquire(blocking=False):
        raise HTTPException(
            status_code=409,
            detail="Another analysis is running. Please try again when it finishes.",
        )
    try:
        final_state = await asyncio.to_thread(
            run_demo if req.mode == "demo" else run_agent,
            **run_kwargs,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:  # noqa: BLE001 — isolate and sanitize provider errors
        error_text = safe_error(e)
        logger.error("Agent run failed for session %s: %s", session_id, error_text)
        if "429" in error_text or "rate limit" in error_text.lower():
            raise HTTPException(
                status_code=429,
                detail="The configured LLM provider is rate-limited or its quota is exhausted. "
                "Wait for the quota reset and try again.",
            )
        status = getattr(e, "status_code", None)
        if status in {401, 403}:
            raise HTTPException(
                status_code=503,
                detail="The model provider rejected the configured API key or permissions.",
            )
        if status == 404:
            raise HTTPException(
                status_code=503,
                detail="The configured model is unavailable. Choose a model your provider account can access.",
            )
        if status == 413:
            raise HTTPException(
                status_code=503,
                detail="This analysis exceeds the model's free token limit. Ask for a smaller summary or fewer rows.",
            )
        raise HTTPException(status_code=500, detail=f"Agent error: {error_text}")
    finally:
        analysis_lock.release()

    latency_ms = (time.time() - t0) * 1000

    # Store trace
    await asyncio.to_thread(save_run, final_state)

    return RunResponse(
        session_id=session_id,
        final_answer=final_state["final_answer"],
        report_markdown=final_state["report_markdown"],
        chart_paths=final_state["chart_paths"],
        total_tokens=final_state["total_tokens"],
        total_cost_usd=final_state["total_cost_usd"],
        step_count=len(final_state["tool_calls"]),
        latency_ms=round(latency_ms),
    )


@app.get("/trace/{session_id}")
async def get_trace(session_id: str):
    state = get_run(session_id)
    if state is None:
        raise HTTPException(status_code=404, detail="Session not found")
    return {
        "session_id": session_id,
        "question": state["question"],
        "plan": state["plan"],
        "report_markdown": state["report_markdown"],
        "chart_count": len(state["chart_paths"]),
        "tool_calls": [dict(tc) for tc in state["tool_calls"]],
        "step_logs": state["step_logs"],
        "total_tokens": state["total_tokens"],
        "total_cost_usd": state["total_cost_usd"],
    }


@app.post("/datasets")
async def upload_dataset(request: Request, filename: str):
    content = bytearray()
    async for chunk in request.stream():
        content.extend(chunk)
        if len(content) > MAX_BYTES:
            raise HTTPException(
                status_code=413, detail="CSV files must be 5 MB or smaller."
            )
    try:
        return await asyncio.to_thread(import_csv, bytes(content), filename)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.get("/health")
async def health():
    return {"status": "ok", "version": "1.0.0"}


@app.get("/runs")
def history():
    return list_runs()


@app.get("/report/{session_id}", response_class=HTMLResponse)
def report(session_id: str):
    state = get_run(session_id)
    if not state:
        raise HTTPException(status_code=404, detail="Session not found")
    return HTMLResponse(state["report_html"])


@app.get("/chart/{session_id}/{index}")
def chart(session_id: str, index: int):
    state = get_run(session_id)
    if not state or index < 0 or index >= len(state["chart_paths"]):
        raise HTTPException(status_code=404, detail="Chart not found")
    path = Path(state["chart_paths"][index]).resolve()
    if (
        not path.is_relative_to((ROOT / "data" / "reports").resolve())
        or not path.is_file()
    ):
        raise HTTPException(status_code=404, detail="Chart not found")
    return FileResponse(path, media_type="image/png")
