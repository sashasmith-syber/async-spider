#!/usr/bin/env python3
"""Async crawler with per-host rate limits, robots.txt checks, and SQLite storage.

Completed page results are stored in SQLite. URLs still waiting in the memory
queue are discarded on timeout or shutdown.
"""

import asyncio
import hashlib
import ipaddress
import json
import logging
import os
import socket
import sqlite3
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Callable, Iterable, List, Optional, Sequence
from urllib.parse import urljoin, urlparse
from urllib.robotparser import RobotFileParser

import aiohttp
from bs4 import BeautifulSoup

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

MAX_RESPONSE_BYTES = 2_000_000
MAX_LINKS_PER_PAGE = 200
MAX_QUEUE_SIZE = 10_000
MAX_ROBOTS_BYTES = 100_000
DEFAULT_CRAWL_TIMEOUT = 300

Resolver = Callable[[str, int], Sequence[str]]

_BLOCKED_HOSTS = {
    "localhost",
    "localhost.localdomain",
    "metadata.google.internal",
    "metadata.google.com",
}
_BLOCKED_SUFFIXES = (".localhost", ".local", ".internal", ".localdomain")
_BLOCK_NETWORKS = [
    ipaddress.ip_network("0.0.0.0/8"),
    ipaddress.ip_network("10.0.0.0/8"),
    ipaddress.ip_network("100.64.0.0/10"),
    ipaddress.ip_network("127.0.0.0/8"),
    ipaddress.ip_network("169.254.0.0/16"),
    ipaddress.ip_network("172.16.0.0/12"),
    ipaddress.ip_network("192.0.0.0/24"),
    ipaddress.ip_network("192.0.2.0/24"),
    ipaddress.ip_network("192.168.0.0/16"),
    ipaddress.ip_network("198.18.0.0/15"),
    ipaddress.ip_network("198.51.100.0/24"),
    ipaddress.ip_network("203.0.113.0/24"),
    ipaddress.ip_network("224.0.0.0/4"),
    ipaddress.ip_network("240.0.0.0/4"),
    ipaddress.ip_network("255.255.255.255/32"),
    ipaddress.ip_network("::/128"),
    ipaddress.ip_network("::1/128"),
    ipaddress.ip_network("fc00::/7"),
    ipaddress.ip_network("fe80::/10"),
    ipaddress.ip_network("ff00::/8"),
    ipaddress.ip_network("2001:db8::/32"),
]


def load_config(path: str = "config.json") -> dict:
    """Load crawler configuration. Raises ValueError if the JSON shape is wrong."""
    with open(path, encoding="utf-8") as handle:
        data = json.load(handle)
    if not isinstance(data, dict):
        raise ValueError("config root must be a JSON object")
    return data


def _normalize_ip(ip_text: str) -> ipaddress._BaseAddress:
    text = ip_text.split("%", 1)[0]
    addr = ipaddress.ip_address(text)
    if isinstance(addr, ipaddress.IPv6Address) and addr.ipv4_mapped is not None:
        return addr.ipv4_mapped
    return addr


def address_is_public(ip_text: str) -> bool:
    """Return True only for a globally routable unicast address."""
    try:
        addr = _normalize_ip(ip_text)
    except ValueError:
        return False
    if (
        addr.is_multicast
        or addr.is_reserved
        or addr.is_loopback
        or addr.is_link_local
        or addr.is_unspecified
        or addr.is_private
        or not addr.is_global
    ):
        return False
    for network in _BLOCK_NETWORKS:
        if addr.version == network.version and addr in network:
            return False
    return True


def default_resolver(host: str, port: int) -> List[str]:
    infos = socket.getaddrinfo(host, port, type=socket.SOCK_STREAM)
    return sorted({item[4][0] for item in infos})


