import csv
import logging
import uuid
from datetime import date, datetime
from io import StringIO
from uuid import UUID

from fastapi import HTTPException
from sqlalchemy.orm import Session

from backend.repository.postgres_books_repository import (
    create_book,
    delete_book,
    get_all_books,
    get_book_by_isbn_uid,
    update_book,
)
from backend.services.page_lookup import (
    BookMetadata,
    GoogleBooksRateLimited,
    OpenLibraryTimeout,
    lookup_google_books_by_isbn,
    lookup_open_library_by_isbn,
    lookup_open_library_by_title,
    normalize_isbn,
)
from backend.services.metadata_normalization import normalize_language
from backend.services.status import database_status_from_normalized, normalize_status


logger = logging.getLogger(__name__)

MAX_ENRICH_LOOKUPS_PER_IMPORT = 10
MAX_ENRICH_FAILURES_PER_IMPORT = 3
MAX_GOOGLE_429_PER_IMPORT = 1
MAX_OPEN_LIBRARY_TIMEOUTS_PER_IMPORT = 2

# Backward-compatible alias for older tests/imports.
MAX_IMPORT_ENRICHMENT_LOOKUPS = MAX_ENRICH_LOOKUPS_PER_IMPORT


def book_to_dict(book):
    return {
        "Title": book.title,
        "Authors": book.authors,
        "ISBN/UID": book.isbn_uid,
        "Read Status": book.read_status,
        "Star Rating": book.star_rating,
        "Last Date Read": book.last_date_read.isoformat()
        if book.last_date_read
        else None,
        "Start Date": book.start_date.isoformat() if book.start_date else None,
        "End Date": book.end_date.isoformat() if book.end_date else None,
        "start_date": book.start_date.isoformat() if book.start_date else None,
        "end_date": book.end_date.isoformat() if book.end_date else None,
        "Progress (%)": book.progress_percent,
        "Pages Read": book.pages_read,
        "Total Pages": book.total_pages,
        "Subjects": book.subjects,
        "Genres": book.genres,
        "Language": book.language,
        "Work Key": book.work_key,
        "Edition Key": book.edition_key,
        "page_count_checked": book.page_count_checked,
        "page_count_source": book.page_count_source,
    }


def parse_date_or_today(date_str):
    if isinstance(date_str, date):
        return date_str

    if date_str:
        try:
            return date.fromisoformat(str(date_str))
        except ValueError:
            pass

    return date.today()


def parse_import_finish_date(value) -> date | None:
    return parse_reading_date(value, field_name="Last Date Read")


def parse_reading_date(value, *, field_name: str) -> date | None:
    if value is None:
        return None
    if isinstance(value, date):
        return value

    raw = str(value).strip()
    if not raw:
        return None

    for fmt in ("%Y-%m-%d", "%Y/%m/%d", "%m/%d/%Y"):
        try:
            return datetime.strptime(raw, fmt).date()
        except ValueError:
            continue

    slash_parts = raw.split("/")
    if len(slash_parts) == 3 and all(part.isdigit() for part in slash_parts):
        first, second, year = (int(part) for part in slash_parts)
        if first > 12 and 1 <= second <= 12:
            try:
                return date(year, second, first)
            except ValueError:
                pass

    logger.warning("Could not parse imported %s value %r", field_name, raw)
    return None


def _validate_date_range(start: date | None, end: date | None) -> None:
    if start is not None and end is not None and start > end:
        raise HTTPException(status_code=400, detail="start_date cannot be after end_date")


def get_books_service(db: Session, user_id: UUID, page: int, limit: int):
    logger.info(
        "GET /books before query user_id=%s page=%s limit=%s",
        user_id,
        page,
        limit,
    )
    books = get_all_books(db, user_id)
    logger.info("GET /books after query user_id=%s rows=%s", user_id, len(books))
    total = len(books)
    start = (page - 1) * limit

    return {
        "page": page,
        "limit": limit,
        "total": total,
        "results": [book_to_dict(book) for book in books[start : start + limit]],
    }


def get_book_by_id_service(db: Session, book_id: str, user_id: UUID):
    book = get_book_by_isbn_uid(db, book_id, user_id)

    if book is None:
        raise HTTPException(status_code=404, detail="Book not found")

    return book_to_dict(book)


