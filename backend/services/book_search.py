"""Normalized, resilient book search across metadata providers and local books."""

import logging
import re
from typing import Any

import httpx
from sqlalchemy.orm import Session

from backend.db.models import Book
from backend.services.metadata_normalization import (
    filter_specific_subjects,
    normalize_genre_list,
    subjects_to_genres,
)
from backend.services.open_library_editions import (
    edition_fields,
    select_best_open_library_edition,
)
from backend.services.book_resolver import resolve_book

logger = logging.getLogger(__name__)

OPEN_LIBRARY_SEARCH_TIMEOUT_SECONDS = 3.0
GOOGLE_BOOKS_SEARCH_TIMEOUT_SECONDS = 3.0
SEARCH_RESULT_LIMIT = 12


def _clean_text(value: Any) -> str | None:
    return value.strip() if isinstance(value, str) and value.strip() else None


def _positive_int(value: Any) -> int | None:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return None
    return parsed if parsed > 0 else None


def _normalize_isbn(value: Any) -> str | None:
    cleaned = re.sub(r"[^0-9Xx]", "", str(value or "")).upper()
    return cleaned if len(cleaned) in {10, 13} else None


def _normalized_result(**values: Any) -> dict:
    authors = values.get("authors") or []
    if isinstance(authors, str):
        authors = [authors]
    return {
        "title": _clean_text(values.get("title")) or "Untitled",
        "authors": [str(author).strip() for author in authors if str(author).strip()],
        "isbn_uid": _normalize_isbn(values.get("isbn_uid")),
        "description": _clean_text(values.get("description")),
        "cover_url": _clean_text(values.get("cover_url")),
        "total_pages": _positive_int(values.get("total_pages")),
        "subjects": list(dict.fromkeys(values.get("subjects") or [])),
        "genres": list(dict.fromkeys(values.get("genres") or [])),
        "first_publish_year": _positive_int(values.get("first_publish_year")),
        "metadata_source": values.get("metadata_source") or "local",
        "work_key": _clean_text(values.get("work_key")),
        "edition_key": _clean_text(values.get("edition_key")),
        "publisher": _clean_text(values.get("publisher")),
        "publish_date": _clean_text(values.get("publish_date")),
        "language": _clean_text(values.get("language")),
        "related_isbns": list(
            dict.fromkeys(
                isbn
                for value in values.get("related_isbns") or []
                if (isbn := _normalize_isbn(value))
            )
        ),
        "already_in_library": bool(values.get("already_in_library", False)),
}


def _fetch_open_library_exact_edition(isbn: str) -> dict | None:
    try:
        response = httpx.get(
            f"https://openlibrary.org/isbn/{isbn}.json",
            timeout=OPEN_LIBRARY_SEARCH_TIMEOUT_SECONDS,
            follow_redirects=True,
        )
        response.raise_for_status()
        payload = response.json()
        return payload if isinstance(payload, dict) else None
    except (httpx.HTTPError, ValueError) as exc:
        logger.warning("Open Library exact edition lookup failed: error=%s", type(exc).__name__)
        return None


def _fetch_open_library_work_editions(work_key: str | None) -> list[dict]:
    key = str(work_key or "").strip().removeprefix("/works/")
    if not key:
        return []
    try:
        response = httpx.get(
            f"https://openlibrary.org/works/{key}/editions.json",
            params={"limit": 100},
            timeout=OPEN_LIBRARY_SEARCH_TIMEOUT_SECONDS,
            follow_redirects=True,
        )
        response.raise_for_status()
        payload = response.json()
    except (httpx.HTTPError, ValueError) as exc:
        logger.warning("Open Library work editions lookup failed: error=%s", type(exc).__name__)
        return []
    entries = payload.get("entries", []) if isinstance(payload, dict) else []
    return [entry for entry in entries if isinstance(entry, dict)] if isinstance(entries, list) else []


def _author_matches_query(authors: object, query: str) -> bool:
    query_key = query.casefold()
    return any(
        str(author).strip().casefold() in query_key
        for author in authors if str(author).strip()
    ) if isinstance(authors, list) else False


