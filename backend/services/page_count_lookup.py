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

OPEN_LIBRARY_TIMEOUT_SECONDS = 2.0
GOOGLE_BOOKS_TIMEOUT_SECONDS = 2.0
LOOKUP_TIMEOUT_SECONDS = OPEN_LIBRARY_TIMEOUT_SECONDS
MAX_BACKFILL_BOOKS = 50
MIN_REASONABLE_PAGES = 50
MAX_REASONABLE_PAGES = 2000
MIN_RELIABLE_TITLE_COUNTS = 3


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
            timeout=OPEN_LIBRARY_TIMEOUT_SECONDS,
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


def fetch_google_pages_by_isbn(isbn: str) -> int | None:
    normalized = normalize_isbn(isbn)
    if not normalized:
        return None
    try:
        response = httpx.get(
            "https://www.googleapis.com/books/v1/volumes",
            params={"q": f"isbn:{normalized}", "maxResults": 5},
            timeout=GOOGLE_BOOKS_TIMEOUT_SECONDS,
        )
        response.raise_for_status()
        payload = response.json()
    except (httpx.HTTPError, ValueError) as exc:
        logger.warning("Google Books page count ISBN lookup failed for %r: %s", isbn, exc)
        return None

    items = payload.get("items", []) if isinstance(payload, dict) else []
    for item in items if isinstance(items, list) else []:
        info = item.get("volumeInfo") if isinstance(item, dict) else None
        pages = _reasonable_page_count(info.get("pageCount")) if isinstance(info, dict) else None
        if pages is not None:
            return pages
    return None


def fetch_openlibrary_pages_by_edition(edition_key: str) -> int | None:
    key = edition_key.strip().removeprefix("/books/")
    if not key:
        return None
    try:
        response = httpx.get(
            f"https://openlibrary.org/books/{key}.json",
            timeout=OPEN_LIBRARY_TIMEOUT_SECONDS,
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
                timeout=OPEN_LIBRARY_TIMEOUT_SECONDS,
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


def _normalized_text(value: str | None) -> str:
    return re.sub(r"[^a-z0-9]+", " ", (value or "").lower()).strip()


def _matches_title(candidate: str | None, expected: str) -> bool:
    candidate_norm = _normalized_text(candidate)
    expected_norm = _normalized_text(expected)
    return bool(candidate_norm and expected_norm and (
        candidate_norm == expected_norm
        or candidate_norm.startswith(f"{expected_norm} ")
        or expected_norm.startswith(f"{candidate_norm} ")
    ))


def _matches_author(candidate: object, expected: str | None) -> bool:
    expected_norm = _normalized_text(expected)
    if not expected_norm or expected_norm == "unknown":
        return True
    values = candidate if isinstance(candidate, list) else [candidate]
    return any(
        expected_norm in _normalized_text(str(value))
        or _normalized_text(str(value)) in expected_norm
        for value in values
        if value
    )


def fetch_openlibrary_title_page_candidates(title: str, author: str | None = None) -> list[int]:
    params = {
        "title": title,
        "limit": 10,
        "fields": "title,author_name,number_of_pages_median,edition_key",
    }
    if author and _normalized_text(author) != "unknown":
        params["author"] = author
    try:
        response = httpx.get(
            "https://openlibrary.org/search.json",
            params=params,
            timeout=OPEN_LIBRARY_TIMEOUT_SECONDS,
        )
        response.raise_for_status()
        payload = response.json()
    except (httpx.HTTPError, ValueError) as exc:
        logger.warning("Open Library page count title lookup failed for %r: %s", title, exc)
        return []

    docs = payload.get("docs", []) if isinstance(payload, dict) else []
    counts: list[int] = []
    for doc in docs if isinstance(docs, list) else []:
        if not isinstance(doc, dict) or not _matches_title(doc.get("title"), title):
            continue
        if not _matches_author(doc.get("author_name"), author):
            continue
        direct = _reasonable_page_count(doc.get("number_of_pages_median"))
        if direct is not None:
            counts.append(direct)
        edition_keys = doc.get("edition_key")
        for edition_key in edition_keys[:3] if isinstance(edition_keys, list) else []:
            if not isinstance(edition_key, str):
                continue
            pages = fetch_openlibrary_pages_by_edition(edition_key)
            if pages is not None:
                counts.append(pages)
    return counts


def fetch_google_title_page_candidates(title: str, author: str | None = None) -> list[int]:
    query = f'intitle:"{title}"'
    if author and _normalized_text(author) != "unknown":
        query += f' inauthor:"{author}"'
    try:
        response = httpx.get(
            "https://www.googleapis.com/books/v1/volumes",
            params={"q": query, "maxResults": 10},
            timeout=GOOGLE_BOOKS_TIMEOUT_SECONDS,
        )
        response.raise_for_status()
        payload = response.json()
    except (httpx.HTTPError, ValueError) as exc:
        logger.warning("Google Books page count title lookup failed for %r: %s", title, exc)
        return []

    items = payload.get("items", []) if isinstance(payload, dict) else []
    counts: list[int] = []
    for item in items if isinstance(items, list) else []:
        info = item.get("volumeInfo") if isinstance(item, dict) else None
        if not isinstance(info, dict) or not _matches_title(info.get("title"), title):
            continue
        if not _matches_author(info.get("authors"), author):
            continue
        pages = _reasonable_page_count(info.get("pageCount"))
        if pages is not None:
            counts.append(pages)
    return counts


def lookup_page_count_by_title(title: str, author: str | None = None) -> PageCountResult:
    clean_title = (title or "").strip()
    if not clean_title:
        return PageCountResult(None, "unavailable")

    candidates = [
        *fetch_openlibrary_title_page_candidates(clean_title, author),
        *fetch_google_title_page_candidates(clean_title, author),
    ]
    filtered = filter_page_count_outliers(candidates)
    if len(filtered) < MIN_RELIABLE_TITLE_COUNTS:
        return PageCountResult(None, "unavailable", len(filtered))
    estimate = int(median(filtered))
    logger.info(
        'Estimated page count for "%s" using %s matching results (median=%s)',
        clean_title,
        len(filtered),
        estimate,
    )
    return PageCountResult(estimate, "median_title_author", len(filtered))


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
            return PageCountResult(pages, "open_library_isbn", 1)
        pages = fetch_google_pages_by_isbn(normalized)
        if pages:
            return PageCountResult(pages, "google_books_isbn", 1)
    if edition_key:
        pages = fetch_openlibrary_pages_by_edition(edition_key)
        if pages:
            return PageCountResult(pages, "open_library_edition", 1)
    return lookup_page_count_by_title(title, author)


def lookup_page_count(title: str, author: str | None = None, isbn: str | None = None) -> int | None:
    return lookup_page_count_result(title, author, isbn).pages


def backfill_missing_page_counts(
    db: Session | None = None,
    limit: int = MAX_BACKFILL_BOOKS,
    user_id=None,
) -> int:
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
            query = session.query(Book).filter(Book.total_pages.is_(None))
            if user_id is not None:
                query = query.filter(Book.user_id == user_id)
            books = query.order_by(Book.id.asc()).limit(limit).all()
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
