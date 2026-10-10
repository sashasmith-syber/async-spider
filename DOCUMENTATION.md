> Accuracy note: this file is an earlier guide. The running code is a single-process SQLite crawler. The image is `python:3.11-slim`, not a Docker Hardened Image. There is no retry, PostgreSQL client, Grafana dashboard, or measured success rate. Use `README.md` for setup and limitations.

# Async crawler notes

## Table of Contents
1. [Overview](#overview)
2. [Architecture](#architecture)
3. [Security](#security)
4. [Installation & Setup](#installation--setup)
5. [Configuration](#configuration)
6. [Running the Crawler](#running-the-crawler)
7. [API Reference](#api-reference)
8. [Docker Deployment](#docker-deployment)
9. [Monitoring & Logging](#monitoring--logging)
10. [Troubleshooting](#troubleshooting)
11. [Performance Tuning](#performance-tuning)
12. [Best Practices](#best-practices)

---

## Overview

This is a production-ready asynchronous web crawler built with Python 3.11, designed for high-throughput, scalable crawling operations. It respects `robots.txt`, implements intelligent rate limiting, and stores results in SQLite or PostgreSQL.

### Key Features
- ✅ **Async/Await Architecture**: Handle thousands of concurrent requests
- ✅ **Rate Limiting**: Per-domain request throttling to avoid overwhelming servers
- ✅ **Robots.txt Compliance**: Automatically respects crawl directives
- ✅ **Duplicate Detection**: Efficient URL deduplication using MD5 hashing
- ✅ **Error Handling**: Automatic retries with exponential backoff
- ✅ **Database Persistence**: SQLite for lightweight storage, PostgreSQL for scale
- ✅ **Docker Hardened Images**: Security-first containerization
- ✅ **Metrics & Monitoring**: Prometheus metrics + Grafana dashboards

---

## Architecture

### Component Overview

```
┌─────────────────────────────────────────────────────────┐
│                   AsyncCrawler                          │
│                                                         │
│  ┌──────────────┐  ┌──────────────┐  ┌────────────────┐│
│  │   URLFilter  │  │ RateLimiter  │  │ RobotsParser   ││
│  │              │  │              │  │                ││
│  │ • Whitelist  │  │ • Per-domain │  │ • Cache robots ││
│  │ • Depth ctrl │  │   throttling │  │ • Respect dirs ││
│  │ • Dedup      │  │ • Backoff    │  │ • User-agent   ││
│  └──────────────┘  └──────────────┘  └────────────────┘│
│                                                         │
│  ┌────────────────────────────────────────────────────┐ │
│  │              Worker Pool (4-16 coroutines)         │ │
│  │  • Concurrent URL fetching                         │ │
│  │  • HTML parsing                                    │ │
│  │  • Link extraction                                 │ │
│  └────────────────────────────────────────────────────┘ │
│                                                         │
│  ┌────────────────────────────────────────────────────┐ │
│  │         Database Layer (SQLite/PostgreSQL)         │ │
│  │  • Store crawl results                             │ │
│  │  • Link relationships                              │ │
│  │  • Pagination support                              │ │
│  └────────────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────────┘
```

### Data Flow

1. **URL Queue**: Start URLs enter async queue
2. **Worker Processing**: Workers fetch URLs concurrently
3. **Parsing**: Extract title, links, metadata
4. **Filtering**: Check whitelist, depth, robots.txt
5. **Deduplication**: MD5 hash prevents re-crawling
6. **Storage**: Results saved to database
7. **Queue New URLs**: Found links added back to queue

---

## Security

### Container image

The Dockerfile uses the Docker Official Image `python:3.11-slim`. It does not use a Docker Hardened Image. Official Hardened Python images are published from `dhi.io` under separate tags and are not configured in this repository. Do not pull `ghcr.io/docker/hardened-python:3.11-slim`; that reference is not the image this project builds.

### Container Security Features

The default Compose service sets `read_only: true`, `cap_drop: [ALL]`, and `no-new-privileges:true`. Data is a volume at `/app/data`, not a tmpfs. There is no `NET_OUTBOUND` capability.

### Network Security

- **Isolated network**: `crawler-network` bridge (subnet: 172.28.0.0/16)
- **No host networking**: Container uses bridge network only
- **SSL/TLS support**: aiohttp handles HTTPS
- **Certificate validation**: Configurable in `config.json`

### Application Security

- **No hardcoded secrets**: Use environment variables (`.env`)
- **Database credentials**: Managed via `DB_PASSWORD` env var
- **User-Agent validation**: Identify your crawler properly
- **robots.txt compliance**: Respect server directives
- **Rate limiting**: Avoid overwhelming target servers
- **Input validation**: URL parsing and sanitization

---

## Installation & Setup

### Prerequisites

- Docker 20.10+ and Docker Compose 2.0+
- Python 3.11+ (for local development)
- 2GB+ available disk space
- Network access for crawling

### Quick Start (Docker)

```bash
# Clone or navigate to project directory
cd web-crawler

# Build the image
docker-compose build

# Start services
docker-compose up -d

# View logs
docker-compose logs -f crawler
```

### Local Development Setup

```bash
# Create virtual environment
python3.11 -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Run crawler directly
python crawler_async.py
```

---

## Configuration

### config.json Structure

```json
{
  "crawler": {
    "start_urls": ["https://example.com"],
    "allowed_domains": ["example.com", "www.example.com"],
    "num_workers": 4,                    // Concurrent coroutines
    "requests_per_second": 1.0,          // Rate limit per domain
    "max_depth": 3,                      // URL depth relative to root
    "timeout": 30,                       // Request timeout in seconds
    "db_path": "/app/data/crawl_results.db"
  },
  "logging": {
    "level": "INFO",                     // DEBUG, INFO, WARNING, ERROR
    "format": "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
  },
  "security": {
    "verify_ssl": false,                 // SSL certificate verification
    "user_agent": "AsyncCrawler/1.0 (+http://example.com/bot)"
  },
  "database": {
    "type": "sqlite",                    // sqlite or postgresql
    "connection_timeout": 5
  }
}
```

### Environment Variables

```bash
# .env file
LOG_LEVEL=INFO
WORKERS=4
DB_PASSWORD=your_secure_password
GRAFANA_PASSWORD=admin
PYTHON_UNBUFFERED=1
```

### Performance Tuning

```json
{
  "crawler": {
    "num_workers": 8,              // Increase for more parallelism
    "requests_per_second": 2.0,    // Increase to crawl faster (be respectful!)
    "max_depth": 5,                // Crawl deeper (may take longer)
    "timeout": 60                  // Longer timeout for slow servers
  }
}
```

---

## Running the Crawler

### Docker Compose (Recommended)

```bash
# Start all services
docker-compose up -d

# View crawler logs
docker-compose logs -f crawler

# Stop services
docker-compose down

# Remove volumes (cleanup data)
docker-compose down -v
```

### Docker Run (Single Container)

```bash
# Build image
docker build -t web-crawler:1.0 .

# Run container
docker run -d \
  --name crawler \
  -v crawl_data:/app/data \
  -v $(pwd)/config.json:/app/config.json:ro \
  -e WORKERS=4 \
  web-crawler:1.0
```

### Kubernetes Deployment

```bash
# Create namespace
kubectl create namespace crawler-app

# Create ConfigMap for configuration
kubectl create configmap crawler-config \
  --from-file=config.json \
  -n crawler-app

# Deploy using Kustomization or Helm
kubectl apply -f k8s/deployment.yaml -n crawler-app

# View logs
kubectl logs -f deployment/web-crawler -n crawler-app
```

---

## API Reference

### AsyncCrawler Class

#### Constructor

```python
crawler = AsyncCrawler(
    start_urls: List[str],           # URLs to begin crawling
    allowed_domains: List[str],      # Domains to stay within
    num_workers: int = 4,            # Number of concurrent workers
    requests_per_second: float = 1.0,# Rate limit per domain
    max_depth: int = 3,              # Maximum URL depth
    timeout: int = 30,               # Request timeout in seconds
    db_path: str = "crawl_results.db"# SQLite database path
)
```

#### Methods

```python
# Run the crawler
stats = await crawler.run(max_crawls: Optional[int] = None)
# Returns: { "crawled": int, "failed": int, "skipped": int, "total_links": int, ... }

# Get results from database
results = crawler.db.get_results(limit: int = 100)
# Returns: List[Dict] with columns: url, status_code, title, error, ...
```

#### Events and Callbacks

```python
# Hook into crawl results
async def process_result(result: CrawlResult):
    print(f"Crawled: {result.url} ({result.status_code})")
    print(f"Found {len(result.links)} links")

# Modify rate limiting per domain
await crawler.rate_limiter.wait(domain)

# Check if URL passes filtering
should_crawl = await crawler.url_filter.should_crawl(url)
```

### CrawlResult Dataclass

```python
@dataclass
class CrawlResult:
    url: str                     # Crawled URL
    status_code: int             # HTTP status (0 if error)
    title: Optional[str]         # Page title from <title> tag
    links: List[str]             # Extracted links
    error: Optional[str]         # Error message if failed
    crawled_at: str              # ISO8601 timestamp
    response_time: float         # Seconds to fetch + parse
```

---

## Docker Deployment

### Build Arguments

```dockerfile
ARG PYTHON_VERSION=3.11
ARG BASE_IMAGE=ghcr.io/docker/hardened-python:${PYTHON_VERSION}-slim
```

### Multi-Stage Build Explanation

**Stage 1: Builder**
- Uses standard Python image
- Installs dependencies from `requirements.txt`
- Creates `.local/` directory with all packages

**Stage 2: Runtime (DHI)**
- Uses Docker Hardened Python image
- Copies only `.local/` from builder
- Minimal footprint (~120MB)
- No build tools or compilers included
- Ready for production

### Image Security Scanning

```bash
# Scan with Docker Scout
docker scout cves web-crawler:1.0

# Scan with Trivy
trivy image web-crawler:1.0

# View image layers
docker history web-crawler:1.0
```

### Push to Registry

```bash
# Tag image
docker tag web-crawler:1.0 your-registry/web-crawler:1.0

# Push
docker push your-registry/web-crawler:1.0

# Deploy from registry
docker pull your-registry/web-crawler:1.0
docker run -d your-registry/web-crawler:1.0
```

---

## Monitoring & Logging

### Prometheus Metrics

Access Prometheus at `http://localhost:9090`

Key metrics:
- `crawler_urls_processed_total`: Total URLs crawled
- `crawler_urls_failed_total`: Failed crawl attempts
- `crawler_response_time_seconds`: Request latency
- `crawler_queue_size`: Pending URLs in queue

### Grafana Dashboards

Access Grafana at `http://localhost:3000` (default: admin/admin)

Pre-configured dashboards:
- **Crawler Status**: Real-time crawl progress
- **Performance**: Response times, throughput
- **Errors**: Failed requests, error rates
- **Database**: Query performance

### Log Aggregation

```bash
# View structured logs from Docker
docker logs --timestamps --follow crawler

# Export logs
docker logs crawler > crawler.log

# With docker-compose
docker-compose logs --timestamps > logs.txt
```

### Python Logging Configuration

```python
import logging

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

logger = logging.getLogger(__name__)
logger.debug("Detailed debug info")
logger.info("General information")
logger.warning("Warning message")
logger.error("Error occurred")
```

---

## Troubleshooting

### Container Won't Start

**Symptoms**: `docker-compose up` fails immediately

**Solution**:
```bash
# Check logs
docker-compose logs crawler

# Rebuild image
docker-compose build --no-cache

# Check available memory
docker system df

# Clean up old containers
docker system prune
```

### High Memory Usage

**Symptoms**: Container uses >1GB RAM

**Solution**:
```python
# Reduce number of workers in config.json
"num_workers": 2,  // Was 4 or 8

# Increase timeout to process faster
"timeout": 60
```

### URLs Not Being Crawled

**Symptoms**: Queue empties but few URLs crawled

**Possible causes**:
- Domain not in `allowed_domains`
- URLs exceed `max_depth`
- Blocked by robots.txt
- Rate limiter too aggressive

**Debug**:
```bash
# Check logs for filtering reasons
docker logs crawler | grep -i "skip\|block\|depth"

# List robots.txt issue
docker logs crawler | grep -i "robots"

# Verify config
docker exec crawler cat config.json
```

### Database Errors

**Symptoms**: "sqlite3.DatabaseError: database is locked"

**Solution**:
```bash
# Stop crawler
docker-compose down

# Remove database
rm crawl_results.db

# Restart
docker-compose up -d
```

### Network Connectivity Issues

**Symptoms**: "Connection refused" or "Host unreachable"

**Debug**:
```bash
# Check network
docker network ls
docker network inspect crawler-network

# Test DNS resolution
docker exec crawler nslookup example.com

# Check firewall
sudo ufw allow 8080/tcp  # Linux
```

---

## Performance Tuning

### Throughput Optimization

| Setting | Impact | Recommendation |
|---------|--------|-----------------|
| `num_workers` | Concurrent requests | 4-8 for most sites, 16+ for large crawls |
| `requests_per_second` | Rate limit | 1-2 for respect, 5+ for owned infrastructure |
| `timeout` | Failed requests | 30-60 seconds balanced |
| `max_depth` | Crawl size | 2-3 for breadth, 5+ for depth |

### Database Performance

```sql
-- Create indexes for faster queries
CREATE INDEX idx_url ON crawl_results(url);
CREATE INDEX idx_crawled_at ON crawl_results(crawled_at);
CREATE INDEX idx_status_code ON crawl_results(status_code);

-- Archive old results
DELETE FROM crawl_results WHERE crawled_at < date('now', '-30 days');
```

### Resource Limits

```yaml
# docker-compose.yml
services:
  crawler:
    deploy:
      resources:
        limits:
          cpus: '2'
          memory: 1G
        reservations:
          cpus: '1'
          memory: 512M
```

---

## Best Practices

### Ethical Crawling

1. **Respect robots.txt**: Always check `robots.txt` before crawling
2. **Identify yourself**: Use meaningful User-Agent header
3. **Rate limit**: Don't overwhelm target servers (start with 1 req/sec)
4. **Cache results**: Avoid re-crawling same URLs
5. **Handle errors gracefully**: Retry with backoff, don't spam errors
6. **Respect NoIndex directives**: Don't crawl pages marked `<meta name="robots" content="noindex">`

### Operational Safety

1. **Monitor resources**: Track memory, CPU, disk space
2. **Set timeouts**: Prevent hanging on slow servers
3. **Backup data**: Regularly export crawl results
4. **Update dependencies**: Keep packages patched
5. **Test in staging**: Run full crawls on test domains first
6. **Log everything**: Enable detailed logging for debugging

### Security Hardening

1. **Use HTTPS only**: Set `verify_ssl: true` in production
2. **Rotate credentials**: Change database passwords regularly
3. **Network isolation**: Use VPC/firewall to restrict access
4. **Scan images**: Run `docker scout` on all images
5. **Non-root user**: Always run containers as unprivileged user
6. **Secret management**: Use Docker secrets or external vaults for credentials

### Scalability

1. **Horizontal scaling**: Deploy multiple crawler instances
2. **Load balancing**: Use Redis queue for distributed crawling
3. **Database replication**: PostgreSQL replicas for read scaling
4. **Caching**: Add Redis for URL deduplication across instances
5. **Partitioning**: Split crawl jobs by domain or URL prefix

---

## Support & Contributing

For issues, suggestions, or contributions:

1. Check existing issues/documentation
2. Provide reproducible steps
3. Include Docker version, OS, and resource usage
4. Share relevant logs and configuration

---

## License

See LICENSE file in repository.