def _open_library_results(query: str) -> list[dict]:
    exact_isbn = _normalize_isbn(query)
    exact_edition = _fetch_open_library_exact_edition(exact_isbn) if exact_isbn else None
    try:
        response = httpx.get(
            "https://openlibrary.org/search.json",
            params={
                "q": f"isbn:{exact_isbn}" if exact_isbn else query,
                "limit": 8,
                "fields": (
                    "title,author_name,subject,key,description,first_publish_year"
                ),
            },
            timeout=OPEN_LIBRARY_SEARCH_TIMEOUT_SECONDS,
        )
        response.raise_for_status()
        payload = response.json()
    except (httpx.HTTPError, ValueError) as exc:
        logger.warning("Open Library search failed: error=%s", type(exc).__name__)
        return []

    docs = payload.get("docs", []) if isinstance(payload, dict) else []
    if exact_edition and not docs:
        work_key = None
        works = exact_edition.get("works")
        if isinstance(works, list) and works and isinstance(works[0], dict):
            work_key = works[0].get("key")
        return [
            _normalized_result(
                title=exact_edition.get("title"),
                authors=[],
                metadata_source="open_library",
                work_key=work_key,
                **edition_fields(exact_edition),
            )
        ]

    if exact_edition and isinstance(docs, list):
        works = exact_edition.get("works")
        exact_work_key = (
            works[0].get("key")
            if isinstance(works, list) and works and isinstance(works[0], dict)
            else None
        )
        matching_docs = [doc for doc in docs if isinstance(doc, dict) and doc.get("key") == exact_work_key]
        docs = matching_docs[:1] or docs[:1]

    results: list[dict] = []
    for index, doc in enumerate(docs if isinstance(docs, list) else []):
        if not isinstance(doc, dict) or not _clean_text(doc.get("title")):
            continue
        subjects = filter_specific_subjects(doc.get("subject"))
        selected_edition = exact_edition if exact_isbn else None
        if selected_edition is None and index < 5:
            selected_edition = select_best_open_library_edition(
                _fetch_open_library_work_editions(doc.get("key")),
                query=query,
                displayed_title=doc.get("title"),
                author_work_match=_author_matches_query(doc.get("author_name"), query),
            )
        selected_fields = edition_fields(selected_edition)
        results.append(
            _normalized_result(
                title=(selected_edition or {}).get("title") if exact_isbn else doc.get("title"),
                authors=doc.get("author_name") or [],
                description=doc.get("description"),
                subjects=subjects,
                genres=subjects_to_genres(subjects),
                first_publish_year=doc.get("first_publish_year"),
                metadata_source="open_library",
                work_key=doc.get("key"),
                **selected_fields,
            )
        )
    return results


def _google_books_results(query: str) -> list[dict]:
    isbn = _normalize_isbn(query)
    try:
        response = httpx.get(
            "https://www.googleapis.com/books/v1/volumes",
            params={"q": f"isbn:{isbn}" if isbn else query, "maxResults": 8},
            timeout=GOOGLE_BOOKS_SEARCH_TIMEOUT_SECONDS,
        )
        response.raise_for_status()
        payload = response.json()
    except (httpx.HTTPError, ValueError) as exc:
        logger.warning("Google Books search failed: error=%s", type(exc).__name__)
        return []

    items = payload.get("items", []) if isinstance(payload, dict) else []
    results: list[dict] = []
    for item in items if isinstance(items, list) else []:
        info = item.get("volumeInfo") if isinstance(item, dict) else None
        if not isinstance(info, dict) or not _clean_text(info.get("title")):
            continue
        identifiers = info.get("industryIdentifiers") or []
        found_isbn = next(
            (
                _normalize_isbn(identifier.get("identifier"))
                for identifier in identifiers
                if isinstance(identifier, dict) and _normalize_isbn(identifier.get("identifier"))
            ),
            None,
        )
        image_links = info.get("imageLinks") if isinstance(info.get("imageLinks"), dict) else {}
        cover_url = image_links.get("thumbnail") or image_links.get("smallThumbnail")
        if isinstance(cover_url, str) and cover_url.startswith("http://"):
            cover_url = f"https://{cover_url[7:]}"
        subjects = filter_specific_subjects(info.get("categories"))
        results.append(
            _normalized_result(
                title=info.get("title"),
                authors=info.get("authors") or [],
                isbn_uid=found_isbn,
                description=info.get("description"),
                cover_url=cover_url,
                total_pages=info.get("pageCount"),
                subjects=subjects,
                genres=normalize_genre_list(info.get("categories")),
                first_publish_year=str(info.get("publishedDate") or "")[:4],
                metadata_source="google_books",
                edition_key=item.get("id"),
                publisher=info.get("publisher"),
                publish_date=info.get("publishedDate"),
                language=info.get("language"),
            )
        )
    return results


