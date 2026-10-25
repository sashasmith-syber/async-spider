"""Deterministic checks. These tests do not contact third-party websites."""

import json
import os
import sqlite3
import tempfile
import unittest
from urllib.robotparser import RobotFileParser
from unittest.mock import patch

from aiohttp import web
from aiohttp.test_utils import make_mocked_request

import example_usage
from crawler_async import (
    AsyncCrawler,
    CrawlDatabase,
    RobotsParser,
    URLFilter,
    address_is_public,
    destination_block_reason,
    host_allowed,
    load_config,
)
from crawler_cli import CrawlerCLI
from metrics_exporter import health_handler, metrics_handler


class PolicyTests(unittest.TestCase):
    def test_domain_boundary(self):
        allowed = ["example.com"]
        self.assertTrue(host_allowed("example.com", allowed))
        self.assertTrue(host_allowed("www.example.com", allowed))
        self.assertFalse(host_allowed("notexample.com", allowed))
        self.assertFalse(host_allowed("example.com.evil.test", allowed))
        self.assertFalse(host_allowed("evil.test", ["*"]))

    def test_public_address_classification(self):
        self.assertTrue(address_is_public("1.1.1.1"))
        self.assertTrue(address_is_public("2001:4860:4860::8888"))
        for blocked in (
            "127.0.0.1",
            "10.0.0.1",
            "172.16.0.1",
            "192.168.1.1",
            "169.254.169.254",
            "100.64.0.1",
            "0.0.0.0",
            "224.0.0.1",
            "::1",
            "fd00::1",
        ):
            self.assertFalse(address_is_public(blocked), blocked)

    def test_destination_policy_does_not_resolve_literals_or_userinfo(self):
        self.assertIsNotNone(destination_block_reason("http://127.0.0.1/"))
        self.assertIsNotNone(destination_block_reason("http://169.254.169.254/latest/meta-data"))
        self.assertIsNotNone(destination_block_reason("file:///etc/passwd"))
        self.assertIsNotNone(destination_block_reason("https://user:example@example.com/"))
        self.assertIsNone(destination_block_reason("http://127.0.0.1/", allow_private=True))

    def test_resolver_blocks_private_answers(self):
        def private(_host, _port):
            return ["10.1.2.3"]

        def public(_host, _port):
            return ["1.1.1.1"]

        self.assertIsNotNone(destination_block_reason("https://ok.example/", resolver=private))
        self.assertIsNone(destination_block_reason("https://ok.example/", resolver=public))

    def test_shipped_config_enables_tls_and_blocks_private_networks(self):
        config = load_config("config.json")
        self.assertTrue(config["security"]["verify_ssl"])
        self.assertFalse(config["security"]["allow_private_networks"])
        self.assertTrue(config["crawler"]["start_urls"])


class LocalCrawlTests(unittest.IsolatedAsyncioTestCase):
    async def test_private_target_is_not_fetched(self):
        with tempfile.TemporaryDirectory() as tmp:
            crawler = AsyncCrawler(
                start_urls=["http://127.0.0.1/"],
                allowed_domains=["127.0.0.1"],
                num_workers=1,
                requests_per_second=100,
                db_path=os.path.join(tmp, "crawl.db"),
                allow_private_networks=False,
            )
            stats = await crawler.run(crawl_timeout=5)
        self.assertEqual(stats["crawled"], 0)
        self.assertGreaterEqual(stats["skipped"], 1)

    async def test_localhost_fixture_and_redirect_stop(self):
        async def page(_request):
            html = "<html><head><title>Fixture</title></head><body><a href='/next'>n</a></body></html>"
            return web.Response(text=html, content_type="text/html")

        async def robots(_request):
            return web.Response(text="User-agent: *\nAllow: /\n", content_type="text/plain")

        async def redir(_request):
            raise web.HTTPFound("http://169.254.169.254/")

        async def big(_request):
            return web.Response(body=b"x" * 100)

        app = web.Application()
        app.router.add_get("/", page)
        app.router.add_get("/robots.txt", robots)
        app.router.add_get("/redir", redir)
        app.router.add_get("/big", big)
        runner = web.AppRunner(app)
        await runner.setup()
        site = web.TCPSite(runner, "127.0.0.1", 0)
        await site.start()
        port = site._server.sockets[0].getsockname()[1]
        base = f"http://127.0.0.1:{port}"

        try:
            with tempfile.TemporaryDirectory() as tmp:
                crawler = AsyncCrawler(
                    start_urls=[base + "/"],
                    allowed_domains=["127.0.0.1"],
                    num_workers=1,
                    requests_per_second=100,
                    max_depth=0,
                    timeout=5,
                    db_path=os.path.join(tmp, "crawl.db"),
                    allow_private_networks=True,
                    verify_ssl=True,
                )
                stats = await crawler.run(crawl_timeout=10)
                rows = crawler.db.get_results()

                redirector = AsyncCrawler(
                    start_urls=[base + "/redir"],
                    allowed_domains=["127.0.0.1"],
                    num_workers=1,
                    requests_per_second=100,
                    max_depth=1,
                    timeout=5,
                    db_path=os.path.join(tmp, "redir.db"),
                    allow_private_networks=True,
                )
                await redirector.run(crawl_timeout=10)
                redirected = redirector.db.get_results()

                limited = AsyncCrawler(
                    start_urls=[base + "/big"],
                    allowed_domains=["127.0.0.1"],
                    num_workers=1,
                    requests_per_second=100,
                    max_depth=1,
                    timeout=5,
                    db_path=os.path.join(tmp, "big.db"),
                    allow_private_networks=True,
                    max_response_bytes=16,
                )
                await limited.run(crawl_timeout=10)
                oversized = limited.db.get_results()
        finally:
            await runner.cleanup()

        self.assertEqual(stats["crawled"], 1)
        self.assertEqual(rows[0]["title"], "Fixture")
        self.assertEqual(redirected[0]["status_code"], 302)
        self.assertIn("redirect", redirected[0]["error"])
        self.assertEqual(oversized[0]["error"], "response too large")


