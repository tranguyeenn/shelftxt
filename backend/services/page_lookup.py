import logging

import httpx

logger = logging.getLogger(__name__)


def lookup_total_pages(title: str, author: str | None = None) -> int | None:
    query = f"{title} {author or ''}".strip()

    try:
        response = httpx.get(
            "https://openlibrary.org/search.json",
            params={"q": query, "limit": 5, "fields": "title,author_name,number_of_pages_median"},
            timeout=5.0,
        )
        response.raise_for_status()
    except httpx.HTTPError as exc:
        logger.warning("Page count lookup failed for %r: %s", title, exc)
        return None

    try:
        docs = response.json().get("docs", [])
    except ValueError as exc:
        logger.warning("Page count lookup returned invalid JSON for %r: %s", title, exc)
        return None

    for doc in docs:
        pages = doc.get("number_of_pages_median")
        if isinstance(pages, int) and pages > 0:
            return pages

    logger.warning("Page count lookup found no page count for %r", title)
    return None