def _local_results(books: list[Book], query: str) -> list[dict]:
    terms = [term for term in query.casefold().split() if term]
    results: list[dict] = []
    for book in books:
        searchable = " ".join(
            [
                book.title or "",
                book.authors or "",
                book.isbn_uid or "",
                book.description or "",
                " ".join(book.subjects or []),
                " ".join(book.genres or []),
                book.work_key or "",
                book.edition_key or "",
                str(book.first_publish_year or ""),
                " ".join(
                    ((book.book_metadata or {}).get("librarything", {}) or {}).get(
                        "related_isbns", []
                    )
                ),
            ]
        ).casefold()
        if terms and not all(term in searchable for term in terms):
            continue
        lt_data = (book.book_metadata or {}).get("librarything", {})
        results.append(
            _normalized_result(
                title=book.title,
                authors=[value.strip() for value in (book.authors or "").split(",") if value.strip()],
                isbn_uid=book.isbn_uid,
                description=book.description,
                cover_url=book.cover_url,
                total_pages=book.total_pages,
                subjects=book.subjects or [],
                genres=book.genres or [],
                first_publish_year=book.first_publish_year,
                metadata_source="local",
                work_key=book.work_key,
                edition_key=book.edition_key,
                related_isbns=lt_data.get("related_isbns", []) if isinstance(lt_data, dict) else [],
                already_in_library=True,
            )
        )
    return results


def _result_keys(result: dict) -> set[tuple[str, str]]:
    keys: set[tuple[str, str]] = set()
    isbn = result.get("isbn_uid")
    if isbn:
        keys.add(("isbn", isbn))
    author = result.get("authors", [""])[0] if result.get("authors") else ""
    keys.add((str(result.get("title", "")).casefold(), str(author).casefold()))
    return keys


def _mark_duplicates(results: list[dict], books: list[Book]) -> None:
    existing_isbns: set[str] = set()
    existing_work_keys: set[str] = set()
    existing_edition_keys: set[str] = set()
    for book in books:
        if isbn := _normalize_isbn(book.isbn_uid):
            existing_isbns.add(isbn)
        if book.work_key:
            existing_work_keys.add(book.work_key)
        if book.edition_key:
            existing_edition_keys.add(book.edition_key)
        lt_data = (book.book_metadata or {}).get("librarything", {})
        if isinstance(lt_data, dict):
            existing_isbns.update(
                isbn
                for value in lt_data.get("related_isbns", [])
                if (isbn := _normalize_isbn(value))
            )

    for result in results:
        candidate_isbns = set(result.get("related_isbns") or [])
        if result.get("isbn_uid"):
            candidate_isbns.add(result["isbn_uid"])
        result["already_in_library"] = bool(
            result.get("already_in_library")
            or candidate_isbns.intersection(existing_isbns)
            or (result.get("work_key") and result["work_key"] in existing_work_keys)
            or (result.get("edition_key") and result["edition_key"] in existing_edition_keys)
        )


def search_books(db: Session, user_id, query: str) -> list[dict]:
    clean_query = query.strip()
    if not clean_query:
        return []
    books = db.query(Book).filter(Book.user_id == user_id).all()

    canonical = resolve_book(clean_query)
    deduped: list[dict] = []
    if canonical is not None:
        data = canonical.to_dict()
        deduped.append(
            _normalized_result(
                **data,
                isbn_uid=data.get("isbn"),
                metadata_source=data.get("source"),
            )
        )
    seen: set[tuple[str, str]] = set()
    for result in deduped:
        keys = _result_keys(result)
        seen.update(keys)

    for result in _local_results(books, clean_query):
        keys = _result_keys(result)
        if not keys.intersection(seen):
            seen.update(keys)
            deduped.append(result)
    _mark_duplicates(deduped, books)
    return deduped[:SEARCH_RESULT_LIMIT]
