# Docker Official Image. This is not a Docker Hardened Image.
# Official DHI Python images are published separately at dhi.io and are not used here.
FROM python:3.15-slim AS builder

WORKDIR /build

RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir --prefix=/install -r requirements.txt

FROM python:3.15-slim

LABEL org.opencontainers.image.title="async-spider" \
      org.opencontainers.image.description="Single-process async crawler using python:3.11-slim"

RUN groupadd --gid 1000 crawler \
    && useradd --uid 1000 --gid 1000 --create-home --home-dir /home/crawler --shell /usr/sbin/nologin crawler \
    && mkdir -p /app/data \
    && chown -R crawler:crawler /app /home/crawler

WORKDIR /app

COPY --from=builder /install /usr/local
COPY --chown=crawler:crawler crawler_async.py crawler_cli.py metrics_exporter.py config.json /app/

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    HOME=/tmp

USER crawler

HEALTHCHECK --interval=30s --timeout=10s --start-period=10s --retries=3 \
    CMD python -c "import os,sys; sys.exit(0 if os.path.isdir('/app/data') else 1)"

CMD ["python", "crawler_async.py"]
