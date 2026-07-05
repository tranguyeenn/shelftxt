import logging
import re
from dataclasses import dataclass
from datetime import datetime, timezone

import httpx

from app.integrations import librarything
from backend.services.goodreads_metadata import lookup_goodreads_metadata
from backend.services.metadata_normalization import (
    MAX_GENRES_PER_BOOK,
    normalize_language,
    normalize_values,
    clean_reader_tags,
    filter_specific_genres,
    filter_specific_subjects,
    normalize_genre_list,
    subjects_to_genres,
)
from backend.services.metadata_merge import merge_metadata_records
from backend.services.open_library_editions import edition_fields, select_best_open_library_edition

logger = logging.getLogger(__name__)

OPEN_LIBRARY_TIMEOUT_SECONDS = 2.0
GOOGLE_BOOKS_TIMEOUT_SECONDS = 2.0
# Backward compatibility for callers/tests importing the old shared timeout.
LOOKUP_TIMEOUT_SECONDS = OPEN_LIBRARY_TIMEOUT_SECONDS


class GoogleBooksRateLimited(Exception):
    pass


class OpenLibraryTimeout(Exception):
    pass


@dataclass(frozen=True)
class BookMetadata:
    title: str | None = None
    authors: str | None = None
    total_pages: int | None = None
    description: str | None = None
    subjects: list[str] | None = None
    genres: list[str] | None = None
    first_publish_year: int | None = None
    metadata_source: str | None = None
    language: str | None = None
    work_key: str | None = None
    edition_key: str | None = None
    cover_url: str | None = None
    librarything: dict | None = None
    isbn_uid: str | None = None


MANUAL_METADATA_OVERRIDES = {
    "a court of wings and ruin": BookMetadata(
        genres=["fantasy", "romance"],
        metadata_source="manual_override",
    ),
    "a court of mist and fury": BookMetadata(
        genres=["fantasy", "romance"],
        metadata_source="manual_override",
    ),
    "a court of frost and starlight": BookMetadata(
        genres=["fantasy", "romance"],
        metadata_source="manual_override",
    ),
    "night": BookMetadata(
        genres=["memoir", "historical", "nonfiction"],
        metadata_source="manual_override",
    ),
    "check mate": BookMetadata(
        genres=["romance", "young adult"],
        metadata_source="manual_override",
    ),
    "animal farm": BookMetadata(
        genres=["dystopian", "classic", "political fiction"],
        metadata_source="manual_override",
    ),
    "girl in pieces": BookMetadata(
        genres=["young adult", "contemporary"],
        metadata_source="manual_override",
    ),
    "loathe to love you": BookMetadata(
        genres=["romance"],
        metadata_source="manual_override",
    ),
    "normal people": BookMetadata(
        genres=["literary fiction", "romance"],
        metadata_source="manual_override",
    ),
    "the great gatsby": BookMetadata(
        genres=["classic", "literary fiction"],
        metadata_source="manual_override",
    ),
    "the death of ivan ilyich": BookMetadata(
        genres=["classic", "literary fiction", "philosophy"],
        metadata_source="manual_override",
    ),
    "the death of ivan ilych": BookMetadata(
        genres=["classic", "literary fiction", "philosophy"],
        metadata_source="manual_override",
    ),
    "frankenstein": BookMetadata(
        genres=["gothic fiction", "science fiction", "classic"],
        metadata_source="manual_override",
    ),
    "frankenstein the 1818 text": BookMetadata(
        genres=["gothic fiction", "science fiction", "classic"],
        metadata_source="manual_override",
    ),
    "the crucible": BookMetadata(
        genres=["drama", "classic"],
        metadata_source="manual_override",
    ),
    "the glass menagerie": BookMetadata(
        genres=["drama", "classic"],
        metadata_source="manual_override",
    ),
    "the alchemist": BookMetadata(
        genres=["philosophical fiction"],
        metadata_source="manual_override",
    ),
    "fahrenheit 451": BookMetadata(
        genres=["dystopian", "science fiction"],
        metadata_source="manual_override",
    ),
    "nineteen eighty four": BookMetadata(
        genres=["dystopian", "political fiction", "science fiction"],
        metadata_source="manual_override",
    ),
    "love theoretically": BookMetadata(
        genres=["romance"],
        metadata_source="manual_override",
    ),
    "book lovers": BookMetadata(
        genres=["romance", "contemporary romance"],
        metadata_source="manual_override",
    ),
    "deep end": BookMetadata(
        genres=["romance"],
        metadata_source="manual_override",
    ),
    "today tonight tomorrow": BookMetadata(
        genres=["romance", "young adult"],
        metadata_source="manual_override",
    ),
    "we are not free": BookMetadata(
        genres=["historical fiction", "young adult"],
        metadata_source="manual_override",
    ),
    "a midsummer s night dream": BookMetadata(
        genres=["drama", "classic"],
        metadata_source="manual_override",
    ),
}


