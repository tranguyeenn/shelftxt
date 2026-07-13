from __future__ import annotations

import asyncio
import ipaddress
import socket
import time
from dataclasses import dataclass
from urllib.parse import urlsplit, urlunsplit

import httpx

from backend.services.book_scraping.domains import is_blocked_domain, is_trusted_domain, normalize_domain
from backend.services.book_scraping.robots import robots_cache


USER_AGENT = "ShelfTXTBookMetadataBot/1.0 (+https://shelftxt.com; metadata lookup)"
MAX_RESPONSE_BYTES = 2 * 1024 * 1024
RATE_LIMIT_SECONDS = 0.5
ALLOWED_CONTENT_TYPES = ("text/html", "application/xhtml+xml")


class ScrapeBlocked(Exception):
    pass


class ScrapeUnavailable(Exception):
    pass


@dataclass
class FetchedPage:
    url: str
    domain: str
    html: str
    status_code: int
    content_type: str | None
    elapsed_ms: float
    robots_allowed: bool
    cache_hit: bool = False


class BookScrapingClient:
    def __init__(self) -> None:
        self._cache: dict[str, FetchedPage] = {}
        self._domain_locks: dict[str, asyncio.Lock] = {}
        self._last_request_at: dict[str, float] = {}

    async def fetch(self, url: str, *, allow_unknown_domain: bool = False) -> FetchedPage:
        safe_url = await self._validate_url(url, allow_unknown_domain=allow_unknown_domain)
        if safe_url in self._cache:
            cached = self._cache[safe_url]
            return FetchedPage(**{**cached.__dict__, "cache_hit": True})

        domain = normalize_domain(safe_url)
        timeout = httpx.Timeout(5.0, connect=2.0, read=5.0, write=5.0, pool=2.0)
        async with httpx.AsyncClient(
            timeout=timeout,
            follow_redirects=True,
            max_redirects=3,
            headers={"User-Agent": USER_AGENT, "Accept": "text/html, application/xhtml+xml"},
        ) as client:
            robots = await robots_cache.allowed(client, safe_url, USER_AGENT)
            if not robots.allowed:
                raise ScrapeBlocked("robots.txt disallows this URL")
            await self._rate_limit(domain)
            page = await self._fetch_with_retry(client, safe_url, domain, robots.allowed)
            self._cache[safe_url] = page
            return page

    async def _fetch_with_retry(
        self,
        client: httpx.AsyncClient,
        url: str,
        domain: str,
        robots_allowed: bool,
    ) -> FetchedPage:
        last_exc: Exception | None = None
        for attempt in range(2):
            started = time.perf_counter()
            try:
                async with client.stream("GET", url) as response:
                    if response.status_code in {500, 502, 503, 504} and attempt == 0:
                        await response.aread()
                        continue
                    if response.status_code in {401, 403, 404, 429}:
                        raise ScrapeUnavailable(f"HTTP {response.status_code}")
                    response.raise_for_status()
                    content_type = response.headers.get("content-type", "").split(";", 1)[0].strip().casefold()
                    if content_type not in ALLOWED_CONTENT_TYPES:
                        raise ScrapeUnavailable("invalid content type")
                    body = bytearray()
                    async for chunk in response.aiter_bytes():
                        body.extend(chunk)
                        if len(body) > MAX_RESPONSE_BYTES:
                            raise ScrapeUnavailable("response too large")
                    elapsed_ms = (time.perf_counter() - started) * 1000
                    return FetchedPage(
                        url=str(response.url),
                        domain=domain,
                        html=bytes(body).decode(response.encoding or "utf-8", errors="replace"),
                        status_code=response.status_code,
                        content_type=content_type,
                        elapsed_ms=round(elapsed_ms, 2),
                        robots_allowed=robots_allowed,
                    )
            except httpx.TooManyRedirects as exc:
                raise ScrapeUnavailable("too many redirects") from exc
            except (httpx.TimeoutException, httpx.HTTPError, ScrapeUnavailable) as exc:
                last_exc = exc
                if isinstance(exc, ScrapeUnavailable) or attempt == 1:
                    raise
        raise ScrapeUnavailable(str(last_exc) if last_exc else "request failed")

    async def _rate_limit(self, domain: str) -> None:
        lock = self._domain_locks.setdefault(domain, asyncio.Lock())
        async with lock:
            now = time.monotonic()
            wait = RATE_LIMIT_SECONDS - (now - self._last_request_at.get(domain, 0.0))
            if wait > 0:
                await asyncio.sleep(wait)
            self._last_request_at[domain] = time.monotonic()

    async def _validate_url(self, url: str, *, allow_unknown_domain: bool) -> str:
        parsed = urlsplit(str(url or "").strip())
        if parsed.scheme not in {"http", "https"} or not parsed.hostname:
            raise ScrapeBlocked("only http and https URLs are supported")
        domain = normalize_domain(parsed.hostname)
        if is_blocked_domain(domain):
            raise ScrapeBlocked("domain is blocked")
        if not allow_unknown_domain and not is_trusted_domain(domain):
            raise ScrapeBlocked("domain is not trusted for automatic scraping")
        await asyncio.to_thread(_reject_private_host, parsed.hostname)
        return urlunsplit((parsed.scheme, parsed.netloc, parsed.path or "/", parsed.query, ""))


def _reject_private_host(hostname: str) -> None:
    try:
        addresses = [ipaddress.ip_address(hostname)]
    except ValueError:
        try:
            infos = socket.getaddrinfo(hostname, None, type=socket.SOCK_STREAM)
        except socket.gaierror as exc:
            raise ScrapeBlocked("hostname could not be resolved") from exc
        addresses = [ipaddress.ip_address(info[4][0]) for info in infos]
    for address in addresses:
        if (
            address.is_private
            or address.is_loopback
            or address.is_link_local
            or address.is_multicast
            or address.is_reserved
            or address.is_unspecified
        ):
            raise ScrapeBlocked("private or local addresses are not allowed")


def redact_url(url: str) -> str:
    parsed = urlsplit(url)
    return urlunsplit((parsed.scheme, parsed.netloc, parsed.path, "", ""))
