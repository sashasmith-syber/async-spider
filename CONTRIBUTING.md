# Contributing

## Setup

Python 3.11 is the version used by the container. Python 3.12 is also covered by the test job. From a clean checkout:

```bash
python -m venv .venv
```

Activate `.venv`, then:

```bash
python -m pip install -r requirements.txt
python -m compileall -q crawler_async.py crawler_cli.py metrics_exporter.py example_usage.py
python -m json.tool config.json > /dev/null
python -m unittest discover -s tests -v
docker compose config --quiet
```

On Windows PowerShell, the JSON check is `python -m json.tool config.json | Out-Null`.

## Tests

Tests use localhost fixtures and mocks. Do not add a test that crawls a third-party site. `example_usage.py` contacts the hosts written in that file only when `ASYNC_SPIDER_LIVE_EXAMPLES=1`.

## Changes

Keep pull requests small. Update `README.md` when behavior, configuration, or limitations change. Do not commit `.env`, crawl databases, exports, logs, or virtual environments. Do not add a license file unless the maintainer has chosen one.

GitHub Actions runs the unit tests, Compose validation, an image build, and a Gitleaks scan. Workflow tokens are read-only. Do not use `pull_request_target`.

## Secrets

If you find a real credential, do not open a public issue and do not paste the value. Follow `SECURITY.md`. Deleting a file does not remove a secret from Git history.
