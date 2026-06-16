import logging
import re

import httpx
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from backend.db.database import get_session_local
from backend.db.models import Book

logger = logging.getLogger(__name__)

LOOKUP_TIMEOUT_SECONDS = 2.0
MAX_BACKFILL_BOOKS = 50


def normalize_isbn(value: str | None) -> str | None:
    cleaned = re.sub(r"[^0-9Xx]", "", value or "").upper()
    return cleaned if len(cleaned) in {10, 13} else None


def _positive_int(value: object) -> int | None:
    return value if isinstance(value, int) and value > 0 else None


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
    return _positive_int(payload.get("number_of_pages"))


def _fetch_edition_pages(edition_key: str) -> int | None:
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
    return _positive_int(payload.get("number_of_pages"))


def fetch_openlibrary_pages_by_title(title: str, author: str | None = None) -> int | None:
    clean_title = (title or "").strip()
    if not clean_title:
        return None

    params = {"title": clean_title, "limit": 5, "fields": "edition_key,title,author_name"}
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
        return None

    docs = payload.get("docs", []) if isinstance(payload, dict) else []
    if not isinstance(docs, list):
        logger.warning("Open Library page count title lookup returned malformed docs for %r", title)
        return None

    for doc in docs:
        if not isinstance(doc, dict):
            continue
        edition_keys = doc.get("edition_key")
        if not isinstance(edition_keys, list):
            continue
        for edition_key in edition_keys:
            if not isinstance(edition_key, str):
                continue
            pages = _fetch_edition_pages(edition_key)
            if pages:
                return pages
    return None


def lookup_page_count(title: str, author: str | None = None, isbn: str | None = None) -> int | None:
    normalized = normalize_isbn(isbn)
    if normalized:
        pages = fetch_openlibrary_pages_by_isbn(normalized)
        if pages:
            return pages
    return fetch_openlibrary_pages_by_title(title, author)


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
                    pages = lookup_page_count(book.title, book.authors, book.isbn_uid)
                    if pages and book.total_pages is None:
                        book.total_pages = pages
                        updated += 1
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
