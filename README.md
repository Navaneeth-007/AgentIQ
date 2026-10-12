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

Open http://localhost:8501. The interface opens directly; server authentication is automatic. Leave **Demo** selected, click a sidebar example, and select **Run analysis**. The startup script creates the sample database only when it is missing. Do not run the seed script against data you want to retain: it recreates the sample tables.

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
- `LLM_PROVIDER=groq`: set `GROQ_API_KEY` and optionally `GROQ_MODEL`.
- Optional tools use `TAVILY_API_KEY`, `OPENWEATHER_API_KEY`, `ALPHAVANTAGE_API_KEY`, `NEWSAPI_KEY`, or SMTP settings.
- `API_BASE` controls the frontend's API address.

The live graph runs planner → executor → reflector → executor/replan/reporter. Groq uses JSON mode for planning and tool arguments. Reflection uses rule-based checks for failures, remaining steps, and missing charts by default; `LLM_REFLECTION=true` enables model reflection and uses more quota. Schema inspection runs without an LLM call. The reporter builds summaries and tables directly from recorded tool results rather than asking a model to rewrite numbers and dates. Charts receive real SQL rows as `sql_rows`. The app records tool inputs and outputs, failures, latency, estimated token costs, and charts. Failed tools trigger bounded replanning; a 15-call budget ends execution with a best-effort report. Reports and traces persist in `data/history.db`. This history is saved-run retrieval; prior analyses are not automatically supplied as conversational memory.

### Analyze your own CSV

Upload a CSV using the sidebar, click **Use this CSV**, choose its filename under
**Data source**, and select **Live AI**. The API imports the file into SQLite's
`uploaded_data` table; the agent inspects its actual columns before querying.
Uploads are limited to 5 MB, 50,000 rows, and 100 columns. Your full imported data
is used for SQL aggregates, rather than only a preview. Uploads, history, and
reports are shared among trusted reviewers using the same deployment.

```bash
python scripts/run_task.py --question "What was delivered revenue by region in 2024?" --save-report
python -m eval.run_eval --no-llm-grading
```

Evaluation uses live providers and can incur charges. No live evaluation score is claimed. Token costs are approximate model estimates.

## Free hosted LLM and deployment

The example configuration uses Groq through the existing OpenAI SDK; no extra
dependency is required. Create a key at https://console.groq.com/keys and set these
server environment variables (keep the key out of Git and the browser):

```dotenv
LLM_PROVIDER=groq
GROQ_API_KEY=your-groq-key
GROQ_MODEL=openai/gpt-oss-120b
GROQ_FREE_TIER=true
LLM_TIMEOUT_SECONDS=45
```

`GROQ_FREE_TIER=true` sets the displayed estimate to $0; it does not select or
enforce a billing plan. Use it only while your Groq account is on the free plan.
Requests and tokens have per-minute and daily limits shared across your
organization. Check [your limits](https://console.groq.com/settings/limits) and
[Groq rate limits](https://console.groq.com/docs/rate-limits). Restart the API after
changing configuration. A provider switch alone does not guarantee answer accuracy;
verify live reports against database results before deployment.

Alternatively, OpenRouter is still supported:

```dotenv
LLM_PROVIDER=openai
OPENAI_API_KEY=your-openrouter-key
OPENAI_BASE_URL=https://openrouter.ai/api/v1
OPENAI_MODEL=openrouter/free
LLM_TIMEOUT_SECONDS=45
```

You can instead select an available model ID ending in `:free` for more consistent
behavior. The free router can select different models across the agent's calls.
No paid fallback is configured. Free model token estimates are displayed as $0.
Existing `.env` files are not changed when `.env.example` changes.

Free inference has quotas and availability limits; each analysis makes multiple
LLM requests (planner, executor, and reflector), so one analysis consumes
more than one request. Check your account's remaining quota before demonstrations.
See [free router](https://openrouter.ai/openrouter/free) and
[rate limits](https://openrouter.ai/docs/api_reference/limits).

For free Render hosting, use the included `render.yaml` Blueprint and supply
`GROQ_API_KEY` in Render's secret settings. The Docker image starts the full app:
Streamlit uses the host's `PORT`; the API listens privately on localhost.
`python scripts/start_app.py` runs the same setup locally. It generates an internal
API token automatically, so visitors do not enter an access code.

For separate API/frontend services, set the same `AGENTIQ_API_TOKEN` in both
servers and set the frontend's `API_BASE` to the API URL. The frontend forwards
the token automatically. Docker Compose already does this. The token stays on
the server and is not a visitor login. Anyone able to reach the UI can use it.

Render's free filesystem is temporary: uploads, charts and saved history can be
lost on a restart/redeploy. The sample database is recreated automatically.
See [deployment guide](docs/DEPLOYMENT.md) for setup and persistence options.

All routes except the minimal `/health` endpoint are protected, including API docs
and downloads. Use HTTPS. The API allows one analysis at a time to avoid competing
for a free provider's quota. Groq retries transient rate limits; analyses can take
several minutes under the free plan.

This deployment is for you and trusted reviewers. Python runs in a disposable
process that is killed after 30 seconds, with provider credentials omitted from
its environment. It is not an OS sandbox: libraries can still access local files
and the network. Public users require stronger OS/container isolation and
individual accounts with separate data and quotas. See [deployment guide](docs/DEPLOYMENT.md).

## API endpoints

- `GET /health`: process health.
- `GET /capabilities`: configured and enabled features, without credentials.
- `POST /datasets?filename=data.csv`: raw CSV bytes; returns a dataset ID.
- `POST /run`: `{ "question": "…", "mode": "demo" | "live", "dataset_id": null }`; optional dataset ID selects an uploaded CSV. Returns an independently generated run ID and analysis summary.
- `GET /runs`: recent saved runs.
- `GET /trace/{session_id}`: plan, tool inputs and outputs, logs, and report markdown.
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
Regression tests also cover reviewer access, the Streamlit demo flow, CSV import and selection, quarter boundaries, SQL-to-chart data transfer, worker termination, and evidence-based reports. CI needs no live provider credentials.

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

This is a trusted-reviewer application. Access protection is enabled when `AGENTIQ_API_TOKEN` is configured. Saved history and uploaded data are shared among reviewers. Python execution has a process timeout but is not a security sandbox. Web/API/email tools require working credentials and connectivity and are separate from the offline demo. Optional integrations can be disabled with `ENABLE_WEB_SEARCH`, `ENABLE_WEATHER`, `ENABLE_FINANCE`, `ENABLE_NEWS`, or `ENABLE_EMAIL`. After updating a rejected key, re-enable its feature and restart the API. SQLite queries open databases read-only; external Postgres schema inspection is not yet supported. The interface displays completed execution traces, not streamed progress. Generated SQL still needs to match the intended business definitions; the report preserves the query and its actual results for review.
