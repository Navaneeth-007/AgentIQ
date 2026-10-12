# Contributing

## Local development

Use Python 3.11+ and a virtual environment:

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements-dev.txt
python scripts/start_app.py
```

Demo requires no external key. To work on live analysis, copy `.env.example` to `.env` and configure the provider as described in [configuration](docs/CONFIGURATION.md).

## Before submitting a change

1. Keep changes focused and describe the resulting behavior.
2. Add meaningful tests for new logic or regressions. Avoid live provider calls in CI.
3. Run `make check` on a fresh sample database.
4. Update relevant documentation if configuration, API behavior, or supported features change.
5. Never include credentials, uploads, generated reports, databases, or evaluation results in commits.

`make seed` recreates the synthetic sample tables. Use it only for a fresh checkout or disposable test data. `make clean` removes Python/tool caches without touching `.env`, `.venv`, uploads, reports, or history.

## Live evaluation

The optional harness is separate from the automated test suite:

```bash
python -m eval.run_eval --tasks task_001 --no-llm-grading
```

Even without LLM grading, task execution uses the configured live provider and consumes quota. Some golden tasks need optional integration credentials. Results are written to a Git-ignored file; do not claim a benchmark score without a recorded run and its configuration.

## Documentation assets

README screenshots are actual app captures using synthetic data. Update captions when replacing images. Keep assets under `docs/assets/` and avoid including private data or credentials.
