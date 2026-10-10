> Accuracy note: this file is an earlier write-up. Where it disagrees with the code, trust README.md. The image is python:3.11-slim, not a Docker Hardened Image. Performance numbers, production-ready claims, PostgreSQL crawling, Grafana dashboards, retries, and horizontal scaling are not implemented.

# Command Reference - Web Crawler

## Docker Compose Commands

### Start/Stop Services
```bash
# Start all services (background)
docker-compose up -d

# Start with logs visible
docker-compose up

# Stop all services
docker-compose down

# Stop and remove volumes
docker-compose down -v

# Restart services
docker-compose restart

# Restart specific service
docker-compose restart crawler
```

### View Logs
```bash
# All services
docker-compose logs

# Specific service
docker-compose logs crawler

# Follow logs (real-time)
docker-compose logs -f crawler

# Last 100 lines
docker-compose logs --tail=100 crawler

# With timestamps
docker-compose logs --timestamps crawler
```

### Check Status
```bash
# Show running containers
docker-compose ps

# Show all containers (including stopped)
docker-compose ps --all

# Show services
docker-compose config --services
```

### Build & Management
```bash
# Build image
docker-compose build

# Build without cache
docker-compose build --no-cache

# Pull latest images
docker-compose pull

# Remove unused volumes
docker-compose volume rm
```

---

## Crawler CLI Commands

### Statistics & Reporting
```bash
# Show crawl statistics
docker exec crawler python crawler_cli.py stats

# List recent results
docker exec crawler python crawler_cli.py list

# List with custom limit
docker exec crawler python crawler_cli.py list --limit 50

# Show only failed crawls
docker exec crawler python crawler_cli.py list --failed

# Show domain summary
docker exec crawler python crawler_cli.py domains
```

### Export Data
```bash
# Export to JSON
docker exec crawler python crawler_cli.py export-json results.json

# Export to CSV
docker exec crawler python crawler_cli.py export-csv results.csv

# Export with custom database
docker exec crawler python crawler_cli.py --db /path/to/db.sqlite stats
```

### Data Management
```bash
# Clear results older than 30 days
docker exec crawler python crawler_cli.py clear 30

# Clear results older than 90 days
docker exec crawler python crawler_cli.py clear 90

# Reset database (remove all data)
docker exec crawler python crawler_cli.py reset
```

---

## Kubernetes Commands

### Deployment
```bash
# Apply manifests
kubectl apply -f k8s/deployment.yaml

# Apply with namespace
kubectl apply -n web-crawler -f k8s/deployment.yaml

# Check deployment status
kubectl get deployment -n web-crawler

# Check pods
kubectl get pods -n web-crawler

# Check services
kubectl get svc -n web-crawler
```

### Logs & Debugging
```bash
# View logs
kubectl logs deployment/web-crawler -n web-crawler

# Follow logs (real-time)
kubectl logs -f deployment/web-crawler -n web-crawler

# View pod logs
kubectl logs pod/web-crawler-xxxxx -n web-crawler

# Get pod details
kubectl describe pod/web-crawler-xxxxx -n web-crawler

# Get events
kubectl get events -n web-crawler
```

### Port Forwarding
```bash
# Port forward to localhost
kubectl port-forward svc/web-crawler 8080:8080 -n web-crawler

# Port forward specific pod
kubectl port-forward pod/web-crawler-xxxxx 8080:8080 -n web-crawler
```

### Scaling
```bash
# Scale to 3 replicas
kubectl scale deployment web-crawler --replicas=3 -n web-crawler

# Scale to 1
kubectl scale deployment web-crawler --replicas=1 -n web-crawler

# Check HPA status
kubectl get hpa -n web-crawler
```

### Cleanup
```bash
# Delete deployment
kubectl delete deployment web-crawler -n web-crawler

# Delete namespace
kubectl delete namespace web-crawler

# Delete all resources
kubectl delete -f k8s/deployment.yaml
```

