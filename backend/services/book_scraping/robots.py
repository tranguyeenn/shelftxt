from __future__ import annotations

import time
from dataclasses import dataclass
from urllib.parse import urljoin, urlparse
from urllib.robotparser import RobotFileParser

import httpx


ROBOTS_CACHE_SECONDS = 3600


@dataclass
class RobotsDecision:
    allowed: bool
    cache_hit: bool = False


class RobotsCache:
    def __init__(self) -> None:
        self._cache: dict[str, tuple[float, RobotFileParser | None]] = {}

    async def allowed(self, client: httpx.AsyncClient, url: str, user_agent: str) -> RobotsDecision:
        parsed = urlparse(url)
        base = f"{parsed.scheme}://{parsed.netloc}"
        robots_url = urljoin(base, "/robots.txt")
        now = time.monotonic()
        cached = self._cache.get(base)
        if cached and now - cached[0] < ROBOTS_CACHE_SECONDS:
            parser = cached[1]
            return RobotsDecision(True if parser is None else parser.can_fetch(user_agent, url), cache_hit=True)

        parser: RobotFileParser | None = RobotFileParser(robots_url)
        try:
            response = await client.get(robots_url)
            if response.status_code >= 400:
                parser = None
            else:
                parser.parse(response.text.splitlines())
        except httpx.HTTPError:
            parser = None

        self._cache[base] = (now, parser)
        return RobotsDecision(True if parser is None else parser.can_fetch(user_agent, url), cache_hit=False)


robots_cache = RobotsCache()
