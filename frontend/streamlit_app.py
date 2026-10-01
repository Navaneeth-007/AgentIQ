"""
AgentIQ Streamlit frontend.

Features:
- Natural language question input
- Live step-by-step trace viewer (planner → executor → reflector → reporter)
- Inline chart display
- Downloadable HTML report
- Cost + token tracking per run
"""

from __future__ import annotations

import json
import requests
import streamlit as st

API_BASE = "http://localhost:8000"

st.set_page_config(
    page_title="AgentIQ",
    page_icon="🔍",
    layout="wide",
)

# ── Sidebar ───────────────────────────────────────────────────────────────────
with st.sidebar:
    st.markdown("## AgentIQ")
    st.markdown("Agentic data analyst — ask questions, get reports.")
    st.divider()

    st.markdown("### Sample questions")
    samples = [
        "Which product category had the highest revenue last quarter?",
        "Show me monthly sales trends for all regions as a chart.",
        "Which customers have the highest lifetime value?",
        "Find any orders with >7 day shipping delay and summarise them.",
        "Compare our Q3 sales to industry benchmarks — search the web.",
    ]
    for q in samples:
        if st.button(q, use_container_width=True, key=q):
            st.session_state["question"] = q

    st.divider()
    st.caption("Powered by Claude + LangGraph")

# ── Main ──────────────────────────────────────────────────────────────────────
st.title("🔍 AgentIQ")
st.markdown("Ask a data question. The agent plans, queries, analyses, and reports.")

question = st.text_area(
    "Your question",
    value=st.session_state.get("question", ""),
    height=80,
    placeholder="Which product category had the highest revenue last quarter?",
)

run_btn = st.button("Run analysis", type="primary", use_container_width=False)

if run_btn and question.strip():
    st.divider()

    # Show live progress
    progress_placeholder = st.empty()
    trace_placeholder = st.container()

    with st.spinner("Agent is working..."):
        try:
            response = requests.post(
                f"{API_BASE}/run",
                json={"question": question},
                timeout=120,
            )
            response.raise_for_status()
            data = response.json()
        except requests.exceptions.ConnectionError:
            st.error("❌ Could not connect to AgentIQ API. Start it with: `uvicorn app.main:app --reload`")
            st.stop()
        except requests.exceptions.HTTPError as e:
            st.error(f"❌ API error: {e.response.json().get('detail', str(e))}")
            st.stop()

    session_id = data["session_id"]

    # Fetch full trace
    trace_resp = requests.get(f"{API_BASE}/trace/{session_id}", timeout=10)
    trace = trace_resp.json() if trace_resp.ok else {}

    # ── Answer ────────────────────────────────────────────────────────────────
    st.success(f"**Answer:** {data['final_answer']}")

    col1, col2, col3 = st.columns(3)
    col1.metric("Tool calls", data["step_count"])
    col2.metric("Tokens used", f"{data['total_tokens']:,}")
    col3.metric("Est. cost", f"${data['total_cost_usd']:.4f}")

    st.divider()

    # ── Report ────────────────────────────────────────────────────────────────
    tab_report, tab_trace, tab_raw = st.tabs(["📄 Report", "🔍 Execution Trace", "⚙️ Raw State"])

    with tab_report:
        st.markdown(data["report_markdown"])
        if data["chart_paths"]:
            st.markdown("### Charts")
            for path in data["chart_paths"]:
                try:
                    st.image(path)
                except Exception:
                    st.caption(f"Chart saved at: {path}")

        st.download_button(
            "⬇️ Download HTML Report",
            data=requests.get(f"{API_BASE}/trace/{session_id}").text,
            file_name=f"agentiq_report_{session_id[:8]}.json",
            mime="application/json",
        )

    with tab_trace:
        if trace.get("plan"):
            st.markdown("### Plan")
            for step in trace["plan"]:
                status_icon = {"done": "✅", "failed": "❌", "pending": "⏳", "running": "🔄"}.get(
                    step.get("status", ""), "•"
                )
                st.markdown(
                    f"{status_icon} **Step {step['step_id']}** — {step['description']}  "
                    f"*({step['tool']})*"
                )

        if trace.get("step_logs"):
            st.markdown("### Step logs")
            for log in trace["step_logs"]:
                with st.expander(f"{log.get('node', '').upper()} — {log.get('latency_ms', 0):.0f}ms"):
                    st.json(log)

    with tab_raw:
        st.json(trace)

elif run_btn:
    st.warning("Please enter a question.")
