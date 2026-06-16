import logging
import re
from dataclasses import dataclass

import httpx

from backend.services.metadata_normalization import (
    normalize_language,
    normalize_values,
    filter_specific_genres,
    filter_specific_subjects,
)

logger = logging.getLogger(__name__)

LOOKUP_TIMEOUT_SECONDS = 2.0


class GoogleBooksRateLimited(Exception):
    pass


class OpenLibraryTimeout(Exception):
    pass


@dataclass(frozen=True)
class BookMetadata:
    title: str | None = None
    authors: str | None = None
    total_pages: int | None = None
    subjects: list[str] | None = None
    genres: list[str] | None = None
    language: str | None = None
    work_key: str | None = None
    edition_key: str | None = None


def looks_like_isbn(value: str | None) -> bool:
    cleaned = re.sub(r"[^0-9Xx]", "", value or "")
    return len(cleaned) in {10, 13}


def normalize_isbn(value: str | None) -> str | None:
    if not looks_like_isbn(value):
        return None
    return re.sub(r"[^0-9Xx]", "", value or "").upper()


def _positive_int(value: object) -> int | None:
    if isinstance(value, int) and value > 0:
        return value
    return None


def _authors_from_open_library_doc(doc: dict) -> str | None:
    authors = doc.get("author_name") or doc.get("authors")
    if isinstance(authors, list):
        cleaned: list[str] = []
        for author in authors:
            if isinstance(author, str) and author.strip():
                cleaned.append(author.strip())
            elif isinstance(author, dict):
                name = author.get("name")
                if isinstance(name, str) and name.strip():
                    cleaned.append(name.strip())
        if cleaned:
            return ", ".join(cleaned)
    return None


def _metadata_has_value(metadata: BookMetadata | None) -> bool:
    return bool(
        metadata
        and (
            metadata.title
            or metadata.authors
            or metadata.total_pages
            or metadata.subjects
            or metadata.genres
            or metadata.language
            or metadata.work_key
            or metadata.edition_key
        )
    )


def _merge_metadata(base: BookMetadata, next_metadata: BookMetadata | None) -> BookMetadata:
    if next_metadata is None:
        return base
    return BookMetadata(
        title=base.title or next_metadata.title,
        authors=base.authors or next_metadata.authors,
        total_pages=base.total_pages or next_metadata.total_pages,
        subjects=base.subjects or next_metadata.subjects,
        genres=base.genres or next_metadata.genres,
        language=base.language or next_metadata.language,
        work_key=base.work_key or next_metadata.work_key,
        edition_key=base.edition_key or next_metadata.edition_key,
    )


def _metadata_complete(metadata: BookMetadata) -> bool:
    return bool(metadata.title and metadata.authors and metadata.total_pages)


def _key_from_open_library_ref(value: object) -> str | None:
    if isinstance(value, dict):
        key = value.get("key")
        return key if isinstance(key, str) and key.strip() else None
    if isinstance(value, str) and value.strip():
        return value.strip()
    return None


def _first_key(values: object) -> str | None:
    if isinstance(values, list):
        for value in values:
            key = _key_from_open_library_ref(value)
            if key:
                return key
    return _key_from_open_library_ref(values)


def _language_from_open_library(value: object) -> str | None:
    if isinstance(value, list):
        for item in value:
            language = _language_from_open_library(item)
            if language:
                return language
        return None
    key = _key_from_open_library_ref(value)
    if key:
        return normalize_language(key.rsplit("/", 1)[-1])
    if isinstance(value, str):
        normalized = normalize_language(value)
        return normalized or None
    return None


def _metadata_from_open_library_payload(payload: dict, *, edition_key: str | None = None) -> BookMetadata:
    subjects = filter_specific_subjects(payload.get("subjects") or payload.get("subject"))
    genres = filter_specific_genres(payload.get("genres"))
    return BookMetadata(
        title=payload.get("title") if isinstance(payload.get("title"), str) else None,
        authors=_authors_from_open_library_doc(payload),
        total_pages=_positive_int(payload.get("number_of_pages")),
        subjects=subjects or None,
        genres=genres or subjects or None,
        language=_language_from_open_library(payload.get("languages") or payload.get("language")),
        work_key=_first_key(payload.get("works") or payload.get("key")),
        edition_key=edition_key or _first_key(payload.get("edition_key") or payload.get("key")),
    )


def lookup_google_books_by_isbn(isbn: str) -> BookMetadata | None:
    try:
        response = httpx.get(
            "https://www.googleapis.com/books/v1/volumes",
            params={"q": f"isbn:{isbn}"},
            timeout=LOOKUP_TIMEOUT_SECONDS,
        )
        response.raise_for_status()
        payload = response.json()
    except httpx.HTTPStatusError as exc:
        if exc.response.status_code == 429:
            logger.warning("Google Books ISBN lookup rate limited for %r", isbn)
            raise GoogleBooksRateLimited(str(exc)) from exc
        logger.warning("Google Books ISBN lookup failed for %r: %s", isbn, exc)
        return None
    except (httpx.HTTPError, ValueError) as exc:
        logger.warning("Google Books ISBN lookup failed for %r: %s", isbn, exc)
        return None

    items = payload.get("items", []) if isinstance(payload, dict) else []
    if not isinstance(items, list):
        logger.warning("Google Books ISBN lookup returned malformed items for %r", isbn)
        return None

    for item in items:
        if not isinstance(item, dict):
            continue
        info = item.get("volumeInfo")
        if not isinstance(info, dict):
            continue
        authors = info.get("authors")
        metadata = BookMetadata(
            title=info.get("title") if isinstance(info.get("title"), str) else None,
            authors=", ".join(a.strip() for a in authors if isinstance(a, str) and a.strip())
            if isinstance(authors, list)
            else None,
            total_pages=_positive_int(info.get("pageCount")),
            subjects=filter_specific_subjects(info.get("categories")) or None,
            genres=filter_specific_genres(info.get("categories")) or None,
            language=normalize_language(info.get("language")) or None,
        )
        if _metadata_has_value(metadata):
            return metadata

    logger.warning("Google Books ISBN lookup found no metadata for %r", isbn)
    return None