---

## Container Inspection Commands

### View Container Info
```bash
# Show running containers
docker ps

# Show all containers
docker ps -a

# Show container details
docker inspect <container_id>

# Show container logs
docker logs <container_id>

# Follow container logs
docker logs -f <container_id>

# Show container stats (real-time)
docker stats web-crawler
```

### Execute Commands in Container
```bash
# Run command
docker exec crawler python crawler_cli.py stats

# Interactive shell
docker exec -it crawler bash

# Check user
docker exec crawler id

# View environment
docker exec crawler env

# Test file system
docker exec crawler touch /test  # Should fail (read-only)
```

### Image Inspection
```bash
# List images
docker images

# Show image history
docker history web-crawler:1.0

# Inspect image
docker inspect web-crawler:1.0

# Check image layers
docker image inspect web-crawler:1.0 --format='{{json .RootFS.Layers}}'
```

---

## File Management Commands

### Copy Data to/from Container
```bash
# Copy from container to host
docker cp crawler:/app/data/crawl_results.db ./

# Copy from host to container
docker cp config.json crawler:/app/

# List container contents
docker exec crawler ls -la /app/data/
```

### Database Commands
```bash
# Backup SQLite database
docker cp crawler:/app/data/crawl_results.db backup_$(date +%s).db

# Backup PostgreSQL database
docker exec postgres pg_dump -U crawler_user crawler > backup.sql

# Restore PostgreSQL database
docker exec -i postgres psql -U crawler_user crawler < backup.sql

# Access SQLite CLI
docker exec -it crawler sqlite3 crawl_results.db
```

---

## Configuration Management

### View Configuration
```bash
# View crawler config
docker exec crawler cat config.json

# View environment variables
docker exec crawler env | grep -E '(LOG_LEVEL|WORKERS)'

# View Prometheus config
docker exec prometheus cat /etc/prometheus/prometheus.yml

# View compose file
cat docker-compose.yml

# Validate compose file
docker-compose config
```

### Update Configuration
```bash
# Edit local config
nano config.json

# Validate JSON
python -m json.tool config.json

# Restart to apply changes
docker-compose restart crawler

# Update environment
nano .env
docker-compose restart
```

---

## Monitoring & Health Checks

### Health Status
```bash
# Check container health
docker inspect --format='{{.State.Health.Status}}' crawler

# Check service readiness
curl http://localhost:8080/health

# Get statistics
curl http://localhost:8080/stats | jq .

# Prometheus UI
open http://localhost:9090

# Grafana UI
open http://localhost:3000
```

### Performance Monitoring
```bash
# CPU & memory usage
docker stats crawler

# Network stats
docker exec crawler cat /proc/net/dev

# Disk usage
docker exec crawler df -h

# Database size
docker exec crawler du -sh crawl_results.db
```

---

## Security Verification

### Security Checks
```bash
# Check user running container
docker exec crawler id

# Verify read-only filesystem
docker exec crawler touch /test  # Should fail

# Check capabilities
docker inspect --format='{{.HostConfig.CapAdd}}' crawler
docker inspect --format='{{.HostConfig.CapDrop}}' crawler

# Check security options
docker inspect --format='{{.HostConfig.SecurityOpt}}' crawler

# Scan image for vulnerabilities
docker scout cves web-crawler:1.0

# Check image layers
docker history web-crawler:1.0
```

---

## Troubleshooting Commands

### Container Issues
```bash
# Check if container is running
docker ps | grep crawler

# Check container status
docker inspect crawler | grep Status

# View error logs
docker logs crawler | tail -50

# Restart container
docker-compose restart crawler

# Rebuild and restart
docker-compose up -d --build
```

### Network Issues
```bash
# Check networks
docker network ls

# Inspect network
docker network inspect crawler-network

# Test DNS resolution
docker exec crawler nslookup postgres

# Test connectivity
docker exec crawler ping postgres
```

