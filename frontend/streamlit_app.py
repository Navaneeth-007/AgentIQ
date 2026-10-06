"""AgentIQ showcase and live analysis interface."""

import os

import requests
import streamlit as st

API_BASE = os.getenv("API_BASE", "http://localhost:8000").rstrip("/")
st.set_page_config(page_title="AgentIQ · Data Analyst", page_icon="📊", layout="wide")
QUESTIONS = [
    "Which product category had the highest revenue last quarter?",
    "Show me monthly sales trends for all regions as a chart.",
    "Which customers have the highest lifetime value?",
    "Find any orders with >7 day shipping delay and summarise them.",
]


def fetch(path):
    response = requests.get(f"{API_BASE}{path}", timeout=15)
    response.raise_for_status()
    return response


with st.sidebar:
    st.title("AgentIQ")
    st.caption("From business questions to evidence.")
    mode = st.radio("Analysis mode", ["Demo", "Live AI"])
    st.caption(
        "Demo runs real calculations on synthetic historical data. Live AI uses your configured model and tools."
    )
    st.divider()
    st.subheader("Try an analysis")
    for q in QUESTIONS:
        if st.button(q, use_container_width=True):
            st.session_state["question"] = q
    st.divider()
    st.subheader("Recent analyses")
    try:
        for run in fetch("/runs").json()[:8]:
            if st.button(
                run["question"], key=run["session_id"], use_container_width=True
            ):
                st.session_state["selected_run"] = run["session_id"]
    except requests.RequestException:
        st.caption("Start the API to see saved analyses.")

st.title("Your data. Clear answers.")
st.markdown("Ask a question, inspect the evidence, and take away a finished report.")
question = st.text_area(
    "What would you like to understand?",
    key="question",
    height=85,
    placeholder=QUESTIONS[0],
)
if st.button("Run analysis", type="primary"):
    if not question.strip():
        st.warning("Enter a question or select an example.")
    else:
        with st.spinner("Querying data and preparing your report…"):
            try:
                response = requests.post(
                    f"{API_BASE}/run",
                    json={
                        "question": question,
                        "mode": "demo" if mode == "Demo" else "live",
                    },
                    timeout=300,
                )
                if not response.ok:
                    st.error(response.json().get("detail", "Analysis failed."))
                else:
                    st.session_state["selected_run"] = response.json()["session_id"]
            except requests.RequestException:
                st.error(
                    "The analysis service is unavailable or timed out. Check that the API is running."
                )

session_id = st.session_state.get("selected_run")
if session_id:
    try:
        trace = fetch(f"/trace/{session_id}").json()
        html = fetch(f"/report/{session_id}").text
        st.subheader(trace["question"])
        cols = st.columns(3)
        cols[0].metric("Tool calls", len(trace["tool_calls"]))
        cols[1].metric("Tokens", f"{trace['total_tokens']:,}")
        cols[2].metric("Estimated cost", f"${trace['total_cost_usd']:.4f}")
        report_tab, trace_tab = st.tabs(["Report", "Execution evidence"])
        with report_tab:
            st.markdown(trace["report_markdown"])
            for index in range(trace["chart_count"]):
                st.image(fetch(f"/chart/{session_id}/{index}").content)
            st.download_button(
                "Download HTML report",
                html,
                file_name=f"agentiq_{session_id[:8]}.html",
                mime="text/html",
            )
        with trace_tab:
            for step in trace["plan"]:
                st.markdown(
                    f"**{step['step_id']}. {step['description']}** · {step['status']}"
                )
            for call in trace["tool_calls"]:
                with st.expander(f"{call['tool_name']} · {call['latency_ms']:.0f} ms"):
                    st.json(call)
    except requests.RequestException:
        st.error("Could not load the saved analysis. Check the API connection.")