def export_library_csv(db: Session, user_id: UUID) -> str:
    books = get_all_books(db, user_id)

    fieldnames = [
        "Title",
        "Authors",
        "ISBN/UID",
        "Read Status",
        "Star Rating",
        "Last Date Read",
        "Start Date",
        "End Date",
        "Progress (%)",
        "Pages Read",
        "Total Pages",
    ]

    output = StringIO()
    writer = csv.DictWriter(output, fieldnames=fieldnames, extrasaction="ignore")
    writer.writeheader()

    for book in books:
        writer.writerow(book_to_dict(book))

    return output.getvalue()


def add_book_service(db: Session, book, user_id: UUID):
    start_date = parse_reading_date(getattr(book, "start_date", None), field_name="Start Date")
    end_date = parse_reading_date(getattr(book, "end_date", None), field_name="End Date")
    _validate_date_range(start_date, end_date)
    create_book(
        db,
        {
            "title": book.title,
            "authors": book.author,
            "isbn_uid": f"uid-{uuid.uuid4()}",
            "read_status": "to-read",
            "star_rating": None,
            "last_date_read": None,
            "start_date": start_date,
            "end_date": end_date,
            "progress_percent": 0,
            "pages_read": 0,
            "total_pages": book.total_pages,
        },
        user_id,
    )

    return {"message": "Book added"}


def _usable_import_author(author: str | None) -> str | None:
    cleaned = (author or "").strip()
    if not cleaned or cleaned.lower() == "unknown":
        return None
    return cleaned


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


def _metadata_update_fields(metadata: BookMetadata | None) -> dict:
    if metadata is None:
        return {}
    data = {}
    if metadata.subjects:
        data["subjects"] = metadata.subjects
    if metadata.genres:
        data["genres"] = metadata.genres
    elif metadata.subjects:
        data["genres"] = metadata.subjects
    if metadata.language:
        data["language"] = normalize_language(metadata.language)
    if metadata.work_key:
        data["work_key"] = metadata.work_key
    if metadata.edition_key:
        data["edition_key"] = metadata.edition_key
    return data


def _new_enrichment_state() -> dict[str, int | bool]:
    return {
        "lookups": 0,
        "failures": 0,
        "google_429s": 0,
        "open_library_timeouts": 0,
        "google_enabled": True,
        "open_library_enabled": True,
    }


def _enrichment_budget_available(state: dict[str, int | bool]) -> bool:
    return (
        int(state["lookups"]) < MAX_ENRICH_LOOKUPS_PER_IMPORT
        and int(state["failures"]) < MAX_ENRICH_FAILURES_PER_IMPORT
    )


def _record_enrichment_failure(state: dict[str, int | bool]) -> None:
    state["failures"] = int(state["failures"]) + 1
    if int(state["failures"]) >= MAX_ENRICH_FAILURES_PER_IMPORT:
        state["google_enabled"] = False
        state["open_library_enabled"] = False


def _record_google_429(state: dict[str, int | bool]) -> None:
    state["google_429s"] = int(state["google_429s"]) + 1
    if int(state["google_429s"]) >= MAX_GOOGLE_429_PER_IMPORT:
        state["google_enabled"] = False


def _record_open_library_timeout(state: dict[str, int | bool]) -> None:
    state["open_library_timeouts"] = int(state["open_library_timeouts"]) + 1
    if int(state["open_library_timeouts"]) >= MAX_OPEN_LIBRARY_TIMEOUTS_PER_IMPORT:
        state["open_library_enabled"] = False


def _try_google_isbn_for_import(
    isbn: str,
    state: dict[str, int | bool],
) -> BookMetadata | None:
    if not state["google_enabled"] or not _enrichment_budget_available(state):
        return None

    state["lookups"] = int(state["lookups"]) + 1
    try:
        metadata = lookup_google_books_by_isbn(isbn)
    except GoogleBooksRateLimited:
        _record_google_429(state)
        _record_enrichment_failure(state)
        return None
    except Exception as exc:
        logger.warning("Google Books import lookup crashed for %r: %s", isbn, exc, exc_info=True)
        _record_enrichment_failure(state)
        return None

    if metadata is None:
        _record_enrichment_failure(state)
    return metadata