def looks_like_isbn(value: str | None) -> bool:
    cleaned = re.sub(r"[^0-9Xx]", "", value or "")
    return len(cleaned) in {10, 13}


def normalize_isbn(value: str | None) -> str | None:
    if not looks_like_isbn(value):
        return None
    return re.sub(r"[^0-9Xx]", "", value or "").upper()


def manual_metadata_for_title(title: str | None) -> BookMetadata | None:
    key = re.sub(r"[^a-z0-9\s]", " ", (title or "").lower())
    key = re.sub(r"\s+", " ", key).strip()
    return MANUAL_METADATA_OVERRIDES.get(key)


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
            or metadata.description
            or metadata.subjects
            or metadata.genres
            or metadata.first_publish_year
            or metadata.language
            or metadata.work_key
            or metadata.edition_key
            or metadata.cover_url
            or metadata.isbn_uid
        )
    )


def merge_book_metadata(
    base: BookMetadata,
    next_metadata: BookMetadata | None,
    *,
    prefer_incoming: frozenset[str] = frozenset(),
) -> BookMetadata:
    if next_metadata is None:
        return base
    return BookMetadata(
        **merge_metadata_records(
            base.__dict__,
            next_metadata.__dict__,
            list_fields={"subjects", "genres"},
            prefer_incoming=prefer_incoming,
        )
    )


# Compatibility for internal callers while merge logic lives in one utility.
_merge_metadata = merge_book_metadata


def _genres_need_fallback(genres: list[str] | None) -> bool:
    if not genres:
        return True
    if filter_specific_genres(genres):
        return False
    return len(clean_reader_tags(genres, max_tags=MAX_GENRES_PER_BOOK)) == 0


def _merge_goodreads_fallback(base: BookMetadata, goodreads: BookMetadata | None) -> BookMetadata:
    if goodreads is None:
        return base
    description = base.description or goodreads.description
    if _genres_need_fallback(base.genres) and goodreads.genres:
        genres = goodreads.genres[:MAX_GENRES_PER_BOOK]
    else:
        genres = base.genres or goodreads.genres
    return BookMetadata(
        title=base.title or goodreads.title,
        authors=base.authors or goodreads.authors,
        total_pages=base.total_pages or goodreads.total_pages,
        description=description,
        subjects=base.subjects or goodreads.subjects,
        genres=genres,
        first_publish_year=base.first_publish_year or goodreads.first_publish_year,
        metadata_source=base.metadata_source or goodreads.metadata_source,
        language=base.language or goodreads.language,
        work_key=base.work_key or goodreads.work_key,
        edition_key=base.edition_key or goodreads.edition_key,
        cover_url=base.cover_url or goodreads.cover_url,
        librarything=base.librarything or goodreads.librarything,
        isbn_uid=base.isbn_uid or goodreads.isbn_uid,
    )


def _merge_manual_override(base: BookMetadata, override: BookMetadata | None) -> BookMetadata:
    if override is None:
        return base
    return BookMetadata(
        title=base.title or override.title,
        authors=base.authors or override.authors,
        total_pages=base.total_pages or override.total_pages,
        description=base.description or override.description,
        subjects=base.subjects or override.subjects,
        genres=override.genres or base.genres,
        first_publish_year=base.first_publish_year or override.first_publish_year,
        metadata_source=override.metadata_source or base.metadata_source,
        language=base.language or override.language,
        work_key=base.work_key or override.work_key,
        edition_key=base.edition_key or override.edition_key,
        cover_url=base.cover_url or override.cover_url,
        librarything=base.librarything or override.librarything,
        isbn_uid=base.isbn_uid or override.isbn_uid,
    )