def lookup_open_library_by_isbn(isbn: str) -> BookMetadata | None:
    try:
        response = httpx.get(
            f"https://openlibrary.org/isbn/{isbn}.json",
            timeout=LOOKUP_TIMEOUT_SECONDS,
            follow_redirects=True,
        )
        response.raise_for_status()
        payload = response.json()
    except httpx.TimeoutException as exc:
        logger.warning("Open Library ISBN lookup timed out for %r: %s", isbn, exc)
        raise OpenLibraryTimeout(str(exc)) from exc
    except (httpx.HTTPError, ValueError) as exc:
        logger.warning("Open Library ISBN lookup failed for %r: %s", isbn, exc)
        return None

    if not isinstance(payload, dict):
        logger.warning("Open Library ISBN lookup returned malformed payload for %r", isbn)
        return None

    metadata = _metadata_from_open_library_payload(payload)
    if _metadata_has_value(metadata):
        return metadata
    return None


def lookup_open_library_by_title(title: str, author: str | None = None) -> BookMetadata | None:
    query = f"{title} {author or ''}".strip()
    if not query:
        return None

    try:
        response = httpx.get(
            "https://openlibrary.org/search.json",
            params={
                "q": query,
                "limit": 5,
                "fields": "title,author_name,edition_key,subject,language,key,number_of_pages_median",
            },
            timeout=LOOKUP_TIMEOUT_SECONDS,
        )
        response.raise_for_status()
        payload = response.json()
    except httpx.TimeoutException as exc:
        logger.warning("Open Library title lookup timed out for %r: %s", query, exc)
        raise OpenLibraryTimeout(str(exc)) from exc
    except (httpx.HTTPError, ValueError) as exc:
        logger.warning("Open Library title lookup failed for %r: %s", query, exc)
        return None

    docs = payload.get("docs", []) if isinstance(payload, dict) else []
    if not isinstance(docs, list):
        logger.warning("Open Library title lookup returned malformed docs for %r", query)
        return None

    for doc in docs:
        if not isinstance(doc, dict):
            continue
        metadata = BookMetadata(
            title=doc.get("title") if isinstance(doc.get("title"), str) else None,
            authors=_authors_from_open_library_doc(doc),
            total_pages=_positive_int(doc.get("number_of_pages_median")),
            subjects=filter_specific_subjects(doc.get("subject")) or None,
            genres=filter_specific_subjects(doc.get("subject")) or None,
            language=normalize_values(doc.get("language"), normalize_language)[0]
            if normalize_values(doc.get("language"), normalize_language)
            else None,
            work_key=doc.get("key") if isinstance(doc.get("key"), str) else None,
            edition_key=(doc.get("edition_key") or [None])[0]
            if isinstance(doc.get("edition_key"), list)
            else None,
        )
        if _metadata_has_value(metadata):
            return metadata

    logger.warning("Open Library title lookup found no metadata for %r", query)
    return None


def lookup_book_metadata(
    title: str | None,
    author: str | None = None,
    isbn_uid: str | None = None,
) -> BookMetadata | None:
    metadata = BookMetadata()
    isbn = normalize_isbn(isbn_uid)
    if isbn:
        try:
            metadata = _merge_metadata(metadata, lookup_google_books_by_isbn(isbn))
        except GoogleBooksRateLimited:
            pass
        if _metadata_complete(metadata):
            return metadata

        try:
            metadata = _merge_metadata(metadata, lookup_open_library_by_isbn(isbn))
        except OpenLibraryTimeout:
            pass
        if _metadata_complete(metadata):
            return metadata

    clean_title = (title or "").strip()
    if clean_title and author:
        try:
            metadata = _merge_metadata(metadata, lookup_open_library_by_title(clean_title, author))
        except OpenLibraryTimeout:
            pass
        if _metadata_complete(metadata):
            return metadata

    if clean_title:
        try:
            metadata = _merge_metadata(metadata, lookup_open_library_by_title(clean_title))
        except OpenLibraryTimeout:
            pass

    return metadata if _metadata_has_value(metadata) else None


def lookup_total_pages(title: str, author: str | None = None) -> int | None:
    query = f"{title} {author or ''}".strip()

    try:
        response = httpx.get(
            "https://openlibrary.org/search.json",
            params={"q": query, "limit": 5, "fields": "title,author_name,number_of_pages_median"},
            timeout=LOOKUP_TIMEOUT_SECONDS,
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
            timeout=LOOKUP_TIMEOUT_SECONDS,
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
