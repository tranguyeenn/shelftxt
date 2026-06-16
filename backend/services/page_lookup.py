import logging

import httpx

logger = logging.getLogger(__name__)


def lookup_total_pages(title: str, author: str | None = None) -> int | None:
    query = f"{title} {author or ''}".strip()

    try:
        response = httpx.get(
            "https://openlibrary.org/search.json",
            params={"q": query, "limit": 5, "fields": "title,author_name,number_of_pages_median"},
            timeout=2.0,
        )
        response.raise_for_status()
    except httpx.HTTPError as exc:
        logger.warning("Page count lookup failed for %r: %s", title, exc)
        return None

    try:
        payload = response.json()
        docs = payload.get("docs", []) if isinstance(payload, dict) else []
    except ValueError as exc:
        logger.warning("Page count lookup returned invalid JSON for %r: %s", title, exc)
        return None

    if not isinstance(docs, list):
        logger.warning("Page count lookup returned malformed docs for %r", title)
        return None

    for doc in docs:
        if not isinstance(doc, dict):
            continue
        pages = doc.get("number_of_pages_median")
        if isinstance(pages, int) and pages > 0:
            return pages

    logger.warning("Page count lookup found no page count for %r", title)
    return None


def lookup_author_name(title: str) -> str | None:
    try:
        response = httpx.get(
            "https://openlibrary.org/search.json",
            params={"q": title, "limit": 5, "fields": "title,author_name"},
            timeout=2.0,
        )
        response.raise_for_status()
    except httpx.HTTPError as exc:
        logger.warning("Author lookup failed for %r: %s", title, exc)
        return None

    try:
        payload = response.json()
        docs = payload.get("docs", []) if isinstance(payload, dict) else []
    except ValueError as exc:
        logger.warning("Author lookup returned invalid JSON for %r: %s", title, exc)
        return None

    if not isinstance(docs, list):
        logger.warning("Author lookup returned malformed docs for %r", title)
        return None

    for doc in docs:
        if not isinstance(doc, dict):
            continue
        authors = doc.get("author_name")
        if isinstance(authors, list):
            for author in authors:
                if isinstance(author, str) and author.strip():
                    return author.strip()

    logger.warning("Author lookup found no author for %r", title)
    return None
