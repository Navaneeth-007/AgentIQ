"""
AgentIQ FastAPI entrypoint.

Endpoints:
  POST /run     — Run a data analysis task
  GET  /health  — Health check
  GET  /trace/{session_id} — Fetch the full step trace for a past run
"""

from __future__ import annotations

import logging
import time
import uuid
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from app.agent.graph import run_agent
from app.guardrails import check_question, check_pii, GuardrailViolation

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s — %(message)s")
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
    session_id = req.session_id or str(uuid.uuid4())

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
        final_state = run_agent(question=req.question, session_id=session_id)
    except Exception as e:
        logger.exception("Agent run failed for session %s", session_id)
        raise HTTPException(status_code=500, detail=f"Agent error: {e}")

    latency_ms = (time.time() - t0) * 1000

    # Store trace
    trace_store[session_id] = final_state

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
    if session_id not in trace_store:
        raise HTTPException(status_code=404, detail="Session not found")
    state = trace_store[session_id]
    return {
        "session_id": session_id,
        "question": state["question"],
        "plan": state["plan"],
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