def _try_open_library_isbn_for_import(
    isbn: str,
    state: dict[str, int | bool],
) -> BookMetadata | None:
    if not state["open_library_enabled"] or not _enrichment_budget_available(state):
        return None

    state["lookups"] = int(state["lookups"]) + 1
    try:
        metadata = lookup_open_library_by_isbn(isbn)
    except OpenLibraryTimeout:
        _record_open_library_timeout(state)
        _record_enrichment_failure(state)
        return None
    except Exception as exc:
        logger.warning("Open Library ISBN import lookup crashed for %r: %s", isbn, exc, exc_info=True)
        _record_enrichment_failure(state)
        return None

    if metadata is None:
        _record_enrichment_failure(state)
    return metadata


def _try_open_library_title_for_import(
    title: str,
    author: str | None,
    state: dict[str, int | bool],
) -> BookMetadata | None:
    if not state["open_library_enabled"] or not _enrichment_budget_available(state):
        return None

    state["lookups"] = int(state["lookups"]) + 1
    try:
        metadata = lookup_open_library_by_title(title, author)
    except OpenLibraryTimeout:
        _record_open_library_timeout(state)
        _record_enrichment_failure(state)
        return None
    except Exception as exc:
        logger.warning("Open Library title import lookup crashed for %r: %s", title, exc, exc_info=True)
        _record_enrichment_failure(state)
        return None

    if metadata is None:
        _record_enrichment_failure(state)
    return metadata


def _lookup_metadata_for_import(
    title: str,
    author: str | None,
    isbn_uid: str | None,
    state: dict[str, int | bool],
) -> tuple[BookMetadata | None, bool]:
    metadata = BookMetadata()
    attempted = False
    isbn = normalize_isbn(isbn_uid)

    if isbn:
        lookups_before = int(state["lookups"])
        google_metadata = _try_google_isbn_for_import(isbn, state)
        attempted = attempted or int(state["lookups"]) > lookups_before
        metadata = _merge_metadata(metadata, google_metadata)
        if metadata.total_pages and (metadata.authors or author):
            return metadata, attempted

        lookups_before = int(state["lookups"])
        open_library_metadata = _try_open_library_isbn_for_import(isbn, state)
        attempted = attempted or int(state["lookups"]) > lookups_before
        metadata = _merge_metadata(metadata, open_library_metadata)
        return (metadata if _metadata_has_value(metadata) else None), attempted

    lookups_before = int(state["lookups"])
    title_metadata = _try_open_library_title_for_import(title, author, state)
    attempted = attempted or int(state["lookups"]) > lookups_before
    metadata = _merge_metadata(metadata, title_metadata)

    return (metadata if _metadata_has_value(metadata) else None), attempted


def _status_patch_value(body) -> str | None:
    return getattr(body, "status", None) or getattr(body, "read_status", None)


def _apply_status_and_progress(
    update_data: dict,
    status: str | None,
    pages_read: int | None,
    total_pages: int | None,
    current_pages_read: int | None,
):
    if status is None and pages_read is None:
        return

    next_pages_read = int(pages_read if pages_read is not None else current_pages_read or 0)
    if next_pages_read < 0:
        raise HTTPException(status_code=400, detail="pages_read cannot be negative")

    total_pages_int = int(total_pages) if total_pages is not None else None
    if total_pages_int is not None and next_pages_read > total_pages_int:
        raise HTTPException(status_code=400, detail="pages_read cannot exceed total_pages")

    if status == "not_started":
        update_data.update({"read_status": "to-read", "pages_read": 0, "progress_percent": 0})
        return

    if status == "completed":
        if total_pages_int is not None:
            next_pages_read = total_pages_int
        update_data.update(
            {
                "read_status": "read",
                "pages_read": next_pages_read,
                "progress_percent": 100,
                "last_date_read": parse_date_or_today(None),
            }
        )
        return

    if status == "reading":
        update_data.update(
            {
                "read_status": "to-read",
                "pages_read": next_pages_read,
                "progress_percent": round((next_pages_read / total_pages_int) * 100, 2)
                if total_pages_int
                else 0,
            }
        )
        return

    if status == "dnf":
        update_data.update(
            {
                "read_status": "dnf",
                "pages_read": next_pages_read,
                "progress_percent": round((next_pages_read / total_pages_int) * 100, 2)
                if total_pages_int
                else 0,
                "last_date_read": parse_date_or_today(None),
            }
        )
        return

    if status is None:
        update_data.update(
            {
                "pages_read": next_pages_read,
                "progress_percent": round((next_pages_read / total_pages_int) * 100, 2)
                if total_pages_int
                else 0,
            }
        )
        return

    raise HTTPException(status_code=400, detail="Invalid status")


