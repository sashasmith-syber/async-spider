#!/bin/bash
# File checklist only. A passing run does not mean the crawler is production-ready.
# See README.md for what the code actually does.

set -e

echo "========================================="
echo "Web Crawler Pre-Deployment Checklist"
echo "========================================="
echo ""

# Color codes
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

check_file() {
    if [ -f "$1" ]; then
        echo -e "${GREEN}✓${NC} $1"
        return 0
    else
        echo -e "${RED}✗${NC} $1 (MISSING)"
        return 1
    fi
}

check_dir() {
    if [ -d "$1" ]; then
        echo -e "${GREEN}✓${NC} $1/"
        return 0
    else
        echo -e "${RED}✗${NC} $1/ (MISSING)"
        return 1
    fi
}

check_command() {
    if command -v "$1" &> /dev/null; then
        echo -e "${GREEN}✓${NC} $1 installed"
        return 0
    else
        echo -e "${RED}✗${NC} $1 not found"
        return 1
    fi
}

echo "1. System Requirements"
echo "====================="
check_command docker
check_command docker-compose
check_command python3

echo ""
echo "2. Application Files"
echo "===================="
check_file "crawler_async.py"
check_file "metrics_exporter.py"
check_file "crawler_cli.py"
check_file "example_usage.py"

echo ""
echo "3. Docker Configuration"
echo "======================"
check_file "Dockerfile"
check_file "docker-compose.yml"
check_file ".dockerignore"
check_file "requirements.txt"

echo ""
echo "4. Configuration Files"
echo "====================="
check_file "config.json"
if [ -f ".env" ]; then
    echo -e "${GREEN}✓${NC} .env configured"
else
    echo -e "${YELLOW}⚠${NC} .env not found (copy from .env.example)"
fi

echo ""
echo "5. Database & Monitoring"
echo "======================="
check_dir "sql"
check_file "sql/init.sql"
check_dir "monitoring"
check_file "monitoring/prometheus.yml"

echo ""
echo "6. Kubernetes Configuration"
echo "=========================="
check_dir "k8s"
check_file "k8s/deployment.yaml"

echo ""
echo "7. Documentation"
echo "================"
check_file "README.md"
check_file "DOCUMENTATION.md"
check_file "SETUP_GUIDE.md"
check_file "DELIVERABLES.md"

echo ""
echo "8. Configuration Validation"
echo "=========================="

# Check config.json syntax
if python3 -m json.tool config.json > /dev/null 2>&1; then
    echo -e "${GREEN}✓${NC} config.json valid JSON"
else
    echo -e "${RED}✗${NC} config.json invalid JSON"
fi

# Check if start_urls are set
if grep -q '"start_urls"' config.json; then
    echo -e "${GREEN}✓${NC} start_urls configured"
else
    echo -e "${YELLOW}⚠${NC} start_urls not configured"
fi

echo ""
echo "9. Environment Validation"
echo "========================"

if [ -f ".env" ]; then
    if grep -q "DB_PASSWORD" .env; then
        DB_PASS=$(grep "DB_PASSWORD" .env | cut -d'=' -f2)
        if [ "$DB_PASS" != "changeme" ] && [ "$DB_PASS" != "your_secure_password_here_min_16_chars" ]; then
            echo -e "${GREEN}✓${NC} DB_PASSWORD set to custom value"
        else
            echo -e "${YELLOW}⚠${NC} DB_PASSWORD is default (change for production)"
        fi
    fi
else
    echo -e "${YELLOW}⚠${NC} .env file not found"
fi

echo ""
echo "10. Docker Image Check"
echo "====================="

if docker images | grep -q "web-crawler"; then
    echo -e "${GREEN}✓${NC} web-crawler image found"
else
    echo -e "${YELLOW}⚠${NC} web-crawler image not built yet (run: docker-compose build)"
fi

echo ""
echo "11. Port Availability"
echo "===================="

check_port() {
    if lsof -Pi :$1 -sTCP:LISTEN -t >/dev/null 2>&1; then
        echo -e "${YELLOW}⚠${NC} Port $1 already in use"
    else
        echo -e "${GREEN}✓${NC} Port $1 available"
    fi
}

check_port 8080  # Crawler
check_port 5432  # PostgreSQL
check_port 9090  # Prometheus
check_port 3000  # Grafana

echo ""
echo "12. Disk Space"
echo "=============="

AVAILABLE=$(df . | tail -1 | awk '{print $4}')
REQUIRED=2097152  # 2GB in KB

if [ $AVAILABLE -gt $REQUIRED ]; then
    echo -e "${GREEN}✓${NC} Sufficient disk space ($(numfmt --to=iec-i --suffix=B $((AVAILABLE * 1024))) available)"
else
    echo -e "${RED}✗${NC} Insufficient disk space (only $(numfmt --to=iec-i --suffix=B $((AVAILABLE * 1024))) available, need 2GB)"
fi

echo ""
echo "========================================="
echo "Pre-Deployment Checklist Complete"
echo "========================================="
echo ""
echo "Ready to deploy? Run:"
echo "  docker-compose up -d"
echo ""
echo "To verify:"
echo "  docker-compose ps"
echo "  docker-compose logs -f crawler"
echo ""
