# Security and data boundaries

AgentIQ is a portfolio showcase for trusted reviewers. The hosted interface opens directly and shares history and uploaded data. Internal API authentication protects backend routes; it is not a visitor login.

## Implemented safeguards

- Provider keys stay in server settings and are omitted from the Python worker's environment.
- SQL connections use read-only access for SQLite queries.
- Input validation, heuristic prompt-injection checks, a tool-call budget, bounded recovery, and a 30-second worker timeout limit routine failures.
- CSV uploads have size/row/column limits, and server-managed dataset IDs prevent choosing arbitrary upload paths.
- Reports and chart downloads are resolved from recorded runs.
- Errors redact configured secret values.

These safeguards are not a complete security boundary. Generated Python libraries can access files and the network; the worker is not an OS/container sandbox. Prompt-injection detection is heuristic. Individual accounts, per-user storage, and quota enforcement are not implemented.

## Deployment guidance

Use synthetic or non-sensitive data in the shared showcase. Live questions and selected query results are sent to the configured model provider. Configure visitor authentication or network restrictions, isolated workers, per-user data/quotas, and durable storage before allowing untrusted or sensitive production usage. Keep `.env` out of Git and rotate any credential that has been exposed.

## Reporting an issue

Do not post secrets or exploit details in a public issue. Contact the maintainer through a private contact method on the [GitHub profile](https://github.com/Navaneeth-007). Include the affected component and safe reproduction details. No response-time guarantee or formal security support policy is currently offered.