def _enrich_with_librarything(
    metadata: BookMetadata,
    *,
    title: str,
    isbn: str | None,
) -> BookMetadata:
    """Attach optional edition/work identifiers without changing primary metadata."""
    try:
        related_isbns = librarything.fetch_related_isbns(isbn) if isbn else []
        work = librarything.fetch_work_by_title(title) if title else None
    except Exception as exc:  # Third-party enrichment must never affect callers.
        logger.warning("LibraryThing enrichment failed for %r: %s", title or isbn, exc)
        return metadata

    if work:
        related_isbns.extend(work.get("related_isbns") or [])
    unique_isbns = list(dict.fromkeys(value for value in related_isbns if value))
    work_url = work.get("work_url") if work else None
    if not unique_isbns and not work_url:
        return metadata
    return BookMetadata(
        **{
            **metadata.__dict__,
            "librarything": {
                "related_isbns": unique_isbns,
                "work_url": work_url,
                "enriched_at": datetime.now(timezone.utc).isoformat(),
            },
        }
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


def parse_open_library_description(value: object) -> str | None:
    if isinstance(value, str):
        cleaned = value.strip()
        return cleaned or None
    if isinstance(value, dict):
        nested = value.get("value")
        return parse_open_library_description(nested)
    return None


def _first_publish_year(value: object) -> int | None:
    if isinstance(value, int) and value > 0:
        return value
    if isinstance(value, str) and value.strip().isdigit():
        parsed = int(value.strip())
        return parsed if parsed > 0 else None
    return None


def _open_library_cover_url(payload: dict) -> str | None:
    covers = payload.get("covers")
    if isinstance(covers, list):
        for cover_id in covers:
            if isinstance(cover_id, int) and cover_id > 0:
                return f"https://covers.openlibrary.org/b/id/{cover_id}-L.jpg?default=false"
    cover_id = payload.get("cover_i")
    if isinstance(cover_id, int) and cover_id > 0:
        return f"https://covers.openlibrary.org/b/id/{cover_id}-L.jpg?default=false"
    return None


def _google_books_cover_url(image_links: object) -> str | None:
    if not isinstance(image_links, dict):
        return None
    for key in ("thumbnail", "smallThumbnail"):
        value = image_links.get(key)
        if isinstance(value, str) and value.strip():
            url = value.strip()
            return f"https://{url[7:]}" if url.startswith("http://") else url
    return None


def _metadata_from_open_library_payload(payload: dict, *, edition_key: str | None = None) -> BookMetadata:
    subjects = filter_specific_subjects(payload.get("subjects") or payload.get("subject"))
    genres = normalize_genre_list(payload.get("genres")) or subjects_to_genres(subjects)
    return BookMetadata(
        title=payload.get("title") if isinstance(payload.get("title"), str) else None,
        authors=_authors_from_open_library_doc(payload),
        total_pages=_positive_int(payload.get("number_of_pages")),
        description=parse_open_library_description(payload.get("description")),
        subjects=subjects or None,
        genres=genres or None,
        first_publish_year=_first_publish_year(payload.get("first_publish_year")),
        metadata_source="open_library",
        language=_language_from_open_library(payload.get("languages") or payload.get("language")),
        work_key=_first_key(payload.get("works") or payload.get("key")),
        edition_key=edition_key or _first_key(payload.get("edition_key") or payload.get("key")),
        cover_url=_open_library_cover_url(payload),
    )


def _isbn_from_google_identifiers(value: object) -> str | None:
    if not isinstance(value, list):
        return None
    normalized: list[tuple[str, str]] = []
    for identifier in value:
        if not isinstance(identifier, dict):
            continue
        isbn = normalize_isbn(identifier.get("identifier"))
        if isbn:
            normalized.append((str(identifier.get("type") or ""), isbn))
    for preferred_type in ("ISBN_13", "ISBN_10"):
        for identifier_type, isbn in normalized:
            if identifier_type == preferred_type:
                return isbn
    return normalized[0][1] if normalized else None


def _metadata_from_google_volume(info: dict) -> BookMetadata:
    authors = info.get("authors")
    return BookMetadata(
        title=info.get("title") if isinstance(info.get("title"), str) else None,
        authors=", ".join(a.strip() for a in authors if isinstance(a, str) and a.strip())
        if isinstance(authors, list)
        else None,
        total_pages=_positive_int(info.get("pageCount")),
        description=info.get("description") if isinstance(info.get("description"), str) else None,
        subjects=filter_specific_subjects(info.get("categories")) or None,
        genres=normalize_genre_list(info.get("categories")) or None,
        first_publish_year=_first_publish_year(str(info.get("publishedDate") or "")[:4]),
        language=normalize_language(info.get("language")) or None,
        metadata_source="google_books",
        cover_url=_google_books_cover_url(info.get("imageLinks")),
        isbn_uid=_isbn_from_google_identifiers(info.get("industryIdentifiers")),
    )


def _lookup_open_library_work(work_key: str | None) -> BookMetadata | None:
    if not work_key:
        return None
    key = work_key.strip().removeprefix("/works/")
    if not key:
        return None
    try:
        response = httpx.get(
            f"https://openlibrary.org/works/{key}.json",
            timeout=OPEN_LIBRARY_TIMEOUT_SECONDS,
            follow_redirects=True,
        )
        response.raise_for_status()
        payload = response.json()
    except httpx.TimeoutException as exc:
        logger.warning("Open Library work lookup timed out for %r: %s", work_key, exc)
        raise OpenLibraryTimeout(str(exc)) from exc
    except (httpx.HTTPError, ValueError) as exc:
        logger.warning("Open Library work lookup failed for %r: %s", work_key, exc)
        return None

    if not isinstance(payload, dict):
        logger.warning("Open Library work lookup returned malformed payload for %r", work_key)
        return None
    metadata = _metadata_from_open_library_payload(payload)
    return metadata if _metadata_has_value(metadata) else None


def lookup_google_books_by_isbn(isbn: str) -> BookMetadata | None:
    try:
        response = httpx.get(
            "https://www.googleapis.com/books/v1/volumes",
            params={"q": f"isbn:{isbn}"},
            timeout=GOOGLE_BOOKS_TIMEOUT_SECONDS,
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
        metadata = _metadata_from_google_volume(info)
        if _metadata_has_value(metadata):
            return metadata

    logger.warning("Google Books ISBN lookup found no metadata for %r", isbn)
    return None


def lookup_google_books_by_title(title: str, author: str | None = None) -> BookMetadata | None:
    query = f'intitle:"{title}"'
    if author:
        query += f' inauthor:"{author}"'
    try:
        response = httpx.get(
            "https://www.googleapis.com/books/v1/volumes",
            params={"q": query, "maxResults": 5},
            timeout=GOOGLE_BOOKS_TIMEOUT_SECONDS,
        )
        response.raise_for_status()
        payload = response.json()
    except httpx.HTTPStatusError as exc:
        if exc.response.status_code == 429:
            raise GoogleBooksRateLimited(str(exc)) from exc
        logger.warning("Google Books title lookup failed for %r: %s", title, exc)
        return None
    except (httpx.HTTPError, ValueError) as exc:
        logger.warning("Google Books title lookup failed for %r: %s", title, exc)
        return None

    items = payload.get("items", []) if isinstance(payload, dict) else []
    for item in items if isinstance(items, list) else []:
        info = item.get("volumeInfo") if isinstance(item, dict) else None
        if isinstance(info, dict):
            metadata = _metadata_from_google_volume(info)
            if _metadata_has_value(metadata):
                return metadata
    return None


def lookup_open_library_by_isbn(isbn: str) -> BookMetadata | None:
    try:
        response = httpx.get(
            f"https://openlibrary.org/isbn/{isbn}.json",
            timeout=OPEN_LIBRARY_TIMEOUT_SECONDS,
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
    if metadata.work_key:
        try:
            metadata = _merge_metadata(metadata, _lookup_open_library_work(metadata.work_key))
        except OpenLibraryTimeout:
            logger.warning(
                "Persisting partial Open Library ISBN metadata after work timeout for %r",
                isbn,
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
                "fields": "title,author_name,subject,language,key,first_publish_year",
            },
            timeout=OPEN_LIBRARY_TIMEOUT_SECONDS,
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
        subjects = filter_specific_subjects(doc.get("subject"))
        work_key = doc.get("key") if isinstance(doc.get("key"), str) else None
        edition_entries: list[dict] = []
        edition_lookup_failed = False
        if work_key:
            key = work_key.strip().removeprefix("/works/")
            try:
                editions_response = httpx.get(
                    f"https://openlibrary.org/works/{key}/editions.json",
                    params={"limit": 100},
                    timeout=OPEN_LIBRARY_TIMEOUT_SECONDS,
                    follow_redirects=True,
                )
                editions_response.raise_for_status()
                editions_payload = editions_response.json()
                entries = editions_payload.get("entries", []) if isinstance(editions_payload, dict) else []
                edition_entries = [entry for entry in entries if isinstance(entry, dict)] if isinstance(entries, list) else []
            except (httpx.HTTPError, ValueError) as exc:
                edition_lookup_failed = True
                logger.warning("Open Library edition selection lookup failed for %r: %s", title, exc)
        selected_edition = select_best_open_library_edition(
            edition_entries,
            query=f"{title} {author or ''}".strip(),
            displayed_title=str(doc.get("title") or title),
            author_work_match=bool(_authors_from_open_library_doc(doc)),
        )
        selected_fields = edition_fields(selected_edition)
        metadata = BookMetadata(
            title=doc.get("title") if isinstance(doc.get("title"), str) else None,
            authors=_authors_from_open_library_doc(doc),
            total_pages=_positive_int(selected_fields["total_pages"]),
            subjects=subjects or None,
            genres=subjects_to_genres(subjects) or None,
            first_publish_year=_first_publish_year(doc.get("first_publish_year")),
            metadata_source="open_library",
            language=normalize_values(doc.get("language"), normalize_language)[0]
            if normalize_values(doc.get("language"), normalize_language)
            else None,
            work_key=work_key,
            edition_key=selected_fields["edition_key"],
            cover_url=selected_fields["cover_url"],
            isbn_uid=normalize_isbn(selected_fields["isbn_uid"]),
        )
        if metadata.work_key and not edition_lookup_failed:
            try:
                work_metadata = _lookup_open_library_work(metadata.work_key)
                if work_metadata:
                    # Work descriptions/subjects may fill gaps, but edition-bound
                    # values must remain exclusively from the selected edition.
                    work_metadata = BookMetadata(
                        **{
                            **work_metadata.__dict__,
                            "cover_url": None,
                            "total_pages": None,
                            "edition_key": None,
                            "isbn_uid": None,
                        }
                    )
                metadata = _merge_metadata(metadata, work_metadata)
            except OpenLibraryTimeout:
                logger.warning(
                    "Persisting partial Open Library search metadata after work timeout for %r",
                    query,
                )
        if _metadata_has_value(metadata):
            return metadata

    logger.warning("Open Library title lookup found no metadata for %r", query)
    return None


def lookup_book_cover(
    title: str | None,
    author: str | None = None,
    isbn_uid: str | None = None,
) -> BookMetadata | None:
    """Resolve only cover metadata, avoiding work-detail calls used by full enrichment."""
    isbn = normalize_isbn(isbn_uid)
    if isbn:
        try:
            response = httpx.get(
                f"https://openlibrary.org/isbn/{isbn}.json",
                timeout=OPEN_LIBRARY_TIMEOUT_SECONDS,
                follow_redirects=True,
            )
            response.raise_for_status()
            payload = response.json()
            cover_url = _open_library_cover_url(payload) if isinstance(payload, dict) else None
            if cover_url:
                return BookMetadata(cover_url=cover_url, metadata_source="open_library")
        except (httpx.HTTPError, ValueError) as exc:
            logger.warning("Open Library cover ISBN lookup failed for %r: %s", isbn, exc)

    clean_title = (title or "").strip()
    if clean_title:
        try:
            response = httpx.get(
                "https://openlibrary.org/search.json",
                params={
                    "q": f"{clean_title} {author or ''}".strip(),
                    "limit": 5,
                    "fields": "cover_i",
                },
                timeout=OPEN_LIBRARY_TIMEOUT_SECONDS,
            )
            response.raise_for_status()
            payload = response.json()
            docs = payload.get("docs", []) if isinstance(payload, dict) else []
            for doc in docs if isinstance(docs, list) else []:
                cover_url = _open_library_cover_url(doc) if isinstance(doc, dict) else None
                if cover_url:
                    return BookMetadata(cover_url=cover_url, metadata_source="open_library")
        except (httpx.HTTPError, ValueError) as exc:
            logger.warning("Open Library cover title lookup failed for %r: %s", clean_title, exc)

    if isbn:
        try:
            google_metadata = lookup_google_books_by_isbn(isbn)
            if google_metadata and google_metadata.cover_url:
                return BookMetadata(
                    cover_url=google_metadata.cover_url,
                    metadata_source="google_books",
                )
        except GoogleBooksRateLimited as exc:
            logger.warning("Google Books cover lookup rate limited for %r: %s", isbn, exc)
    return None


def lookup_book_metadata(
    title: str | None,
    author: str | None = None,
    isbn_uid: str | None = None,
) -> BookMetadata | None:
    metadata = BookMetadata()
    clean_title = (title or "").strip()
    manual_override = manual_metadata_for_title(clean_title)
    isbn = normalize_isbn(isbn_uid)

    # Open Library owns bibliographic/work priority. Use its ISBN path when
    # possible and its title path as a fallback within the same provider.
    open_library_metadata = None
    if isbn:
        try:
            open_library_metadata = lookup_open_library_by_isbn(isbn)
        except OpenLibraryTimeout:
            pass
    if not isbn and open_library_metadata is None and clean_title:
        try:
            open_library_metadata = lookup_open_library_by_title(clean_title, author)
        except OpenLibraryTimeout:
            pass
    metadata = merge_book_metadata(metadata, open_library_metadata)

    # Google is always queried after Open Library and is authoritative for
    # descriptions/page counts when it returns non-empty values.
    google_metadata = None
    if isbn:
        try:
            google_metadata = lookup_google_books_by_isbn(isbn)
        except GoogleBooksRateLimited:
            pass
    if not isbn and google_metadata is None and clean_title:
        try:
            google_metadata = lookup_google_books_by_title(clean_title, author)
        except GoogleBooksRateLimited:
            pass
    metadata = merge_book_metadata(
        metadata,
        google_metadata,
        prefer_incoming=frozenset({"description", "total_pages"}),
    )

    if isbn and _metadata_has_value(metadata) and not metadata.isbn_uid:
        metadata = BookMetadata(**{**metadata.__dict__, "isbn_uid": isbn})

    # LibraryThing is the final remote provider. It contributes only work/edition
    # identifiers; local datasets and manual overrides still fill content gaps.
    metadata = _enrich_with_librarything(metadata, title=clean_title, isbn=isbn)

    goodreads = lookup_goodreads_metadata(clean_title, author)
    if goodreads is not None and (goodreads.description or goodreads.genres):
        metadata = _merge_goodreads_fallback(
            metadata,
            BookMetadata(
                description=goodreads.description,
                genres=goodreads.genres[:MAX_GENRES_PER_BOOK] if goodreads.genres else None,
                metadata_source="goodreads_kaggle",
            ),
        )

    metadata = _merge_manual_override(metadata, manual_override)

    return metadata if (_metadata_has_value(metadata) or metadata.librarything) else None


def lookup_total_pages(title: str, author: str | None = None) -> int | None:
    query = f"{title} {author or ''}".strip()

    try:
        response = httpx.get(
            "https://openlibrary.org/search.json",
            params={"q": query, "limit": 5, "fields": "title,author_name,number_of_pages_median"},
            timeout=OPEN_LIBRARY_TIMEOUT_SECONDS,
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
            timeout=OPEN_LIBRARY_TIMEOUT_SECONDS,
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
