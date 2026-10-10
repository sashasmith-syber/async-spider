> Accuracy note: this file is an earlier write-up. Where it disagrees with the code, trust README.md. The image is python:3.11-slim, not a Docker Hardened Image. Performance numbers, production-ready claims, PostgreSQL crawling, Grafana dashboards, retries, and horizontal scaling are not implemented.

# Web Crawler - Setup & Deployment Guide

## Quick Start (5 minutes)

### Option 1: Docker Compose (Recommended)

```bash
# Clone repository
cd web-crawler

# Create .env file
cp .env.example .env
# Edit .env with your settings

# Build and start
docker-compose up -d

# View logs
docker-compose logs -f crawler

# Access services
- Crawler metrics: http://localhost:8080/metrics
- Prometheus: http://localhost:9090
- Grafana: http://localhost:3000
```

### Option 2: Local Development

```bash
# Create virtual environment
python3.11 -m venv venv
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Edit config.json with your URLs
nano config.json

# Run crawler
python crawler_async.py

# View results
python crawler_cli.py stats
python crawler_cli.py list
```

---

## Full Setup Guide

### Prerequisites Check

```bash
# Check Docker
docker --version  # Should be 20.10+
docker-compose --version  # Should be 2.0+

# Check Python (for local development)
python3.11 --version

# Check disk space
df -h  # At least 2GB free
```

### Step 1: Configure Environment

```bash
# Copy example environment
cp .env.example .env

# Edit configuration
nano .env

# Key settings:
# - LOG_LEVEL: INFO, DEBUG, WARNING
# - WORKERS: 2-8 (depends on server)
# - REQUESTS_PER_SECOND: 0.5-2 (be respectful)
# - DB_PASSWORD: Strong password for production
```

### Step 2: Configure Crawl Targets

```bash
# Edit config.json
nano config.json

# Critical settings:
{
  "crawler": {
    "start_urls": ["https://yourtarget.com"],
    "allowed_domains": ["yourtarget.com", "www.yourtarget.com"],
    "num_workers": 4,
    "max_depth": 3
  }
}
```

### Step 3: Build Docker Image

```bash
# Build with Docker Hardened Images
docker-compose build

# Verify image
docker images | grep web-crawler

# Check image security (optional)
docker scout cves web-crawler
```

### Step 4: Start Services

```bash
# Start all services
docker-compose up -d

# Verify services are running
docker-compose ps

# Expected output:
# NAME              STATUS
# web-crawler       Up 2 seconds (healthy)
# postgres          Up 2 seconds (healthy)
# prometheus        Up 2 seconds
# grafana           Up 2 seconds
```

### Step 5: Verify Crawl Results

```bash
# Check crawler logs
docker-compose logs -f crawler

# List results
docker exec web-crawler python crawler_cli.py stats

# View sample results
docker exec web-crawler python crawler_cli.py list --limit 10

# Export results
docker exec web-crawler python crawler_cli.py export-json results.json
```

---

## Docker Security Features (DHI)

This setup uses Docker Hardened Images which includes:

✅ **Non-root user**: Crawler runs as `crawler` user (UID 1000)
✅ **No new privileges**: `no-new-privileges:true` prevents privilege escalation
✅ **Minimal base image**: Only essential packages included
✅ **Read-only filesystem**: Root filesystem is immutable
✅ **Dropped capabilities**: All Linux capabilities dropped by default
✅ **Security scanning**: Image scanned for CVEs automatically
✅ **Network isolation**: Runs on isolated bridge network

### Verify Security

```bash
# Check running container user
docker exec web-crawler id
# Should output: uid=1000(crawler) gid=1000(crawler)

# Check read-only filesystem
docker exec web-crawler touch /test
# Should fail: "Read-only file system"

# Scan for vulnerabilities
docker scout cves web-crawler

# Check security options
docker inspect web-crawler | grep -A 20 "SecurityOpt"
```

---

## Production Deployment

### Option 1: Kubernetes

```bash
# Create namespace
kubectl create namespace web-crawler

# Deploy
kubectl apply -f k8s/deployment.yaml

# Verify
kubectl get pods -n web-crawler
kubectl logs -f deployment/web-crawler -n web-crawler

# Access via port-forward
kubectl port-forward -n web-crawler svc/web-crawler 8080:8080

# Scale horizontally
kubectl scale deployment web-crawler --replicas=3
```

### Option 2: Docker Swarm

```bash
# Initialize swarm
docker swarm init

# Deploy stack
docker stack deploy -c docker-compose.yml crawler

# View services
docker service ls

# Check logs
docker service logs crawler_crawler

# Scale service
docker service scale crawler_crawler=3
```

### Option 3: Self-hosted VM