def import_books_service(db: Session, data, user_id: UUID):
    books = get_all_books(db, user_id)
    existing_titles = {book.title for book in books}
    existing_isbn_uids = {book.isbn_uid for book in books}

    imported = 0
    skipped = 0
    enriched = 0
    enrichment_skipped = 0
    enrichment_state = _new_enrichment_state()

    for book in data.books:
        title = (book.title or "").strip()
        isbn_uid = (getattr(book, "isbn_uid", None) or "").strip() or None

        if not title or title in existing_titles or (isbn_uid is not None and isbn_uid in existing_isbn_uids):
            skipped += 1
            continue

        author = _usable_import_author(book.author)
        pages_read = int(book.pages_read or 0)
        progress_percent = float(book.progress_percent or 0)
        normalized_status = normalize_status(
            book.read_status,
            progress_percent=progress_percent,
            pages_read=pages_read,
        )
        total_pages = book.total_pages
        stored_author = author
        page_count_attempted = False
        metadata = None
        imported_finish_date = parse_import_finish_date(getattr(book, "last_date_read", None))
        imported_start_date = parse_reading_date(getattr(book, "start_date", None), field_name="Start Date")
        imported_end_date = parse_reading_date(getattr(book, "end_date", None), field_name="End Date")
        if imported_end_date is None:
            imported_end_date = imported_finish_date
        _validate_date_range(imported_start_date, imported_end_date)

        if total_pages is None or stored_author is None:
            if _enrichment_budget_available(enrichment_state):
                metadata, attempted = _lookup_metadata_for_import(
                    title,
                    author,
                    isbn_uid,
                    enrichment_state,
                )
                page_count_attempted = attempted and total_pages is None
                if metadata is not None:
                    if total_pages is None:
                        total_pages = getattr(metadata, "total_pages", None)
                    if stored_author is None:
                        stored_author = _usable_import_author(getattr(metadata, "authors", None))
                if metadata is not None and (
                    getattr(metadata, "total_pages", None) is not None
                    or getattr(metadata, "authors", None) is not None
                ):
                    enriched += 1
                if not attempted:
                    enrichment_skipped += 1
            else:
                enrichment_skipped += 1

        stored_author = stored_author or "Unknown"

        if normalized_status == "completed":
            progress_percent = 100
            if total_pages is not None:
                pages_read = int(total_pages)
        elif normalized_status == "not_started":
            pages_read = 0
            progress_percent = 0
        elif normalized_status == "reading" and total_pages is not None and pages_read > 0:
            pages_read = min(pages_read, int(total_pages))
            progress_percent = round((pages_read / int(total_pages)) * 100, 2)

        create_book(
            db,
            {
                "title": title,
                "authors": stored_author,
                "isbn_uid": isbn_uid or f"uid-{uuid.uuid4()}",
                "read_status": database_status_from_normalized(normalized_status),
                "star_rating": None,
                "last_date_read": imported_end_date if normalized_status == "completed" else None,
                "start_date": imported_start_date,
                "end_date": imported_end_date if normalized_status == "completed" else None,
                "progress_percent": progress_percent,
                "pages_read": pages_read,
                "total_pages": total_pages,
                "page_count_checked": total_pages is not None or page_count_attempted,
                **_metadata_update_fields(metadata),
            },
            user_id,
        )

        existing_titles.add(title)
        if isbn_uid is not None:
            existing_isbn_uids.add(isbn_uid)
        imported += 1

    return {
        "imported_count": imported,
        "skipped_count": skipped,
        "duplicate_count": skipped,
        "skipped_duplicates": skipped,
        "enriched_count": enriched,
        "enrichment_skipped_count": enrichment_skipped,
        "enrichment_failed_count": int(enrichment_state["failures"]),
    }


def clear_library_service(db: Session, confirm: bool, user_id: UUID):
    if not confirm:
        raise HTTPException(
            status_code=400,
            detail="Confirmation required to clear the library",
        )

    books = get_all_books(db, user_id)
    deleted = len(books)

    for book in books:
        delete_book(db, book.id, user_id)

    return {"message": "Library cleared", "deleted": deleted}