def destination_block_reason(
    url: str,
    allow_private: bool = False,
    resolver: Optional[Resolver] = None,
) -> Optional[str]:
    """Return a reason to refuse the URL, or None when the destination is allowed.

    Private, loopback, link-local, and metadata destinations are refused unless
    allow_private is set. Name resolution is checked once immediately before use;
    a later DNS change is not re-checked by the socket layer.
    """
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https"):
        return "unsupported URL scheme"
    if parsed.username is not None or parsed.password is not None:
        return "URL userinfo is not allowed"
    host = parsed.hostname
    if not host:
        return "missing host"
    host_l = host.lower().rstrip(".")
    if host_l in _BLOCKED_HOSTS or host_l.endswith(_BLOCKED_SUFFIXES):
        return "blocked hostname"

    try:
        literal = _normalize_ip(host_l)
    except ValueError:
        literal = None

    if literal is not None:
        if not allow_private and not address_is_public(str(literal)):
            return "non-public address"
        return None

    try:
        host_ascii = host_l.encode("idna").decode("ascii")
    except UnicodeError:
        return "invalid hostname"
    if any(label == "" for label in host_ascii.split(".")):
        return "invalid hostname"

    if allow_private:
        return None

    port = parsed.port or (443 if parsed.scheme == "https" else 80)
    resolve = resolver or default_resolver
    try:
        ips = list(resolve(host_ascii, port))
    except OSError:
        return "name resolution failed"
    if not ips:
        return "name resolution failed"
    for ip in ips:
        if not address_is_public(ip):
            return "hostname resolves to a non-public address"
    return None


def host_allowed(host: str, allowed_domains: Iterable[str]) -> bool:
    """Allow an exact host or a real subdomain. A bare suffix is not enough."""
    host_l = (host or "").lower().rstrip(".")
    if not host_l:
        return False
    for domain in allowed_domains:
        allowed = (domain or "").lower().strip().rstrip(".")
        if not allowed or allowed == "*":
            continue
        if host_l == allowed or host_l.endswith("." + allowed):
            return True
    return False


class _GuardedRedirectHandler(urllib.request.HTTPRedirectHandler):
    def __init__(self, allow_private: bool):
        super().__init__()
        self.allow_private = allow_private

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        reason = destination_block_reason(newurl, allow_private=self.allow_private)
        if reason:
            raise urllib.error.URLError(f"robots redirect blocked: {reason}")
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def _read_robots(url: str, timeout: float, allow_private: bool) -> RobotFileParser:
    parser = RobotFileParser()
    parser.set_url(url)
    opener = urllib.request.build_opener(_GuardedRedirectHandler(allow_private))
    try:
        with opener.open(url, timeout=timeout) as response:
            raw = response.read(MAX_ROBOTS_BYTES + 1)
    except urllib.error.HTTPError as err:
        if err.code in (401, 403):
            parser.disallow_all = True
            return parser
        if 400 <= err.code < 500:
            parser.allow_all = True
            return parser
        raise
    if len(raw) > MAX_ROBOTS_BYTES:
        raise ValueError("robots.txt exceeds size limit")
    parser.parse(raw.decode("utf-8", "surrogateescape").splitlines())
    return parser


@dataclass
class CrawlResult:
    """Result from a single crawled page."""

    url: str
    status_code: int
    title: Optional[str]
    links: List[str]
    error: Optional[str]
    crawled_at: str
    response_time: float


class RateLimiter:
    """Per-domain delay. The lock is not held while sleeping."""

    def __init__(self, requests_per_second: float = 1.0):
        if requests_per_second <= 0:
            raise ValueError("requests_per_second must be greater than 0")
        self.requests_per_second = requests_per_second
        self.next_allowed = {}
        self.lock = asyncio.Lock()

    async def wait(self, domain: str) -> None:
        delay = 0.0
        spacing = 1.0 / self.requests_per_second
        async with self.lock:
            now = time.monotonic()
            earliest = self.next_allowed.get(domain, now)
            if earliest > now:
                delay = earliest - now
            self.next_allowed[domain] = max(earliest, now) + spacing
        if delay:
            await asyncio.sleep(delay)


