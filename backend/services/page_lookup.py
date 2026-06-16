import logging
import re
from dataclasses import dataclass

import httpx

logger = logging.getLogger(__name__)

LOOKUP_TIMEOUT_SECONDS = 2.0


@dataclass(frozen=True)
class BookMetadata:
    title: str | None = None
    authors: str | None = None
    total_pages: int | None = None


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
    return bool(metadata and (metadata.title or metadata.authors or metadata.total_pages))


def _merge_metadata(base: BookMetadata, next_metadata: BookMetadata | None) -> BookMetadata:
    if next_metadata is None:
        return base
    return BookMetadata(
        title=base.title or next_metadata.title,
        authors=base.authors or next_metadata.authors,
        total_pages=base.total_pages or next_metadata.total_pages,
    )


def _metadata_complete(metadata: BookMetadata) -> bool:
    return bool(metadata.title and metadata.authors and metadata.total_pages)


def lookup_google_books_by_isbn(isbn: str) -> BookMetadata | None:
    try:
        response = httpx.get(
            "https://www.googleapis.com/books/v1/volumes",
            params={"q": f"isbn:{isbn}"},
            timeout=LOOKUP_TIMEOUT_SECONDS,
        )
        response.raise_for_status()
        payload = response.json()
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
        )
        response.raise_for_status()
        payload = response.json()
    except (httpx.HTTPError, ValueError) as exc:
        logger.warning("Open Library ISBN lookup failed for %r: %s", isbn, exc)
        return None

    if not isinstance(payload, dict):
        logger.warning("Open Library ISBN lookup returned malformed payload for %r", isbn)
        return None

    metadata = BookMetadata(
        title=payload.get("title") if isinstance(payload.get("title"), str) else None,
        authors=_authors_from_open_library_doc(payload),
        total_pages=_positive_int(payload.get("number_of_pages")),
    )
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
                "fields": "title,author_name,number_of_pages_median",
            },
            timeout=LOOKUP_TIMEOUT_SECONDS,
        )
        response.raise_for_status()
        payload = response.json()
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
        metadata = _merge_metadata(metadata, lookup_google_books_by_isbn(isbn))
        if _metadata_complete(metadata):
            return metadata

        metadata = _merge_metadata(metadata, lookup_open_library_by_isbn(isbn))
        if _metadata_complete(metadata):
            return metadata

    clean_title = (title or "").strip()
    if clean_title and author:
        metadata = _merge_metadata(metadata, lookup_open_library_by_title(clean_title, author))
        if _metadata_complete(metadata):
            return metadata

    if clean_title:
        metadata = _merge_metadata(metadata, lookup_open_library_by_title(clean_title))

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
