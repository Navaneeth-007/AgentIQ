# Deploying AgentIQ for trusted reviewers

## Required configuration

Only Groq is needed for live database analysis, CSV analysis, charts, history, and
HTML reports. Demo analyses require no external API.

```dotenv
LLM_PROVIDER=groq
GROQ_API_KEY=your-groq-key
GROQ_MODEL=openai/gpt-oss-120b
GROQ_FREE_TIER=true
```

The current account was tested with GPT-OSS 120B. The earlier Llama model was not
available to this account. Confirm models and limits in Groq Console if your
account or provider availability changes. `GROQ_FREE_TIER` affects the displayed
estimate, not provider billing. Keep the account on its free plan if you want
free inference. No paid model fallback is configured.

The UI opens directly. The single-service launcher generates a private internal
API token automatically; there is no access-code field and no token to configure.
For separate services, set the same `AGENTIQ_API_TOKEN` on both servers. It is
forwarded automatically and never displayed to visitors.

## Free Render deployment

1. Push this project, including `render.yaml`, to your GitHub repository. Never push `.env`.
2. Sign into Render and create a **Blueprint** from the repository.
3. Supply only `GROQ_API_KEY` when prompted; the Blueprint selects the free plan.
4. Open the resulting `https://agentiq-….onrender.com` URL after deployment completes.

Alternatively create a **Web Service**, select **Docker** and **Free**, and set
`LLM_PROVIDER=groq`, `GROQ_MODEL=openai/gpt-oss-120b`, `GROQ_FREE_TIER=true`, and
`GROQ_API_KEY`. Keep the default Docker start command. Disable optional tools
without valid credentials, as the Blueprint does. No second service is needed.

The launcher exposes Streamlit at Render's assigned `PORT`; the API listens only
on `127.0.0.1:8000`. Both processes shut down together if either fails. No
provider key or API token needs to be entered in the browser.

The free plan sleeps after idle time, so the first visit can take time to wake.
Its filesystem is temporary: uploaded datasets, charts and history can disappear
on restarts or deployments. Free services cannot attach persistent disks. For
retained data, move to a paid service with a disk mounted at `/app/data`.
See [Render free service limits](https://render.com/docs/free).

A Render web service has a public URL. This version shares history and accepts
analysis requests without a visitor login, so anyone with that URL can use its
quota and view shared data. Keep it for trusted reviewers and non-sensitive data;
restrict access at the hosting/network layer if you need private access.

## Run locally

```bash
source .venv/bin/activate
python scripts/start_api.py
```

In a second terminal:

```bash
source .venv/bin/activate
streamlit run frontend/streamlit_app.py
```

Open http://localhost:8501 directly. Demo uses sample data.
Live AI uses Groq. To analyze your own data, upload a CSV, click **Use this CSV**,
select its filename, and choose Live AI.

## Docker or a hosting service

```bash
docker compose up --build
```

The API starts first; the frontend waits for its health check. Only the API
container receives provider credentials. The frontend receives the internal API
token through its server environment and forwards it automatically.

For separate hosted services:

| Service | Start command | Settings |
| --- | --- | --- |
| API | `python scripts/start_api.py` | Groq variables and `AGENTIQ_API_TOKEN`; the host's `PORT` is honored |
| Frontend | `streamlit run frontend/streamlit_app.py --server.address 0.0.0.0 --server.port <assigned-port>` | `API_BASE=https://your-api-host` and the same `AGENTIQ_API_TOKEN` as the API |

Use HTTPS for both services. Mount persistent storage at `/app/data` when using
the Docker image. It stores the sample database, uploaded datasets, history, and
charts. Without persistence, redeployment can lose that data. Free inference
does not include application hosting or persistent storage.

The API accepts one analysis at a time. A second analysis receives a readable
busy response. Groq's free token limits can cause retry delays; the frontend waits
up to 10 minutes. Check the provider's quota when requests stop completing.

## Optional features and credential checks

These checks were performed on October 12, 2026. Populated environment variables
are not proof that a credential is valid.

| Feature | Configuration | Check result / action |
| --- | --- | --- |
| Web search and external benchmarks | `TAVILY_API_KEY`, or `SERPAPI_KEY` as an alternative | Tavily rejected the current key. Replace it; then set `ENABLE_WEB_SEARCH=true`. |
| Weather enrichment | `OPENWEATHER_API_KEY` | Current key returned HTTP 401. Replace it; then set `ENABLE_WEATHER=true`. Supports 1–5 days of forecast for a city. |
| Stock quotes | `ALPHAVANTAGE_API_KEY` | Returned an IBM quote. Supports quotes only; other financial metrics are not implemented. |
| News enrichment | `NEWSAPI_KEY` | Current key returned HTTP 401. Replace it; then set `ENABLE_NEWS=true`. NewsAPI's free Developer plan is for development/testing, not deployment. |
| Email delivery | `SMTP_HOST`, `SMTP_PORT`, `SMTP_USER`, `SMTP_PASSWORD`, optional `EMAIL_FROM` | Settings exist, but delivery has not been tested. Use your provider's SMTP credential or app password. A test requires an approved recipient. |

Rejected search, weather, and news integrations have been disabled in the local
`.env`. No email was sent. After correcting credentials and flags, restart the
API. The interface's feature list reflects configuration and enablement, not a
live credential check. None of these optional services are required for core
data analysis.

Provider references: [Groq limits](https://console.groq.com/docs/rate-limits),
[Groq models](https://console.groq.com/docs/models),
[NewsAPI terms](https://newsapi.org/terms).

## Scope

This configuration uses automatic server authentication and shared history. It is intended
for you and trusted reviewers. The Python worker's timeout kills its process,
but its libraries can still access files and the network. It is not suitable
for unrestricted public accounts without OS/container isolation, separate data,
and per-user quotas. CSV data stays on your API host, but prompts and selected
query results are sent to the configured model provider during live analysis.

Reports preserve exact database results and queries instead of model-written
statistics. This prevents the report from changing values or their associated
dates; it does not prove the generated SQL answers every business question
correctly. Review the execution evidence for unfamiliar analyses.

## Verification

```bash
python -m pytest -q
ruff check app eval tests frontend scripts
docker compose config --quiet
```

Automated tests run without external API calls or sending email. Live provider
checks consume your account's quota and should be run separately.
