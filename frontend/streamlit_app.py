"""AgentIQ showcase and live analysis interface."""

import os
import sys
from pathlib import Path

import requests
import streamlit as st

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from app import config  # noqa: F401 -- load local server configuration

API_BASE = os.getenv("API_BASE", "http://localhost:8000").rstrip("/")
st.set_page_config(page_title="AgentIQ · Data Analyst", page_icon="📊", layout="wide")

# Authentication is between servers; visitors never enter or receive this secret.
access_code = os.getenv("AGENTIQ_API_TOKEN", "")
HEADERS = {"Authorization": f"Bearer {access_code}"} if access_code else {}
selected_dataset_id = None
QUESTIONS = [
    "Which product category had the highest revenue last quarter?",
    "Show me monthly sales trends for all regions as a chart.",
    "Which customers have the highest lifetime value?",
    "Find any orders with >7 day shipping delay and summarise them.",
]


def fetch(path):
    response = requests.get(f"{API_BASE}{path}", headers=HEADERS, timeout=15)
    response.raise_for_status()
    return response


with st.sidebar:
    st.title("AgentIQ")
    st.caption("From business questions to evidence.")
    try:
        features = fetch("/capabilities").json()
    except requests.RequestException as exc:
        if exc.response is not None and exc.response.status_code == 401:
            st.error(
                "The frontend and analysis service have mismatched server credentials."
            )
        else:
            st.error("Cannot connect to the analysis service.")
        st.stop()
    mode = st.radio("Analysis mode", ["Demo", "Live AI"])
    if mode == "Live AI" and not features["live_ai"]:
        st.warning("Configure the model API key on the analysis service first.")
    with st.expander("Available features"):
        for name in [
            "database_analysis",
            "charts",
            "web_search",
            "weather",
            "finance",
            "news",
            "email",
        ]:
            st.write(
                f"{'✓' if features[name] else '—'} {name.replace('_', ' ').title()}"
            )
        st.caption(
            "Availability reflects configuration; provider credentials and quotas may still need verification."
        )
    st.divider()
    uploaded = st.file_uploader(
        "Upload your data",
        type=["csv"],
        help="CSV with a header row, up to 5 MB and 50,000 rows.",
    )
    if uploaded is not None and st.button("Use this CSV"):
        try:
            response = requests.post(
                f"{API_BASE}/datasets",
                params={"filename": uploaded.name},
                data=uploaded.getvalue(),
                headers=HEADERS,
                timeout=30,
            )
            if response.ok:
                st.session_state["dataset"] = response.json()
                st.session_state.pop("selected_run", None)
            else:
                st.error(response.json().get("detail", "Upload failed."))
        except requests.RequestException:
            st.error("Cannot upload the file. Check the API connection.")
    if "dataset" in st.session_state:
        dataset = st.session_state["dataset"]
        source = st.radio("Data source", ["Sample business data", dataset["filename"]])
        if source != "Sample business data":
            selected_dataset_id = dataset["dataset_id"]
            st.caption(
                f"{dataset['row_count']:,} rows · {len(dataset['columns'])} columns"
            )
            if mode == "Demo":
                st.info("Select Live AI to analyze your CSV.")
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
if st.button(
    "Run analysis",
    type="primary",
    disabled=(selected_dataset_id is not None and mode == "Demo")
    or (mode == "Live AI" and not features["live_ai"]),
):
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
                        "dataset_id": selected_dataset_id,
                    },
                    timeout=600,
                    headers=HEADERS,
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
