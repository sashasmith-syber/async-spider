# Async Spider

A single-process asynchronous web crawler. It fetches the URLs in `config.json`, keeps results in SQLite, and can export them with `crawler_cli.py`. A separate process, `metrics_exporter.py`, can publish totals from that database.

The container is built from the Docker Official Image `python:3.11-slim`. It is not a Docker Hardened Image. This repository has no measured throughput, success rate, or image size.

## What it does

- Fetches pages with `aiohttp` and parses links with BeautifulSoup.
- Allows only hosts that exactly match, or are subdomains of, `allowed_domains`.
- Refuses non-HTTP(S) URLs, URL userinfo, and private, loopback, link-local, and other non-public destinations unless `security.allow_private_networks` is `true`.
- Verifies TLS certificates by default.
- Does not follow redirects.
- Reads `robots.txt` and refuses the host when that file cannot be retrieved. An HTTP 404 is treated as allowing the crawl, which matches Python's `RobotFileParser`.
- Waits between requests to the same host.
- Caps each response at 2 MB, each page at 200 links, and the memory queue at 10,000 URLs.
- Stores finished rows in SQLite.

PostgreSQL, Grafana dashboards, retries, and multi-node scaling are not implemented. `sql/init.sql` and `k8s/deployment.yaml` are optional examples. The Kubernetes manifest has not been applied to a cluster.

## Requirements

- Python 3.11 (container) or 3.12 (also covered by tests)
- Docker Engine and Docker Compose v2, if you use the container

Install Python dependencies with:

```bash
python -m venv .venv
```

Activate the virtual environment, then:

```bash
python -m pip install -r requirements.txt
```

## Configure

`config.json` is the crawler configuration. The process does not read `.env`.

```json
{
  "crawler": {
    "start_urls": ["https://example.com"],
    "allowed_domains": ["example.com", "www.example.com"],
    "num_workers": 4,
    "requests_per_second": 1.0,
    "max_depth": 3,
    "timeout": 30,
    "db_path": "data/crawl_results.db"
  },
  "security": {
    "verify_ssl": true,
    "allow_private_networks": false,
    "user_agent": "AsyncCrawler/1.0 (+https://example.com/bot)"
  }
}
```

Replace `example.com` with a site you are allowed to crawl. `requests_per_second` must be greater than zero. `allow_private_networks` defaults to false and disables the address check when set to true. Use that only for an isolated local fixture.

Running the crawler contacts every URL in `start_urls`.

## Run locally

```bash
python crawler_async.py
python crawler_cli.py stats
python crawler_cli.py list --limit 20
python crawler_cli.py export-json results.json
python crawler_cli.py export-csv results.csv
python crawler_cli.py domains
```

`crawler_cli.py clear 30` deletes rows older than 30 days. `crawler_cli.py reset` asks for confirmation and deletes stored rows.

`example_usage.py` does not crawl unless `ASYNC_SPIDER_LIVE_EXAMPLES=1`.

## Container

The default Compose file starts only the crawler. It does not publish a host port. The root filesystem is read-only, all capabilities are dropped, and the Dockerfile plus Compose `user` field set uid 1000. Crawl data is the `crawl_data` volume mounted at `/app/data`.

```bash
docker compose build
docker compose up
docker compose exec crawler python crawler_cli.py stats
```

`docker compose up` uses `config.json` and will crawl those URLs.

### Optional monitoring and PostgreSQL

`docker-compose.optional.yml` is not part of a normal start. Prometheus and Grafana use floating `latest` tags. Grafana has no provisioned dashboards. The crawler never connects to PostgreSQL.

Metrics and Grafana listen on `127.0.0.1` only. Prometheus has no authentication.

```bash
# PowerShell
$env:GRAFANA_PASSWORD = "choose-a-password"
docker compose -f docker-compose.yml -f docker-compose.optional.yml --profile monitoring up
```

The metrics process serves:

- `GET /health`
- `GET /metrics` — gauges derived from SQLite, including `crawler_queue_size`, which is always 0
- `GET /stats` — the same totals as JSON, which includes crawled URLs only through the database aggregates, not raw page bodies

Set `DB_PASSWORD` the same way before `--profile postgres`.

## Checks

```bash
python -m compileall -q crawler_async.py crawler_cli.py metrics_exporter.py example_usage.py
python -m json.tool config.json
python -m unittest discover -s tests -v
docker compose config --quiet
```

The unit tests do not crawl third-party sites.

## Threat model

**Untrusted URLs and page bodies.** Operators choose `start_urls`, and pages can contain further links. Links are filtered by scheme, domain, and destination policy, then truncated. HTML is parsed as data. It is not executed. Titles are stored in SQLite and can be exported. Treat the database and exports as untrusted content.

**SSRF and internal networks.** Before a connection, the crawler rejects non-public addresses and names that resolve to them, including loopback, RFC 1918, link-local, and `169.254.169.254`. Redirects are not followed, including redirects from `robots.txt`. This is not a complete SSRF defense. The check and the later connection are separate, so a DNS record can change in between. Unusual address encodings that the resolver accepts but this check does not classify can still be a gap. `allow_private_networks: true` turns the address check off.

**Resource exhaustion.** Workers, timeout, depth, response size, links per page, and queue length are bounded. The crawl also stops waiting after 300 seconds. The rate limiter is per host name, not a global bandwidth cap. SQLite writes are one connection per result.

**Secrets and crawl data.** Do not put credentials in `config.json` or in URLs. `.env` is gitignored and is only for optional Compose passwords. The metrics and stats endpoints do not require authentication. Leave them on localhost. Crawl databases, JSON exports, and CSV exports can contain URLs and titles and must not be committed.

**Trust boundaries.** The operator trusts this process with outbound network access and with whatever it writes into the database. The container drops Linux capabilities and uses a read-only root filesystem; it does not sandbox the crawler against a malicious operator. The Kubernetes file is an example for one replica and a local emptyDir volume. It is not a reviewed production profile.

## Limitations

- Finished rows are kept. URLs left in the memory queue are discarded on timeout or shutdown. There is no resume file.
- There is no retry or backoff.
- `robots.txt` failure refuses the host. A 404 allows it.
- The metrics process is not the crawler and cannot see the live queue.
- The `crawled_links` table is created and is not filled.
- `logging.format` in `config.json` is not applied.
- No license has been selected. See the maintainer before redistributing.

## Older notes

`DOCUMENTATION.md`, `SETUP_GUIDE.md`, `COMMANDS.md`, `STATUS.md`, `COMPLETE.md`, `DELIVERABLES.md`, `FILE_MANIFEST.md`, `PROJECT_INDEX.md`, and `START_HERE.txt` are earlier write-ups. Where they disagree with this file or the code, trust this file and the code.
