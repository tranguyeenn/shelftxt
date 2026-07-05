"""Best-effort access to LibraryThing's lightweight XML APIs."""

import logging
import os
import re
from urllib.parse import quote
from xml.etree import ElementTree

import httpx

logger = logging.getLogger(__name__)

BASE_URL = "https://www.librarything.com/api"
TIMEOUT_SECONDS = 2.0


def _token() -> str | None:
    return (os.getenv("LIBRARYTHING_API_TOKEN") or "").strip() or None


def _clean_isbn(value: str | None) -> str | None:
    cleaned = re.sub(r"[^0-9Xx]", "", value or "").upper()
    return cleaned if len(cleaned) in {10, 13} else None


def _fetch_xml(endpoint: str, value: str) -> ElementTree.Element | None:
    token = _token()
    if not token:
        return None
    try:
        response = httpx.get(
            f"{BASE_URL}/{quote(token, safe='')}/{endpoint}/{quote(value, safe='')}",
            timeout=TIMEOUT_SECONDS,
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
        logger.warning(
            "LibraryThing %s lookup failed for %r: error=%s status=%s",
            endpoint,
            value,
            type(exc).__name__,
            status,
        )
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
