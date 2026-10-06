# AgentIQ — Agentic Data Analyst

AgentIQ turns business questions into database analyses, charts, and downloadable HTML reports. The Streamlit interface offers a credential-free showcase and a live LangGraph agent with planning, tool execution, reflection, and reporting.

## Run the showcase

Use Python 3.11 or newer. From the project folder:

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python scripts/start_api.py
```

In another terminal, from the same folder:

```bash
source .venv/bin/activate
streamlit run frontend/streamlit_app.py
```

Open http://localhost:8501. Leave **Demo** selected, click a sidebar example, and select **Run analysis**. The startup script creates the sample database only when it is missing. Do not run the seed script against data you want to retain: it recreates the sample tables.

### Suggested presentation (3 minutes)

1. Run **Which product category had the highest revenue last quarter?** Explain that relative dates use the latest complete quarter in the dataset.
2. Open **Execution evidence** to show schema inspection, date inspection, the SQL query, and chart rendering.
3. Download the HTML report: the chart is embedded, so the file works offline.
4. Run **Show me monthly sales trends for all regions as a chart.** Compare regional trends.
5. Select an analysis under **Recent analyses** to demonstrate persistent history.
6. If provider credentials are configured, switch to **Live AI** and ask a new data question to demonstrate autonomous planning.

Demo mode performs real calculations on the bundled SQLite database using four predefined analyses. It does not call or simulate an LLM. The dataset contains synthetic 2023–2024 records: 2,000 orders, 200 customers, 24 products, and 80 employees. Delivered orders define revenue. “Lifetime value” in the showcase means observed customer revenue within this dataset. Shipping analyses cover delivered orders with a recorded delay over seven days.

## Live AI mode

Copy `.env.example` to `.env` if no configuration exists, then fill in the selected provider's key. Existing environment variables take precedence over `.env`. Restart the API after changes.

- `LLM_PROVIDER=anthropic`: set `ANTHROPIC_API_KEY` and optionally `ANTHROPIC_MODEL`.
- `LLM_PROVIDER=openai`: set `OPENAI_API_KEY`, `OPENAI_MODEL`, and optionally `OPENAI_BASE_URL` for a compatible endpoint.
- Optional tools use `TAVILY_API_KEY`, `OPENWEATHER_API_KEY`, `ALPHAVANTAGE_API_KEY`, `NEWSAPI_KEY`, or SMTP settings.
- `API_BASE` controls the frontend's API address.

The live graph runs planner → executor → reflector → executor/replan/reporter. It records tool inputs, failures, latency, estimated token costs, and charts. Failed tools trigger bounded replanning; a 15-call budget ends execution with a best-effort report. Reports and traces persist in `data/history.db`. This history is saved-run retrieval; prior analyses are not automatically supplied as conversational memory.

```bash
python scripts/run_task.py --question "What was delivered revenue by region in 2024?" --save-report
python -m eval.run_eval --no-llm-grading
```

Evaluation uses live providers and can incur charges. No live evaluation score is claimed. Token costs are approximate model estimates.

## API

- `GET /health`: process health.
- `POST /run`: `{ "question": "…", "mode": "demo" | "live" }`; returns an independently generated run ID and analysis summary.
- `GET /runs`: recent saved runs.
- `GET /trace/{session_id}`: plan, tool inputs, logs, and report markdown.
- `GET /report/{session_id}`: self-contained HTML report.
- `GET /chart/{session_id}/{index}`: chart PNG.
- http://localhost:8000/docs: interactive API reference.

## Docker

```bash
cp .env.example .env  # only if no .env already exists
mkdir -p data
docker compose up --build
```

Open http://localhost:8501. The API seeds an empty mounted data folder on startup. `.dockerignore` excludes credentials, local environments, and generated data from the image.

## Verification

```bash
python -m pytest -q
ruff check app eval tests frontend scripts
```

Integration tests run all four demo questions against real sample data and verify persistence, report downloads, chart bytes, input validation, and retry routing. Seed the sample DB before running tests on a fresh checkout. CI performs seeding automatically.

## Project layout

- `app/agent/`: LangGraph state, nodes, and prompts.
- `app/tools/`: SQL, Python, files, web search, APIs, email.
- `app/demo.py`: predefined showcase analyses with actual SQL and charts.
- `app/memory/long_term.py`: persistent run store.
- `app/reporting/`: HTML export with embedded charts.
- `frontend/`: Streamlit interface.
- `scripts/`: startup, sample seeding, live task CLI.
- `tests/`, `eval/`: regression checks and live evaluation harness.

## Scope and deployment limits

This is a local showcase application. The API has no authentication, and saved history is shared among users of an instance. Restrict access to trusted users. Python execution uses restricted builtins but exposed analysis libraries still have filesystem capabilities; its thread timeout does not kill running code. Run untrusted generated code in an isolated worker before exposing the app publicly. Web/API/email tools require credentials and connectivity and are separate from the offline demo. SQLite queries open databases read-only; external Postgres schema inspection is not yet supported. The interface displays completed execution traces, not streamed progress.
