from __future__ import annotations

import time

import httpx

from backend.services.book_scraping.client import BookScrapingClient, ScrapeBlocked, ScrapeUnavailable, redact_url
from backend.services.book_scraping.metadata import fields_extracted, parse_book_metadata
from backend.services.book_scraping.models import ScrapeDiagnostic, ScrapeResult


metadata_cache: dict[str, ScrapeResult] = {}


async def scrape_book_metadata(url: str, *, allow_unknown_domain: bool = False) -> ScrapeResult:
    redacted_url = redact_url(url)
    started = time.perf_counter()
    if url in metadata_cache:
        cached = metadata_cache[url]
        diagnostics = cached.diagnostics.model_copy(update={"cache_hit": True, "request_url": redacted_url})
        return ScrapeResult(status=cached.status, metadata=cached.metadata, diagnostics=diagnostics)

    client = BookScrapingClient()
    try:
        page = await client.fetch(url, allow_unknown_domain=allow_unknown_domain)
        metadata, malformed_jsonld = parse_book_metadata(page.html, page.url)
        if metadata is None:
            result = ScrapeResult(
                status="empty",
                metadata=None,
                diagnostics=ScrapeDiagnostic(
                    domain=page.domain,
                    outcome="parsing_failure" if malformed_jsonld else "empty",
                    http_status=page.status_code,
                    elapsed_ms=page.elapsed_ms,
                    parser_used="jsonld" if malformed_jsonld else None,
                    robots_allowed=page.robots_allowed,
                    response_content_type=page.content_type,
                    cache_hit=page.cache_hit,
                    request_url=redact_url(page.url),
                ),
            )
        else:
            result = ScrapeResult(
                status="success",
                metadata=metadata,
                diagnostics=ScrapeDiagnostic(
                    domain=page.domain,
                    outcome="success",
                    http_status=page.status_code,
                    elapsed_ms=page.elapsed_ms,
                    parser_used=metadata.parser_used,
                    robots_allowed=page.robots_allowed,
                    fields_extracted=fields_extracted(metadata),
                    response_content_type=page.content_type,
                    cache_hit=page.cache_hit,
                    request_url=redact_url(page.url),
                ),
            )
        if result.status == "success":
            metadata_cache[url] = result
        return result
    except ScrapeBlocked as exc:
        return ScrapeResult(
            status="blocked",
            metadata=None,
            diagnostics=ScrapeDiagnostic(
                outcome="blocked",
                elapsed_ms=round((time.perf_counter() - started) * 1000, 2),
                robots_allowed=False if "robots" in str(exc).casefold() else None,
                exception_type=type(exc).__name__,
                request_url=redacted_url,
            ),
        )
    except (ScrapeUnavailable, httpx.HTTPError, Exception) as exc:
        return ScrapeResult(
            status="failed",
            metadata=None,
            diagnostics=ScrapeDiagnostic(
                outcome="timeout" if isinstance(exc, httpx.TimeoutException) else "failed",
                elapsed_ms=round((time.perf_counter() - started) * 1000, 2),
                exception_type=type(exc).__name__,
                request_url=redacted_url,
            ),
        )
