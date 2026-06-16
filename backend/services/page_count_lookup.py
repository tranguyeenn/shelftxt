import logging
import re
from dataclasses import dataclass
from statistics import median

import httpx
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from backend.db.database import get_session_local
from backend.db.models import Book

logger = logging.getLogger(__name__)

LOOKUP_TIMEOUT_SECONDS = 2.0
MAX_BACKFILL_BOOKS = 50
MIN_REASONABLE_PAGES = 50
MAX_REASONABLE_PAGES = 2000


@dataclass(frozen=True)
class PageCountResult:
    pages: int | None
    source: str
    editions_used: int = 0


def normalize_isbn(value: str | None) -> str | None:
    cleaned = re.sub(r"[^0-9Xx]", "", value or "").upper()
    return cleaned if len(cleaned) in {10, 13} else None


def _positive_int(value: object) -> int | None:
    return value if isinstance(value, int) and value > 0 else None


def _reasonable_page_count(value: object) -> int | None:
    pages = _positive_int(value)
    if pages is None or pages < MIN_REASONABLE_PAGES or pages > MAX_REASONABLE_PAGES:
        return None
    return pages


def _quartile(sorted_values: list[int]) -> float:
    count = len(sorted_values)
    if count == 0:
        return 0
    midpoint = count // 2
    if count % 2 == 0:
        return float(median(sorted_values))
    return float(sorted_values[midpoint])


def filter_page_count_outliers(values: list[int]) -> list[int]:
    cleaned = sorted(
        pages
        for pages in values
        if MIN_REASONABLE_PAGES <= pages <= MAX_REASONABLE_PAGES
    )
    if len(cleaned) < 4:
        return cleaned

    midpoint = len(cleaned) // 2
    lower_half = cleaned[:midpoint]
    upper_half = cleaned[midpoint:] if len(cleaned) % 2 == 0 else cleaned[midpoint + 1 :]
    q1 = _quartile(lower_half)
    q3 = _quartile(upper_half)
    iqr = q3 - q1
    lower_bound = q1 - 1.5 * iqr
    upper_bound = q3 + 1.5 * iqr
    filtered = [pages for pages in cleaned if lower_bound <= pages <= upper_bound]
    return filtered or cleaned


def median_page_count(values: list[int]) -> int | None:
    filtered = filter_page_count_outliers(values)
    if not filtered:
        return None
    return int(median(filtered))


def fetch_openlibrary_pages_by_isbn(isbn: str) -> int | None:
    normalized = normalize_isbn(isbn)
    if not normalized:
        return None
    try:
        response = httpx.get(
            f"https://openlibrary.org/isbn/{normalized}.json",
            timeout=LOOKUP_TIMEOUT_SECONDS,
            follow_redirects=True,
        )
        response.raise_for_status()
        payload = response.json()
    except (httpx.HTTPError, ValueError) as exc:
        logger.warning("Open Library page count ISBN lookup failed for %r: %s", isbn, exc)
        return None

    if not isinstance(payload, dict):
        logger.warning("Open Library page count ISBN lookup returned malformed payload for %r", isbn)
        return None
    return _reasonable_page_count(payload.get("number_of_pages"))


def fetch_openlibrary_pages_by_edition(edition_key: str) -> int | None:
    key = edition_key.strip().removeprefix("/books/")
    if not key:
        return None
    try:
        response = httpx.get(
            f"https://openlibrary.org/books/{key}.json",
            timeout=LOOKUP_TIMEOUT_SECONDS,
            follow_redirects=True,
        )
        response.raise_for_status()
        payload = response.json()
    except (httpx.HTTPError, ValueError) as exc:
        logger.warning("Open Library edition page count lookup failed for %r: %s", edition_key, exc)
        return None

    if not isinstance(payload, dict):
        logger.warning("Open Library edition page count lookup returned malformed payload for %r", edition_key)
        return None
    return _reasonable_page_count(payload.get("number_of_pages"))


def _fetch_work_edition_pages(work_key: str) -> list[int]:
    key = work_key.strip().removeprefix("/works/")
    if not key:
        return []
    pages: list[int] = []
    offset = 0
    limit = 100
    while True:
        try:
            response = httpx.get(
                f"https://openlibrary.org/works/{key}/editions.json",
                params={"limit": limit, "offset": offset},
                timeout=LOOKUP_TIMEOUT_SECONDS,
                follow_redirects=True,
            )
            response.raise_for_status()
            payload = response.json()
        except (httpx.HTTPError, ValueError) as exc:
            logger.warning("Open Library work editions lookup failed for %r: %s", work_key, exc)
            return pages

        entries = payload.get("entries", []) if isinstance(payload, dict) else []
        if not isinstance(entries, list):
            logger.warning("Open Library work editions lookup returned malformed entries for %r", work_key)
            return pages
        for entry in entries:
            if not isinstance(entry, dict):
                continue
            page_count = _reasonable_page_count(entry.get("number_of_pages"))
            if page_count is not None:
                pages.append(page_count)

        size = len(entries)
        total = payload.get("size") if isinstance(payload, dict) else None
        offset += size
        if size == 0 or size < limit or not isinstance(total, int) or offset >= total:
            return pages