def delete_book_by_id_service(db: Session, book_id: str, user_id: UUID):
    book = get_book_by_isbn_uid(db, book_id, user_id)

    if book is None:
        raise HTTPException(status_code=404, detail="Book not found")

    delete_book(db, book.id, user_id)

    return {"message": "Book deleted"}


def delete_book_by_title_service(db: Session, title: str, user_id: UUID):
    books = get_all_books(db, user_id)

    for book in books:
        if book.title == title:
            delete_book(db, book.id, user_id)
            return {"message": "Book deleted"}

    raise HTTPException(status_code=404, detail="Book not found")


def patch_book_service(db: Session, p, user_id: UUID):
    books = get_all_books(db, user_id)
    book = next((b for b in books if b.title == p.title), None)

    if book is None:
        raise HTTPException(status_code=404, detail="Book not found")

    update_data = {}

    if p.new_title and p.new_title != p.title:
        duplicate = next((b for b in books if b.title == p.new_title), None)

        if duplicate is not None:
            raise HTTPException(status_code=400, detail="Title already exists")

        update_data["title"] = p.new_title

    if p.author is not None:
        update_data["authors"] = p.author.strip() or "Unknown"

    if getattr(p, "isbn_uid", None) is not None:
        next_isbn = p.isbn_uid.strip()
        duplicate = next((b for b in books if b.isbn_uid == next_isbn and b.id != book.id), None)
        if duplicate is not None:
            raise HTTPException(status_code=400, detail="ISBN/UID already exists")
        update_data["isbn_uid"] = next_isbn

    if p.total_pages is not None:
        update_data["total_pages"] = p.total_pages

    next_start_date = book.start_date
    next_end_date = book.end_date
    if getattr(p, "start_date", None) is not None:
        next_start_date = parse_reading_date(p.start_date, field_name="Start Date")
        update_data["start_date"] = next_start_date
    if getattr(p, "end_date", None) is not None:
        next_end_date = parse_reading_date(p.end_date, field_name="End Date")
        update_data["end_date"] = next_end_date
    _validate_date_range(next_start_date, next_end_date)

    if p.move_to:
        move_to = p.move_to.strip().lower()

        if move_to == "want":
            update_data.update(
                {
                    "read_status": "to-read",
                    "progress_percent": 0,
                    "pages_read": 0,
                }
            )

        elif move_to == "reading":
            total_pages = update_data.get("total_pages", book.total_pages)

            if total_pages is None or int(total_pages) <= 0:
                raise HTTPException(
                    status_code=400,
                    detail="Set total pages first",
                )

            total_pages_int = int(total_pages)
            pages_read = max(1, min(int(p.pages_read or 1), total_pages_int))

            update_data.update(
                {
                    "read_status": "to-read",
                    "pages_read": pages_read,
                    "progress_percent": round(
                        (pages_read / total_pages_int) * 100,
                        2,
                    ),
                }
            )

        elif move_to == "read":
            rating = p.rating if p.rating is not None else book.star_rating

            if rating is None or not (1 <= rating <= 5):
                raise HTTPException(
                    status_code=400,
                    detail="Rating 1-5 required",
                )

            total_pages = update_data.get("total_pages", book.total_pages)

            update_data.update(
                {
                    "read_status": "read",
                    "star_rating": rating,
                    "progress_percent": 100,
                    "last_date_read": parse_date_or_today(p.date_read),
                    "end_date": parse_reading_date(p.date_read, field_name="End Date")
                    or date.today(),
                }
            )

            if total_pages is not None:
                update_data["pages_read"] = int(total_pages)

        elif move_to == "dnf":
            update_data.update(
                {
                    "read_status": "dnf",
                    "star_rating": 1,
                    "progress_percent": 0,
                    "pages_read": 0,
                    "last_date_read": parse_date_or_today(p.date_read),
                    "end_date": parse_reading_date(p.date_read, field_name="End Date")
                    or date.today(),
                }
            )

        else:
            raise HTTPException(status_code=400, detail="Invalid move target")

    if _status_patch_value(p) is not None or p.pages_read is not None:
        total_pages = update_data.get("total_pages", book.total_pages)
        _apply_status_and_progress(
            update_data,
            _status_patch_value(p),
            p.pages_read,
            total_pages,
            book.pages_read,
        )

    update_book(db, book.id, update_data, user_id)

    return {"message": "Book updated"}


