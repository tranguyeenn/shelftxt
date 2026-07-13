"""Best-effort access to LibraryThing's lightweight XML APIs."""

from __future__ import annotations

import asyncio
import logging
import os
import re
import time
from urllib.parse import quote
from xml.etree import ElementTree

import httpx

from backend.services.metadata_providers import (
    MetadataProvider,
    ProviderSearchError,
    is_transient_error,
    provider_outcome_for_exception,
)

logger = logging.getLogger(__name__)

BASE_URL = "https://www.librarything.com/api"
TIMEOUT_SECONDS = 2.0
PROVIDER_DEADLINE_SECONDS = 5.0
HTTP_TIMEOUT = httpx.Timeout(4.0, connect=2.0, read=4.0, write=4.0, pool=2.0)
MAX_RETRIES = 1


def _token() -> str | None:
    return (os.getenv("LIBRARYTHING_API_TOKEN") or "").strip() or None


def _clean_isbn(value: str | None) -> str | None:
    cleaned = re.sub(r"[^0-9Xx]", "", value or "").upper()
    return cleaned if len(cleaned) in {10, 13} else None


def _fetch_xml(endpoint: str, value: str) -> ElementTree.Element | None:
    token = _token()
    if not token:
        return None
    raw_url = f"{BASE_URL}/{quote(token, safe='')}/{endpoint}/{quote(value, safe='')}"
    log_url = f"{BASE_URL}/<redacted-token>/{endpoint}/{quote(value, safe='')}"
    for attempt in range(1, MAX_RETRIES + 2):
        started = time.perf_counter()
        try:
            response = httpx.get(
                raw_url,
                timeout=HTTP_TIMEOUT,
                follow_redirects=True,
            )
            response.raise_for_status()
            # stdlib ElementTree does not resolve external entities. Reject doctypes as
            # an additional guard against parsing content other than the tiny API XML.
            if b"<!DOCTYPE" in response.content.upper():
                raise ValueError("doctype is not allowed")
            return ElementTree.fromstring(response.content)
        except (httpx.HTTPError, ElementTree.ParseError, ValueError) as exc:
            # The token is part of the request path, so never log the exception text
            # (httpx exceptions can include the full URL).
            status = exc.response.status_code if isinstance(exc, httpx.HTTPStatusError) else None
            body = exc.response.text[:1000] if isinstance(exc, httpx.HTTPStatusError) else None
            transient = is_transient_error(exc)
            logger.warning(
                "LibraryThing %s lookup failed for %r: error=%s status=%s attempt=%s transient=%s",
                endpoint,
                value,
                type(exc).__name__,
                status,
                attempt,
                transient,
                extra={
                    "provider": "librarything",
                    "http_status": status,
                    "request_url": log_url,
                    "response_body": body,
                    "exception_type": type(exc).__name__,
                    "elapsed_ms": round((time.perf_counter() - started) * 1000, 2),
                    "outcome": provider_outcome_for_exception(exc),
                },
            )
            if attempt > MAX_RETRIES or not transient:
                return None
    return None


def _isbns_from_xml(root: ElementTree.Element) -> list[str]:
    values: list[str] = []
    seen: set[str] = set()
    for element in root.iter():
        if element.tag.rsplit("}", 1)[-1].lower() != "isbn":
            continue
        isbn = _clean_isbn(element.text)
        if isbn and isbn not in seen:
            seen.add(isbn)
            values.append(isbn)
    return values


def fetch_related_isbns(isbn: str) -> list[str]:
    """Return ISBNs for editions of the same work, or an empty list on failure."""
    normalized = _clean_isbn(isbn)
    if not normalized:
        return []
    root = _fetch_xml("thingISBN", normalized)
    return _isbns_from_xml(root) if root is not None else []


def fetch_work_by_title(title: str) -> dict | None:
    """Return the most likely LibraryThing work represented by a title."""
    clean_title = (title or "").strip()
    if not clean_title:
        return None
    root = _fetch_xml("thingTitle", clean_title)
    if root is None:
        return None

    def first_text(tag: str) -> str | None:
        for element in root.iter():
            if element.tag.rsplit("}", 1)[-1].lower() == tag:
                value = (element.text or "").strip()
                if value:
                    return value
        return None

    related_isbns = _isbns_from_xml(root)
    work_title = first_text("title")
    work_url = first_text("link")
    if not (related_isbns or work_title or work_url):
        return None
    return {
        "title": work_title,
        "work_url": work_url,
        "related_isbns": related_isbns,
    }


class LibraryThingProvider(MetadataProvider):
    name = "librarything"
    timeout_seconds = PROVIDER_DEADLINE_SECONDS
    max_retries = 1

    async def search(self, query: str) -> list[dict]:
        if not _token():
            raise ProviderSearchError(
                "LibraryThing API token is not configured",
                provider=self.name,
                outcome="not_configured",
                exception_type="MissingConfiguration",
            )
        from backend.services.book_search import _librarything_results

        return await asyncio.to_thread(_librarything_results, query)


def search_candidates(query: str) -> list[dict]:
    from backend.services.book_search import _librarything_results

    return _librarything_results(query)
