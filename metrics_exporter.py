#!/usr/bin/env python3
"""Expose SQLite crawl totals for Prometheus.

These are point-in-time gauges read from the database. They are not live
counters from the crawler process, and queue depth is not available here.
"""

import asyncio
import logging
import os
import signal
import sqlite3
from datetime import datetime, timezone

from aiohttp import web
from prometheus_client import CONTENT_TYPE_LATEST, CollectorRegistry, Gauge, generate_latest

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

registry = CollectorRegistry()
urls_stored = Gauge("crawler_urls_stored", "Pages stored in SQLite", registry=registry)
urls_failed = Gauge("crawler_urls_failed", "Stored pages with a non-200 status", registry=registry)
links_stored = Gauge("crawler_links_stored", "Sum of links_count in SQLite", registry=registry)
response_avg = Gauge(
    "crawler_response_time_seconds_avg",
    "Average stored response time in seconds",
    registry=registry,
)
queue_size = Gauge(
    "crawler_queue_size",
    "Always 0; the exporter cannot see the crawler memory queue",
    registry=registry,
)


def db_path() -> str:
    return os.environ.get("CRAWL_DB", "data/crawl_results.db")


def _sqlite_ro_uri(path: str) -> str:
    absolute = os.path.abspath(path).replace("\\", "/")
    if not absolute.startswith("/"):
        absolute = "/" + absolute
    return "file://" + absolute + "?mode=ro"


def read_stats(path: str) -> dict:
    """Read aggregate totals. Missing or locked databases return an empty snapshot."""
    if not os.path.exists(path):
        return {}
    try:
        conn = sqlite3.connect(_sqlite_ro_uri(path), uri=True, timeout=2)
        cursor = conn.cursor()
        cursor.execute("""
            SELECT
                COUNT(*) as total,
                SUM(CASE WHEN status_code = 200 THEN 1 ELSE 0 END) as success,
                SUM(CASE WHEN status_code != 200 THEN 1 ELSE 0 END) as failed,
                AVG(response_time) as avg_response_time,
                SUM(links_count) as total_links
            FROM crawl_results
        """)
        row = cursor.fetchone()
        conn.close()
    except Exception as exc:
        logger.error("Failed to read %s: %s", path, exc)
        return {}
    return {
        "total_crawled": row[0] or 0,
        "successful": row[1] or 0,
        "failed": row[2] or 0,
        "avg_response_time": row[3] or 0.0,
        "total_links": row[4] or 0,
        "db_ok": True,
    }


def apply_gauges(stats: dict) -> None:
    urls_stored.set(stats.get("total_crawled", 0))
    urls_failed.set(stats.get("failed", 0))
    links_stored.set(stats.get("total_links", 0))
    response_avg.set(stats.get("avg_response_time", 0.0))
    queue_size.set(0)


async def metrics_handler(request: web.Request) -> web.Response:
    apply_gauges(read_stats(db_path()))
    payload = generate_latest(registry)
    return web.Response(body=payload, headers={"Content-Type": CONTENT_TYPE_LATEST})


async def health_handler(request: web.Request) -> web.Response:
    stats = read_stats(db_path())
    return web.json_response({
        "status": "ok",
        "db_ok": bool(stats.get("db_ok")),
        "timestamp": datetime.now(timezone.utc).isoformat(),
    })


async def stats_handler(request: web.Request) -> web.Response:
    stats = read_stats(db_path())
    if not stats:
        stats = {
            "total_crawled": 0,
            "successful": 0,
            "failed": 0,
            "avg_response_time": 0.0,
            "total_links": 0,
            "db_ok": False,
        }
    return web.json_response(stats)


async def start_app():
    app = web.Application()
    app.router.add_get("/metrics", metrics_handler)
    app.router.add_get("/health", health_handler)
    app.router.add_get("/stats", stats_handler)

    runner = web.AppRunner(app)
    await runner.setup()
    host = os.environ.get("METRICS_BIND", "0.0.0.0")
    port = int(os.environ.get("METRICS_PORT", "8080"))
    site = web.TCPSite(runner, host, port)
    await site.start()
    logger.info("Metrics exporter listening on %s:%s", host, port)

    stop = asyncio.Event()
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGTERM, signal.SIGINT):
        try:
            loop.add_signal_handler(sig, stop.set)
        except NotImplementedError:
            pass
    await stop.wait()
    await runner.cleanup()


if __name__ == "__main__":
    asyncio.run(start_app())