def fetch_openlibrary_pages_by_title(title: str, author: str | None = None) -> int | None:
    return lookup_page_count_by_title(title, author).pages


def lookup_page_count_by_title(title: str, author: str | None = None) -> PageCountResult:
    clean_title = (title or "").strip()
    if not clean_title:
        return PageCountResult(None, "unavailable")

    params = {"title": clean_title, "limit": 5, "fields": "key,edition_key,title,author_name"}
    if author and author.strip() and author.strip().lower() != "unknown":
        params["author"] = author.strip()

    try:
        response = httpx.get(
            "https://openlibrary.org/search.json",
            params=params,
            timeout=LOOKUP_TIMEOUT_SECONDS,
        )
        response.raise_for_status()
        payload = response.json()
    except (httpx.HTTPError, ValueError) as exc:
        logger.warning("Open Library page count title lookup failed for %r: %s", title, exc)
        return PageCountResult(None, "unavailable")

    docs = payload.get("docs", []) if isinstance(payload, dict) else []
    if not isinstance(docs, list):
        logger.warning("Open Library page count title lookup returned malformed docs for %r", title)
        return PageCountResult(None, "unavailable")

    for doc in docs:
        if not isinstance(doc, dict):
            continue
        page_counts: list[int] = []
        work_key = doc.get("key")
        if isinstance(work_key, str) and work_key.strip():
            page_counts.extend(_fetch_work_edition_pages(work_key))

        edition_keys = doc.get("edition_key")
        if isinstance(edition_keys, list):
            for edition_key in edition_keys:
                if not isinstance(edition_key, str):
                    continue
                pages = fetch_openlibrary_pages_by_edition(edition_key)
                if pages:
                    page_counts.append(pages)

        estimate = median_page_count(page_counts)
        if estimate is not None:
            filtered_count = len(filter_page_count_outliers(page_counts))
            logger.info(
                'Estimated page count for "%s" using %s editions (median=%s)',
                clean_title,
                filtered_count,
                estimate,
            )
            return PageCountResult(estimate, "median_editions", filtered_count)
    return PageCountResult(None, "unavailable")


def lookup_page_count_result(
    title: str,
    author: str | None = None,
    isbn: str | None = None,
    edition_key: str | None = None,
) -> PageCountResult:
    normalized = normalize_isbn(isbn)
    if normalized:
        pages = fetch_openlibrary_pages_by_isbn(normalized)
        if pages:
            return PageCountResult(pages, "exact_isbn", 1)
    if edition_key:
        pages = fetch_openlibrary_pages_by_edition(edition_key)
        if pages:
            return PageCountResult(pages, "exact_edition", 1)
    return lookup_page_count_by_title(title, author)


def lookup_page_count(title: str, author: str | None = None, isbn: str | None = None) -> int | None:
    return lookup_page_count_result(title, author, isbn).pages


def backfill_missing_page_counts(db: Session | None = None, limit: int = MAX_BACKFILL_BOOKS) -> int:
    owns_session = db is None
    session = db
    if session is None:
        try:
            session = get_session_local()()
        except RuntimeError as exc:
            logger.warning("Page count backfill skipped because database is unavailable: %s", exc)
            return 0

    updated = 0
    try:
        try:
            books = (
                session.query(Book)
                .filter(Book.total_pages.is_(None), Book.page_count_checked.is_(False))
                .order_by(Book.id.asc())
                .limit(limit)
                .all()
            )
        except SQLAlchemyError as exc:
            logger.warning("Page count backfill skipped because database query failed: %s", exc)
            return 0
        for book in books:
            try:
                if book.total_pages is None:
                    result = lookup_page_count_result(
                        book.title,
                        book.authors,
                        book.isbn_uid,
                        book.edition_key,
                    )
                    if result.pages and book.total_pages is None:
                        book.total_pages = result.pages
                        book.page_count_source = result.source
                        updated += 1
                    elif result.source == "unavailable":
                        book.page_count_source = "unavailable"
                book.page_count_checked = True
                session.commit()
            except Exception as exc:
                session.rollback()
                try:
                    fresh = session.get(Book, book.id)
                    if fresh is not None and fresh.total_pages is None:
                        fresh.page_count_checked = True
                        session.commit()
                except Exception:
                    session.rollback()
                logger.warning("Page count backfill failed for book %r: %s", book.id, exc, exc_info=True)
        return updated
    finally:
        if owns_session:
            session.close()