```bash
# SSH to server
ssh user@server.com

# Clone repository
git clone https://github.com/yourrepo/web-crawler.git
cd web-crawler

# Configure
cp .env.example .env
nano .env
nano config.json

# Start with systemd (create service file)
sudo cp docker-compose.yml /etc/docker/compose/
sudo systemctl start docker-compose@web-crawler

# View logs
sudo journalctl -u docker-compose@web-crawler -f
```

---

## Monitoring & Troubleshooting

### Access Monitoring Dashboards

| Service | URL | Default Creds |
|---------|-----|-----------------|
| Prometheus | http://localhost:9090 | - |
| Grafana | http://localhost:3000 | admin/admin |
| Crawler API | http://localhost:8080/stats | - |

### Common Issues

#### 1. Container won't start

```bash
# Check logs
docker-compose logs crawler

# Common causes:
# - Port already in use: Change port in docker-compose.yml
# - Config JSON syntax error: docker exec crawler python -m json.tool config.json
# - Permission denied: Check .env DATABASE password
```

#### 2. High memory usage

```bash
# Reduce workers
docker-compose exec crawler python crawler_cli.py stats

# Edit config.json
"num_workers": 2  # Reduce from default

# Restart
docker-compose restart crawler
```

#### 3. Slow crawling speed

```bash
# Check rate limiter
docker logs crawler | grep "RateLimiter"

# Increase requests per second (be respectful!)
"requests_per_second": 2.0

# Add more workers
"num_workers": 8
```

### Export Data

```bash
# JSON format
docker exec crawler python crawler_cli.py export-json backup.json

# CSV format
docker exec crawler python crawler_cli.py export-csv backup.csv

# Database dump (PostgreSQL)
docker exec postgres pg_dump -U crawler_user crawler > backup.sql
```

---

## Performance Tuning

### For Small Crawls (<1000 URLs)

```json
{
  "crawler": {
    "num_workers": 2,
    "requests_per_second": 0.5,
    "max_depth": 2
  }
}
```

### For Large Crawls (>10000 URLs)

```json
{
  "crawler": {
    "num_workers": 8,
    "requests_per_second": 2.0,
    "max_depth": 3,
    "timeout": 60
  }
}
```

### Resource Limits

```yaml
# docker-compose.yml - Add to crawler service
deploy:
  resources:
    limits:
      cpus: '2'
      memory: 2G
    reservations:
      cpus: '1'
      memory: 1G
```

---

## Maintenance Tasks

### Weekly

```bash
# Check disk usage
docker system df

# Review logs for errors
docker-compose logs crawler | grep ERROR

# Backup database
docker exec postgres pg_dump -U crawler_user crawler > weekly_backup.sql
```

### Monthly

```bash
# Clean old results
docker exec crawler python crawler_cli.py clear 30

# Update images
docker-compose pull
docker-compose build

# Check security vulnerabilities
docker scout cves web-crawler
```

### Quarterly

```bash
# Full backup
docker-compose exec postgres pg_dump crawler > quarterly_backup.sql

# Update dependencies
pip list --outdated
# Update in requirements.txt, rebuild image

# Security audit
docker security scan
```

---

## Advanced Configuration

### Using PostgreSQL Instead of SQLite

```python
# In crawler_async.py, modify CrawlDatabase class:
class CrawlDatabase:
    def __init__(self, db_type="postgresql"):
        # Add PostgreSQL connection logic
```

### Custom Rate Limiting Per Domain

```python
# Create domain-specific rules
rate_limits = {
    "example.com": 0.5,      # Very slow
    "api.example.com": 2.0,  # Faster
    "default": 1.0
}
```

### Proxy Support

```python
# Add to AsyncCrawler.fetch_url():
connector = aiohttp.TCPConnector(
    proxy="http://proxy.example.com:8080",
    ssl=False
)
```

---

## Support & Troubleshooting

For detailed troubleshooting, see `DOCUMENTATION.md`

### Quick Commands

```bash
# View status
docker-compose ps

# View logs (all services)
docker-compose logs

# View logs (crawler only)
docker-compose logs -f crawler

# Enter container shell
docker-compose exec crawler bash

# Restart service
docker-compose restart crawler

# Stop all services
docker-compose down

# Remove all data
docker-compose down -v
```

### Getting Help

1. Check logs: `docker-compose logs crawler`
2. Check config: `docker exec crawler cat config.json`
3. Check database: `docker exec crawler python crawler_cli.py stats`
4. Read DOCUMENTATION.md for detailed info

---

## Next Steps

- [ ] Edit `.env` with your settings
- [ ] Edit `config.json` with your target URLs
- [ ] Run `docker-compose up`
- [ ] Monitor at `http://localhost:9090` (Prometheus)
- [ ] Export results with `crawler_cli.py`
- [ ] Scale to production (Kubernetes/Swarm)

Happy crawling! 🕷️🔍