def patch_book_by_id_service(db: Session, book_id: str, body, user_id: UUID):
    books = get_all_books(db, user_id)
    book = get_book_by_isbn_uid(db, book_id, user_id)

    if book is None:
        raise HTTPException(status_code=404, detail="Book not found")

    update_data = {}
    fields_set = getattr(body, "model_fields_set", set())

    if "title" in fields_set and body.title is not None:
        title = body.title.strip()
        if not title:
            raise HTTPException(status_code=400, detail="Title is required")
        duplicate = next((b for b in books if b.title == title and b.id != book.id), None)
        if duplicate is not None:
            raise HTTPException(status_code=400, detail="Title already exists")
        update_data["title"] = title

    if "author" in fields_set:
        update_data["authors"] = (body.author or "").strip() or "Unknown"

    if "isbn_uid" in fields_set and body.isbn_uid is not None:
        isbn_uid = body.isbn_uid.strip()
        duplicate = next((b for b in books if b.isbn_uid == isbn_uid and b.id != book.id), None)
        if duplicate is not None:
            raise HTTPException(status_code=400, detail="ISBN/UID already exists")
        update_data["isbn_uid"] = isbn_uid

    if "total_pages" in fields_set:
        update_data["total_pages"] = body.total_pages

    next_start_date = book.start_date
    next_end_date = book.end_date
    if "start_date" in fields_set:
        next_start_date = parse_reading_date(body.start_date, field_name="Start Date")
        update_data["start_date"] = next_start_date
    if "end_date" in fields_set:
        next_end_date = parse_reading_date(body.end_date, field_name="End Date")
        update_data["end_date"] = next_end_date
    _validate_date_range(next_start_date, next_end_date)

    total_pages = update_data.get("total_pages", book.total_pages)
    pages_read = body.pages_read if "pages_read" in fields_set else None
    _apply_status_and_progress(
        update_data,
        _status_patch_value(body),
        pages_read,
        total_pages,
        book.pages_read,
    )

    updated = update_book(db, book.id, update_data, user_id)

    return book_to_dict(updated)


def update_book_progress_by_id_service(db: Session, book_id: str, body, user_id: UUID):
    book = get_book_by_isbn_uid(db, book_id, user_id)

    if book is None:
        raise HTTPException(status_code=404, detail="Book not found")

    total_pages = book.total_pages
    total_pages_int = (
        int(total_pages)
        if total_pages is not None and int(total_pages) > 0
        else None
    )
    has_total = total_pages_int is not None

    status = body.status
    pages_read = int(body.pages_read)

    if status in ("reading", "completed") and not has_total:
        raise HTTPException(status_code=400, detail="Set total pages first")

    if has_total and total_pages_int is not None:
        if pages_read > total_pages_int:
            raise HTTPException(
                status_code=400,
                detail="pages_read cannot exceed total_pages",
            )

        if status == "completed" and pages_read != total_pages_int:
            raise HTTPException(
                status_code=400,
                detail="pages_read must equal total_pages when status is completed",
            )

        if pages_read == total_pages_int and status == "reading":
            status = "completed"

    update_data = {}

    if status == "not_started":
        update_data.update(
            {
                "read_status": "to-read",
                "progress_percent": 0,
                "pages_read": 0,
            }
        )

    elif status == "reading":
        progress_pct = (
            round((pages_read / total_pages_int) * 100, 2)
            if total_pages_int
            else 0
        )

        update_data.update(
            {
                "read_status": "to-read",
                "pages_read": pages_read,
                "progress_percent": progress_pct,
                "start_date": book.start_date or date.today(),
            }
        )

    elif status == "completed":
        rating = getattr(body, "rating", None)

        update_data.update(
            {
                "read_status": "read",
                "star_rating": float(rating)
                if rating is not None
                else book.star_rating,
                "progress_percent": 100,
                "pages_read": pages_read,
                "last_date_read": parse_date_or_today(None),
                "start_date": book.start_date,
                "end_date": date.today(),
            }
        )

    elif status == "dnf":
        update_data.update(
            {
                "read_status": "dnf",
                "star_rating": 1,
                "progress_percent": 0,
                "pages_read": pages_read,
                "last_date_read": parse_date_or_today(None),
                "end_date": date.today(),
            }
        )

    else:
        raise HTTPException(status_code=400, detail="Invalid status")

    updated = update_book(db, book.id, update_data, user_id)

    return book_to_dict(updated)