class URLFilter:
    """Domain allow-list, depth limit, destination policy, and deduplication."""

    def __init__(
        self,
        allowed_domains: List[str],
        max_depth: int = 3,
        allow_private_networks: bool = False,
        resolver: Optional[Resolver] = None,
    ):
        self.allowed_domains = allowed_domains
        self.max_depth = max_depth
        self.allow_private_networks = allow_private_networks
        self.resolver = resolver
        self.seen = set()
        self.lock = asyncio.Lock()

    def _get_depth(self, url: str) -> int:
        parsed = urlparse(url)
        return len([part for part in parsed.path.split("/") if part])

    async def should_crawl(self, url: str) -> bool:
        parsed = urlparse(url)
        host = parsed.hostname or ""
        if not host_allowed(host, self.allowed_domains):
            return False
        if self._get_depth(url) > self.max_depth:
            return False
        reason = await asyncio.to_thread(
            destination_block_reason,
            url,
            self.allow_private_networks,
            self.resolver,
        )
        if reason:
            logger.info("Skipping %s (%s)", url, reason)
            return False

        async with self.lock:
            url_hash = hashlib.sha256(url.encode()).hexdigest()
            if url_hash in self.seen:
                return False
            self.seen.add(url_hash)
        return True


class RobotsParser:
    """Fetch and cache robots.txt. A failed fetch refuses the URL."""

    def __init__(self, timeout: float = 10, allow_private_networks: bool = False):
        self.cache = {}
        self.timeout = timeout
        self.allow_private_networks = allow_private_networks

    async def can_fetch(self, url: str, user_agent: str = "AsyncCrawler/1.0") -> bool:
        parsed = urlparse(url)
        cache_key = parsed.netloc.lower()
        if cache_key not in self.cache:
            robots_url = f"{parsed.scheme}://{parsed.netloc}/robots.txt"
            try:
                parser = await asyncio.to_thread(
                    _read_robots,
                    robots_url,
                    self.timeout,
                    self.allow_private_networks,
                )
                self.cache[cache_key] = parser
            except Exception as exc:
                logger.warning("Refusing %s because robots.txt could not be read: %s", parsed.netloc, exc)
                return False
        return self.cache[cache_key].can_fetch(user_agent, url)