### Database Issues
```bash
# Check database connection
docker exec crawler python -c "import sqlite3; sqlite3.connect('crawl_results.db')"

# Check database size
docker exec crawler ls -lh crawl_results.db

# Verify database structure
docker exec crawler sqlite3 crawl_results.db ".schema"

# Check database integrity
docker exec crawler sqlite3 crawl_results.db "PRAGMA integrity_check;"

# Backup before reset
docker exec crawler cp crawl_results.db crawl_results.db.bak
```

### Performance Issues
```bash
# Check memory usage
docker stats crawler

# Check CPU usage
docker stats --no-stream crawler

# Check disk space
docker exec crawler df -h

# View process info
docker exec crawler ps aux

# Check network connections
docker exec crawler netstat -an
```

---

## System Cleanup Commands

### Remove Unused Resources
```bash
# Remove unused images
docker image prune -a

# Remove unused containers
docker container prune

# Remove unused volumes
docker volume prune

# Remove unused networks
docker network prune

# Full cleanup (caution!)
docker system prune -a
```

### Disk Space Management
```bash
# Show disk usage
docker system df

# Show detailed usage
docker system df -v

# Remove build cache
docker builder prune

# Remove dangling images
docker image prune

# Remove all images not used by containers
docker image prune -a --force
```

---

## Quick Workflows

### Development Workflow
```bash
# 1. Make code changes
# 2. Rebuild image
docker-compose build

# 3. Restart service
docker-compose up -d crawler

# 4. Check logs
docker-compose logs -f crawler

# 5. Test changes
docker exec crawler python crawler_cli.py stats
```

### Deployment Workflow
```bash
# 1. Validate configuration
pre_deployment_check.sh

# 2. Build image
docker-compose build

# 3. Start services
docker-compose up -d

# 4. Verify health
docker-compose ps

# 5. Check logs
docker-compose logs crawler

# 6. Export results
docker exec crawler python crawler_cli.py export-json results.json
```

### Backup Workflow
```bash
# 1. Export data
docker exec crawler python crawler_cli.py export-json data_$(date +%s).json

# 2. Backup database
docker cp crawler:/app/data/crawl_results.db backup_$(date +%s).db

# 3. Backup logs
docker logs crawler > logs_$(date +%s).txt

# 4. Store backups
# Move to backup storage/cloud
```

---

## Environment-Specific Commands

### Development
```bash
docker-compose -f docker-compose.yml up -d
docker-compose logs -f
```

### Testing
```bash
docker-compose build --no-cache
docker-compose down -v
docker-compose up -d
```

### Production (Kubernetes)
```bash
kubectl apply -f k8s/deployment.yaml
kubectl logs -f deployment/web-crawler -n web-crawler
```

### Production (Docker Swarm)
```bash
docker stack deploy -c docker-compose.yml crawler
docker service logs crawler_crawler
```

---

## Useful Aliases

Add to ~/.bashrc or ~/.zshrc:

```bash
# Crawler commands
alias crawler-stats='docker exec crawler python crawler_cli.py stats'
alias crawler-list='docker exec crawler python crawler_cli.py list'
alias crawler-logs='docker-compose logs -f crawler'
alias crawler-restart='docker-compose restart crawler'

# Docker Compose
alias dc='docker-compose'
alias dcup='docker-compose up -d'
alias dcdown='docker-compose down'
alias dcps='docker-compose ps'

# Kubernetes
alias kget='kubectl get'
alias klogs='kubectl logs -f'
alias kport='kubectl port-forward'
```

---

## Getting Help

```bash
# Show docker-compose help
docker-compose help

# Show crawler CLI help
docker exec crawler python crawler_cli.py -h

# Show specific command help
docker exec crawler python crawler_cli.py list -h

# kubectl help
kubectl help

# Check logs for errors
docker-compose logs | grep ERROR
```

---

**Save this reference for quick command lookup during operations!**
