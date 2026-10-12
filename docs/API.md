# API reference

The combined launcher exposes Streamlit publicly and keeps FastAPI at `http://127.0.0.1:8000`. These routes are intended for local development or a separately hosted backend. They are not routed through the public Render UI URL.

If `AGENTIQ_API_TOKEN` is configured, every route except `/health` requires `Authorization: Bearer <token>`. Streamlit supplies it automatically. Locally, interactive OpenAPI documentation is available at `/docs` when the required authorization is provided.

| Method | Route | Purpose |
| --- | --- | --- |
| GET | `/health` | Minimal process health. |
| GET | `/capabilities` | Configured feature availability, without credentials. |
| POST | `/datasets?filename=data.csv` | Import raw CSV bytes and return the dataset ID/schema summary. |
| POST | `/run` | Execute a demo or live analysis and return its run ID/summary. |
| GET | `/runs` | Retrieve recent saved analyses. |
| GET | `/trace/{session_id}` | Retrieve plan, inputs, outputs, errors, report Markdown, and usage. |
| GET | `/report/{session_id}` | Download self-contained HTML. |
| GET | `/chart/{session_id}/{index}` | Retrieve a generated PNG. |

## Analysis request

```json
{
  "question": "Which product category had the highest revenue last quarter?",
  "mode": "live",
  "dataset_id": null
}
```

`mode` is `demo` or `live`. `dataset_id` is the ID returned by CSV upload; omit it or use null for sample data. Uploaded data requires live mode. The API generates a separate run ID for each analysis.

```bash
curl http://localhost:8000/run \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $AGENTIQ_API_TOKEN" \
  --data '{"question":"Which product category had the highest revenue last quarter?","mode":"demo"}'
```

For the combined launcher, its generated token stays inside child processes; use a configured token when testing the API directly.

## CSV upload

```bash
curl 'http://localhost:8000/datasets?filename=sales.csv' \
  -H "Authorization: Bearer $AGENTIQ_API_TOKEN" \
  --data-binary @sales.csv
```

Limits are 5 MB, 50,000 rows, and 100 columns. UTF-8 and a header are required. Dataset IDs are validated and mapped to server-managed SQLite files.

## Operational behavior

Only one analysis runs at a time. A competing request receives HTTP 409. Invalid input, authentication failures, provider quota issues, and provider configuration failures return readable errors. Exact response shapes are defined by the running API's OpenAPI schema; completed tool evidence is under `/trace/{session_id}`.