class FilterAndRobotsTests(unittest.IsolatedAsyncioTestCase):
    async def test_url_filter_dedupes_and_enforces_depth(self):
        public = lambda _h, _p: ["1.1.1.1"]
        url_filter = URLFilter(["example.com"], max_depth=2, resolver=public)
        self.assertTrue(await url_filter.should_crawl("https://example.com/a/b"))
        self.assertFalse(await url_filter.should_crawl("https://example.com/a/b"))
        self.assertFalse(await url_filter.should_crawl("https://example.com/a/b/c"))
        self.assertFalse(await url_filter.should_crawl("https://other.test/"))

    async def test_robots_disallow_and_fetch_failure_refuse(self):
        robots = RobotsParser()
        parser = RobotFileParser()
        parser.parse(["User-agent: *", "Disallow: /private"])
        with patch("crawler_async._read_robots", return_value=parser) as read:
            self.assertTrue(await robots.can_fetch("https://example.com/ok"))
            self.assertFalse(await robots.can_fetch("https://example.com/private/x"))
            self.assertEqual(read.call_count, 1)

        failing = RobotsParser()
        with patch("crawler_async._read_robots", side_effect=OSError("boom")):
            self.assertFalse(await failing.can_fetch("https://down.example/"))


class CliAndMetricsTests(unittest.IsolatedAsyncioTestCase):
    def test_cli_reads_sqlite_rows(self):
        with tempfile.TemporaryDirectory() as tmp:
            db_path = os.path.join(tmp, "crawl.db")
            database = CrawlDatabase(db_path)
            conn = sqlite3.connect(db_path)
            conn.execute(
                "INSERT INTO crawl_results (url, status_code, title, links_count, error, crawled_at, response_time) VALUES (?, ?, ?, ?, ?, ?, ?)",
                ("https://example.com/", 200, "Example", 1, None, "2026-01-01T00:00:00+00:00", 0.1),
            )
            conn.commit()
            conn.close()
            stats = CrawlerCLI(db_path).get_stats()
            self.assertEqual(stats["total_crawled"], 1)
            self.assertEqual(stats["successful"], 1)
            self.assertIsNotNone(database.db_path)

    def test_cli_domain_summary_groups_by_host(self):
        with tempfile.TemporaryDirectory() as tmp:
            db_path = os.path.join(tmp, "crawl.db")
            CrawlDatabase(db_path)
            conn = sqlite3.connect(db_path)
            conn.executemany(
                "INSERT INTO crawl_results (url, status_code, title, links_count, error, crawled_at, response_time) VALUES (?, ?, ?, ?, ?, ?, ?)",
                [
                    ("http://127.0.0.1:8765/", 200, "Home", 2, None, "2026-01-01T00:00:00+00:00", 0.1),
                    ("http://127.0.0.1:8765/missing", 404, None, 0, "HTTP 404", "2026-01-01T00:00:01+00:00", 0.3),
                    ("https://Example.com", 200, "Example", 0, None, "2026-01-01T00:00:02+00:00", None),
                ],
            )
            conn.commit()
            conn.close()
            with patch("builtins.print"):
                summary = CrawlerCLI(db_path).domain_summary()
            self.assertEqual(
                [(row["domain"], row["count"], row["success"]) for row in summary],
                [("127.0.0.1:8765", 2, 1), ("example.com", 1, 1)],
            )
            self.assertAlmostEqual(summary[0]["avg_time"], 0.2)
            self.assertEqual(summary[1]["avg_time"], 0.0)

    def test_cli_domain_summary_reports_missing_table(self):
        with tempfile.TemporaryDirectory() as tmp:
            with patch("builtins.print"):
                self.assertIsNone(CrawlerCLI(os.path.join(tmp, "empty.db")).domain_summary())

    async def test_health_and_metrics_from_sqlite(self):
        with tempfile.TemporaryDirectory() as tmp:
            missing = os.path.join(tmp, "missing.db")
            with patch.dict(os.environ, {"CRAWL_DB": missing}):
                health = await health_handler(make_mocked_request("GET", "/health"))
            payload = json.loads(health.body)
            self.assertEqual(health.status, 200)
            self.assertFalse(payload["db_ok"])

            db_path = os.path.join(tmp, "crawl.db")
            CrawlDatabase(db_path)
            conn = sqlite3.connect(db_path)
            conn.execute(
                "INSERT INTO crawl_results (url, status_code, title, links_count, error, crawled_at, response_time) VALUES (?, ?, ?, ?, ?, ?, ?)",
                ("https://example.com/", 200, "Example", 2, None, "2026-01-01T00:00:00+00:00", 0.2),
            )
            conn.commit()
            conn.close()
            with patch.dict(os.environ, {"CRAWL_DB": db_path}):
                metrics = await metrics_handler(make_mocked_request("GET", "/metrics"))
            text = metrics.body.decode()
            self.assertIn("crawler_urls_stored", text)
            self.assertIn("crawler_queue_size", text)

    async def test_examples_do_not_crawl_unless_enabled(self):
        with patch.dict(os.environ, {"ASYNC_SPIDER_LIVE_EXAMPLES": "0"}):
            await example_usage.main()


if __name__ == "__main__":
    unittest.main()
