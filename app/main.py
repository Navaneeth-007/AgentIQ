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
import time
import uuid
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any, Literal

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse
from pydantic import BaseModel

from app.agent.graph import run_agent
from app.config import ROOT
from app.demo import run_demo
from app.guardrails import GuardrailViolation, check_pii, check_question
from app.memory.long_term import get_run, list_runs, save_run

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s — %(message)s"
)
logger = logging.getLogger(__name__)

# In-memory trace store (swap for Redis/Postgres in production)
trace_store: dict[str, Any] = {}


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("AgentIQ starting up")
    yield
    logger.info("AgentIQ shutting down")


app = FastAPI(title="AgentIQ", version="1.0.0", lifespan=lifespan)

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
    try:
        final_state = await asyncio.to_thread(
            run_demo if req.mode == "demo" else run_agent,
            question=req.question,
            session_id=session_id,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.exception("Agent run failed for session %s", session_id)
        error_text = str(e)
        if "429" in error_text or "rate limit" in error_text.lower():
            raise HTTPException(
                status_code=429,
                detail="The configured OpenRouter model is rate-limited or its free quota is exhausted. "
                "Wait for the quota reset, choose another available model, or add credits.",
            )
        raise HTTPException(status_code=500, detail=f"Agent error: {e}")

    latency_ms = (time.time() - t0) * 1000

    # Store trace
    save_run(final_state)

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
        "tool_calls": [
            {k: v for k, v in tc.items() if k != "tool_output"}
            for tc in state["tool_calls"]
        ],
        "step_logs": state["step_logs"],
        "total_tokens": state["total_tokens"],
        "total_cost_usd": state["total_cost_usd"],
    }


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
