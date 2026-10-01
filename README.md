# AgentIQ — Agentic Data Analyst

A production-grade AI agent that accepts natural language questions, autonomously plans multi-step analyses, queries databases, fetches live data via APIs, generates charts, writes reports, and delivers results — all orchestrated with LangGraph.

## Why This Exists

DocuMind answers questions from documents. AgentIQ answers questions from *data*. It plans, executes tools in sequence, recovers from failures, and produces a finished analytical report. The same rigour (guardrails, observability, evaluation) — applied to an agentic loop.

---

## Architecture

```
User Question
      │
      ▼
┌─────────────────────────────────────────────────────┐
│                  LangGraph Agent Loop               │
│                                                     │
│  ┌──────────┐    ┌─────────────┐    ┌───────────┐  │
│  │  Planner │───▶│ Tool Router │───▶│ Executor  │  │
│  └──────────┘    └─────────────┘    └───────────┘  │
│        ▲                                   │        │
│        └──── Reflect / Retry ◀─────────────┘        │
│                                                     │
│  Tools available:                                   │
│    sql_query   → Postgres/SQLite                    │
│    web_search  → Tavily / SerpAPI                   │
│    python_repl → pandas + matplotlib charts         │
│    file_read   → CSV, JSON, Parquet                 │
│    api_fetch   → weather, finance, news APIs        │
│    email_send  → SMTP (optional delivery)           │
└─────────────────────────────────────────────────────┘
      │
      ▼
┌─────────────┐
│  Reporter   │  Synthesises findings → structured markdown + charts
└─────────────┘
      │
      ▼
  HTML Report  +  Streamlit UI  +  optional email
```

### Key Design Decisions

| Decision | Choice | Why |
|----------|--------|-----|
| Orchestration | LangGraph | Explicit state graph — each node is inspectable and testable |
| Reflection | Re-plan node on tool failure | Agent self-corrects rather than halting |
| Memory | Short-term (scratchpad) + long-term (SQLite) | Agent remembers prior analyses per session |
| Tool safety | Input validation + sandboxed Python REPL | No arbitrary shell access |
| Observability | Step-level logging (tool, input, output, latency) | Full trace per query |
| Evaluation | Task completion rate + tool precision + report quality | Quantified, not vibes |

---

## Project Structure

```
agentiq/
├── app/
│   ├── agent/
│   │   ├── graph.py          # LangGraph state graph definition
│   │   ├── nodes.py          # Planner, executor, reflector, reporter nodes
│   │   ├── state.py          # AgentState TypedDict
│   │   └── prompts.py        # System + node-level prompt templates
│   ├── tools/
│   │   ├── sql_tool.py       # Parameterised SQL queries (no injection)
│   │   ├── search_tool.py    # Web search via Tavily
│   │   ├── python_repl.py    # Sandboxed pandas/matplotlib execution
│   │   ├── file_tool.py      # CSV/JSON/Parquet reader
│   │   ├── api_tool.py       # Weather, finance, news API calls
│   │   └── email_tool.py     # SMTP report delivery
│   ├── memory/
│   │   ├── scratchpad.py     # In-session step memory
│   │   └── long_term.py      # SQLite persistence across sessions
│   ├── generation/
│   │   ├── llm_client.py     # Anthropic / OpenAI wrapper (swappable)
│   │   └── cost_tracker.py   # Token cost estimation per run
│   ├── reporting/
│   │   ├── report_builder.py # Markdown → HTML report with charts
│   │   └── chart_renderer.py # matplotlib → base64 inline images
│   ├── guardrails.py         # Input validation, tool call limits, PII detection
│   └── main.py               # FastAPI entrypoint
├── frontend/
│   └── streamlit_app.py      # Chat UI with step-by-step trace viewer
├── eval/
│   ├── metrics.py            # Task completion, tool precision, report quality
│   ├── golden_tasks.json     # Golden evaluation tasks
│   └── run_eval.py           # Evaluation harness
├── tests/
│   ├── test_tools.py
│   ├── test_agent_graph.py
│   └── test_guardrails.py
├── data/
│   ├── sample_db/            # SQLite sample database (sales, hr, ops data)
│   └── reports/              # Generated report output directory
├── scripts/
│   ├── seed_database.py      # Populate sample SQLite DB
│   └── run_task.py           # CLI: run a single agent task
├── .github/workflows/ci.yml
├── docker-compose.yml
├── requirements.txt
├── .env
└── README.md
```

---

## Quickstart

```bash
# 1. Clone and install
git clone https://github.com/yourhandle/agentiq
cd agentiq
pip install -r requirements.txt

# 2. Configure
.env
# Fill in: ANTHROPIC_API_KEY, TAVILY_API_KEY, SMTP credentials (optional)

# 3. Seed sample database
python scripts/seed_database.py

# 4. Run the API
uvicorn app.main:app --reload          # http://localhost:8000

# 5. Run the UI
streamlit run frontend/streamlit_app.py # http://localhost:8501

# 6. Or run a task from CLI
python scripts/run_task.py --question "Which product category had the highest revenue last quarter, and how does it trend over the past year?"
```

---

## Sample Tasks

```
"Which product category had the highest revenue last quarter?"
"Compare our Q3 sales to industry benchmarks — pull the latest data."
"Find any customers with >3 failed payments in the last 30 days and email me a summary."
"Generate a monthly sales trend chart for all regions and save it as a report."
"What's the weather forecast for our top 5 customer cities this week?"
```

---

## Evaluation Results

| Metric | Score |
|--------|-------|
| Task completion rate | — |
| Tool selection precision | — |
| Report coherence (LLM-graded 1–5) | — |
| Avg steps per task | — |
| Avg cost per task (USD) | — |

*Run `python eval/run_eval.py` and paste your results here.*

---

## Differentiators vs. Basic Agent Demos

✅ **LangGraph state graph** — explicit, inspectable, testable  
✅ **Reflection node** — agent self-corrects on tool failure  
✅ **Multi-tool orchestration** — SQL + search + Python + APIs in one run  
✅ **Sandboxed Python REPL** — safe code execution for data analysis  
✅ **Structured HTML reports** — not just text, real deliverables  
✅ **Step-level observability** — full trace logged per query  
✅ **Evaluation harness** — quantified task completion, not vibes  
✅ **Guardrails** — tool call limits, PII detection, injection prevention  

---

## Resume Tie-In

*"DocuMind answers questions from documents. AgentIQ answers questions from data — it plans multi-step analyses, selects tools autonomously, recovers from failures, and delivers a finished report. Built with LangGraph, mirroring the agentic patterns I applied at GE Aerospace."*