class CrawlDatabase:
    """SQLite database for storing crawl results."""

    def __init__(self, db_path: str = "data/crawl_results.db"):
        self.db_path = db_path
        self._init_db()

    def _init_db(self):
        parent = os.path.dirname(self.db_path)
        if parent:
            os.makedirs(parent, exist_ok=True)
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS crawl_results (
                id INTEGER PRIMARY KEY,
                url TEXT UNIQUE NOT NULL,
                status_code INTEGER,
                title TEXT,
                links_count INTEGER,
                error TEXT,
                crawled_at TEXT,
                response_time REAL
            )
        """)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS crawled_links (
                id INTEGER PRIMARY KEY,
                parent_url TEXT NOT NULL,
                child_url TEXT NOT NULL,
                UNIQUE(parent_url, child_url)
            )
        """)
        conn.commit()
        conn.close()

    def save_result(self, result: CrawlResult):
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        try:
            cursor.execute("""
                INSERT OR REPLACE INTO crawl_results
                (url, status_code, title, links_count, error, crawled_at, response_time)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (
                result.url,
                result.status_code,
                result.title,
                len(result.links),
                result.error,
                result.crawled_at,
                result.response_time,
            ))
            conn.commit()
        except Exception as exc:
            logger.error("Failed to save result for %s: %s", result.url, exc)
        finally:
            conn.close()

    def get_results(self, limit: int = 100) -> List[dict]:
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM crawl_results LIMIT ?", (limit,))
        columns = [desc[0] for desc in cursor.description]
        results = [dict(zip(columns, row)) for row in cursor.fetchall()]
        conn.close()
        return results


class AsyncCrawler:
    """Main async crawler engine."""

    def __init__(
        self,
        start_urls: List[str],
        allowed_domains: List[str],
        num_workers: int = 4,
        requests_per_second: float = 1.0,
        max_depth: int = 3,
        timeout: int = 30,
        db_path: str = "data/crawl_results.db",
        verify_ssl: bool = True,
        user_agent: str = "AsyncCrawler/1.0 (+https://example.com/bot)",
        allow_private_networks: bool = False,
        max_response_bytes: int = MAX_RESPONSE_BYTES,
        resolver: Optional[Resolver] = None,
    ):
        if num_workers < 1:
            raise ValueError("num_workers must be at least 1")
        if timeout < 1:
            raise ValueError("timeout must be at least 1 second")
        self.start_urls = start_urls
        self.allowed_domains = allowed_domains
        self.num_workers = num_workers
        self.timeout = timeout
        self.verify_ssl = verify_ssl
        self.user_agent = user_agent
        self.allow_private_networks = allow_private_networks
        self.max_response_bytes = max_response_bytes
        self.max_crawls: Optional[int] = None
        self.queue: asyncio.Queue = asyncio.Queue(maxsize=MAX_QUEUE_SIZE)
        self.rate_limiter = RateLimiter(requests_per_second)
        self.url_filter = URLFilter(
            allowed_domains,
            max_depth,
            allow_private_networks=allow_private_networks,
            resolver=resolver,
        )
        self.robots_parser = RobotsParser(
            timeout=min(timeout, 10),
            allow_private_networks=allow_private_networks,
        )
        self.db = CrawlDatabase(db_path)
        self.stats = {
            "crawled": 0,
            "failed": 0,
            "skipped": 0,
            "total_links": 0,
            "queued_discarded": 0,
            "start_time": None,
            "end_time": None,
        }
        self.session: Optional[aiohttp.ClientSession] = None

    def _now(self) -> str:
        return datetime.now(timezone.utc).isoformat()

    def _result(self, url: str, status_code: int, error: Optional[str], started: float, title=None, links=None):
        return CrawlResult(
            url=url,
            status_code=status_code,
            title=title,
            links=links or [],
            error=error,
            crawled_at=self._now(),
            response_time=time.time() - started,
        )

    def _over_budget(self) -> bool:
        if self.max_crawls is None:
            return False
        return (self.stats["crawled"] + self.stats["failed"]) >= self.max_crawls

    async def _enqueue(self, url: str) -> None:
        try:
            self.queue.put_nowait(url)
        except asyncio.QueueFull:
            self.stats["skipped"] += 1
            logger.warning("Queue is full; skipped %s", url)

    async def fetch_url(self, url: str) -> CrawlResult:
        """Fetch and parse a single URL. Redirects are not followed."""
        start_time = time.time()
        domain = urlparse(url).netloc

        reason = await asyncio.to_thread(
            destination_block_reason,
            url,
            self.allow_private_networks,
            self.url_filter.resolver,
        )
        if reason:
            self.stats["skipped"] += 1
            return self._result(url, 0, reason, start_time)

        try:
            if not await self.robots_parser.can_fetch(url, self.user_agent):
                logger.info("Robots.txt blocks: %s", url)
                self.stats["skipped"] += 1
                return self._result(url, 0, "Blocked by robots.txt", start_time)
        except Exception as exc:
            self.stats["skipped"] += 1
            return self._result(url, 0, f"robots.txt check failed: {exc}", start_time)

        await self.rate_limiter.wait(domain)

        try:
            async with self.session.get(url, allow_redirects=False) as resp:
                if resp.status in (301, 302, 303, 307, 308):
                    self.stats["skipped"] += 1
                    return self._result(url, resp.status, "redirects are not followed", start_time)
                if resp.status != 200:
                    self.stats["failed"] += 1
                    return self._result(url, resp.status, f"HTTP {resp.status}", start_time)
                if resp.content_length is not None and resp.content_length > self.max_response_bytes:
                    self.stats["failed"] += 1
                    return self._result(url, resp.status, "response too large", start_time)
                body = await resp.content.read(self.max_response_bytes + 1)
        except asyncio.TimeoutError:
            self.stats["failed"] += 1
            return self._result(url, 0, "Timeout", start_time)
        except Exception as exc:
            self.stats["failed"] += 1
            return self._result(url, 0, str(exc), start_time)

        if len(body) > self.max_response_bytes:
            self.stats["failed"] += 1
            return self._result(url, 200, "response too large", start_time)

        try:
            html = body.decode("utf-8", "replace")
            soup = BeautifulSoup(html, "html.parser")
            title = None
            if soup.title and soup.title.string:
                title = " ".join(str(soup.title.string).split())[:500]
            links = []
            for anchor in soup.find_all("a", href=True):
                if len(links) >= MAX_LINKS_PER_PAGE:
                    break
                link = urljoin(url, anchor.get("href", ""))
                if link.startswith(("http://", "https://")):
                    links.append(link)
            self.stats["crawled"] += 1
            self.stats["total_links"] += len(links)
        except Exception as exc:
            self.stats["failed"] += 1
            return self._result(url, 200, f"Parse error: {exc}", start_time)

        if not self._over_budget():
            for link in links:
                if await self.url_filter.should_crawl(link):
                    await self._enqueue(link)

        return self._result(url, 200, None, start_time, title=title, links=links)

    async def worker(self, worker_id: int):
        logger.info("Worker %s started", worker_id)
        while True:
            try:
                url = await self.queue.get()
            except asyncio.CancelledError:
                break
            try:
                if self._over_budget():
                    self.stats["skipped"] += 1
                    continue
                logger.info("[W%s] Crawling: %s", worker_id, url)
                result = await self.fetch_url(url)
                self.db.save_result(result)
            finally:
                self.queue.task_done()

    async def run(self, max_crawls: Optional[int] = None, crawl_timeout: float = DEFAULT_CRAWL_TIMEOUT):
        """Run the crawler. Completed rows stay in SQLite; leftover queue entries do not."""
        self.max_crawls = max_crawls
        self.stats["start_time"] = self._now()
        if not self.verify_ssl:
            logger.warning("TLS certificate verification is disabled")
        if self.allow_private_networks:
            logger.warning("Private-network destinations are explicitly allowed")

        timeout = aiohttp.ClientTimeout(
            total=self.timeout,
            connect=min(10, self.timeout),
            sock_read=self.timeout,
        )
        connector = aiohttp.TCPConnector(ssl=None if self.verify_ssl else False)
        self.session = aiohttp.ClientSession(
            timeout=timeout,
            connector=connector,
            headers={"User-Agent": self.user_agent},
        )
        workers = []
        try:
            for url in self.start_urls:
                if await self.url_filter.should_crawl(url):
                    await self._enqueue(url)
                else:
                    self.stats["skipped"] += 1

            workers = [asyncio.create_task(self.worker(i)) for i in range(self.num_workers)]
            try:
                await asyncio.wait_for(self.queue.join(), timeout=crawl_timeout)
            except asyncio.TimeoutError:
                logger.warning("Crawl timeout reached")
        finally:
            for worker in workers:
                worker.cancel()
            if workers:
                await asyncio.gather(*workers, return_exceptions=True)
            discarded = self.queue.qsize()
            self.stats["queued_discarded"] = discarded
            if discarded:
                logger.warning(
                    "Stopped with %s queued URL(s) not crawled. Completed results remain in %s",
                    discarded,
                    self.db.db_path,
                )
            if self.session is not None:
                await self.session.close()
            self.stats["end_time"] = self._now()
        return self.stats


async def main():
    """Crawl the URLs listed in config.json."""
    config_path = os.environ.get("CRAWLER_CONFIG", "config.json")
    config = load_config(config_path)
    crawler_cfg = config.get("crawler") or {}
    security_cfg = config.get("security") or {}
    if not isinstance(crawler_cfg, dict) or not isinstance(security_cfg, dict):
        raise ValueError("crawler and security config sections must be objects")

    crawler = AsyncCrawler(
        start_urls=list(crawler_cfg.get("start_urls") or []),
        allowed_domains=list(crawler_cfg.get("allowed_domains") or []),
        num_workers=int(crawler_cfg.get("num_workers", 4)),
        requests_per_second=float(crawler_cfg.get("requests_per_second", 1.0)),
        max_depth=int(crawler_cfg.get("max_depth", 3)),
        timeout=int(crawler_cfg.get("timeout", 30)),
        db_path=crawler_cfg.get("db_path") or "data/crawl_results.db",
        verify_ssl=bool(security_cfg.get("verify_ssl", True)),
        user_agent=security_cfg.get("user_agent") or "AsyncCrawler/1.0 (+https://example.com/bot)",
        allow_private_networks=bool(security_cfg.get("allow_private_networks", False)),
    )
    level_name = str((config.get("logging") or {}).get("level", "INFO")).upper()
    logging.getLogger().setLevel(getattr(logging, level_name, logging.INFO))

    if not crawler.start_urls:
        logger.error("No start_urls configured in %s", config_path)
        return {}

    logger.info("Starting crawl of %s URL(s) from %s", len(crawler.start_urls), config_path)
    stats = await crawler.run()
    logger.info("Crawl complete: %s", stats)
    return stats


if __name__ == "__main__":
    asyncio.run(main())
