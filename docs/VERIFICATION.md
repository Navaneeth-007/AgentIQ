# Verification — October 12, 2026

The final implementation passed 45 automated tests, lint checks, and Docker
Compose configuration validation. The API and frontend were started locally;
both health checks returned HTTP 200. History returned HTTP 401 without the
internal API token and was available with it. The frontend test verifies it opens
directly and completes a demo using automatic server authentication. The new
single-service launcher was started successfully with a loopback-only API and
public Streamlit port. Render successfully built the Docker image and published the service in Singapore
on its free plan. The hosted demo and live Groq analysis both completed. The hosted
Q4 revenue result matched $11,834.55 for Electronics; one Python tool call failed
and the agent recovered through replanning. No benchmark score is claimed.

Live app: [AgentIQ](https://agentiq-9jrm.onrender.com).

Five real Groq checks passed with `openai/gpt-oss-120b`:

| Analysis | Verified result | Outcome |
| --- | --- | --- |
| Highest category revenue in the latest complete quarter | Q4 2024: Electronics, $11,834.55 | SQL result and report agree |
| Monthly revenue chart by region | Highest monthly value: East, November 2024, $6,018.87 | Chart generated, visually inspected, and downloaded as valid PNG |
| Highest customer value | Nina Davis, $6,105.09 in observed delivered revenue | SQL result and report agree |
| Shipping delay greater than seven days | 131 delivered orders | SQL result and report agree |
| Uploaded CSV | Two rows with revenue 123.45 and 10; total 133.45 | Upload, schema inspection, SQL analysis, and report passed |

The four sample results were compared with separately written SQL reference
queries. All four live sample runs produced downloadable HTML reports and had
zero tool failures. These checks establish the tested cases, not a guarantee
that every generated query matches a future business question.

The final sample runs used approximately 18,201 tokens in total. Actual quotas,
latency, and model availability depend on the provider account. The reporter and
default reflection checks make no model requests.

Optional service checks:

- Tavily: current credential rejected; disabled locally.
- OpenWeather: HTTP 401; disabled locally.
- Alpha Vantage: an IBM stock quote was returned.
- NewsAPI: HTTP 401; disabled locally.
- SMTP: no message sent; delivery is unverified.

See [deployment and credential guide](DEPLOYMENT.md) for setup and remaining inputs.
