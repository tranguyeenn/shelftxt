import csv
import logging
import re
import uuid
from datetime import date, datetime, timezone
from io import StringIO
import time
from uuid import UUID

from fastapi import HTTPException
from sqlalchemy.orm import Session

from backend.db.models import Book

from backend.repository.postgres_books_repository import (
    count_books,
    create_book,
    create_books_bulk,
    delete_book,
    delete_books_for_user,
    get_existing_import_keys,
    get_all_books,
    get_book_by_title,
    get_book_by_title_excluding_id,
    get_book_by_isbn_uid,
    get_book_by_isbn_uid_excluding_id,
    get_books_page,
    update_book,
)
from backend.services.page_lookup import (
    BookMetadata,
)
from backend.env import is_local_env
from backend.services.metadata_normalization import normalize_language
from backend.services.metadata_jobs import reset_metadata_progress_if_library_empty
from backend.services.page_count_lookup import (
    MAX_BACKFILL_BOOKS,
    backfill_missing_page_counts,
    lookup_page_count_result,
)
from backend.services.progress import clamp_pages_read, clamp_progress_percent, estimated_pages_read
from backend.services.reading_activity import record_progress_activity
from backend.services.status import database_status_from_normalized, normalize_status


logger = logging.getLogger(__name__)
TRACKING_MODES = {"percentage", "pages"}


def infer_tracking_mode(total_pages: int | None) -> str:
    return "pages" if total_pages is not None else "percentage"


def normalized_tracking_mode(value: str | None, total_pages: int | None) -> str:
    if value is None or str(value).strip() == "":
        return infer_tracking_mode(total_pages)
    mode = str(value).strip().lower()
    if mode not in TRACKING_MODES:
        raise HTTPException(status_code=400, detail="tracking_mode must be percentage or pages")
    return mode


def _log_endpoint_timing(endpoint: str, user_id: UUID, started: float, rows: int) -> None:
    if not is_local_env():
        return

    logger.info(
        "endpoint_timing endpoint=%s user_id=%s duration_ms=%.2f rows=%s external_calls=0",
        endpoint,
        user_id,
        (time.perf_counter() - started) * 1000,
        rows,
    )


def book_to_dict(book):
    progress_percent = clamp_progress_percent(book.progress_percent)
    pages_read = clamp_pages_read(book.pages_read, book.total_pages)
    estimated_pages = estimated_pages_read(progress_percent, book.total_pages)
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
        "Progress (%)": progress_percent,
        "Pages Read": pages_read,
        "estimated_pages_read": estimated_pages,
        "Total Pages": book.total_pages,
        "Tracking Mode": normalized_tracking_mode(book.tracking_mode, book.total_pages),
        "tracking_mode": normalized_tracking_mode(book.tracking_mode, book.total_pages),
        "Description": book.description,
        "Cover URL": book.cover_url,
        "cover_url": book.cover_url,
        "Subjects": book.subjects,
        "Genres": book.genres,
        "First Publish Year": book.first_publish_year,
        "metadata_source": book.metadata_source,
        "metadata_enriched_at": book.metadata_enriched_at.isoformat()
        if book.metadata_enriched_at
        else None,
        "Language": book.language,
        "Work Key": book.work_key,
        "Edition Key": book.edition_key,
        "metadata": book.book_metadata,
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


def parse_dates_read_range(value) -> tuple[date | None, date | None]:
    raw = str(value or "").strip()
    if not raw:
        return None, None

    matches = [
        match.group(0)
        for match in re.finditer(r"\d{4}[/-]\d{2}[/-]\d{2}", raw)
    ]
    if not matches:
        return None, None

    start = parse_reading_date(matches[0], field_name="Dates Read")
    end = parse_reading_date(matches[1], field_name="Dates Read") if len(matches) > 1 else start
    return start, end


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
    started = time.perf_counter()
    total = count_books(db, user_id)
    start = (page - 1) * limit
    books = get_books_page(db, user_id, start, limit)
    _log_endpoint_timing("GET /books", user_id, started, len(books))

    return {
        "page": page,
        "limit": limit,
        "total": total,
        "results": [book_to_dict(book) for book in books],
    }


def get_book_by_id_service(db: Session, book_id: str, user_id: UUID):
    book = get_book_by_isbn_uid(db, book_id, user_id)

    if book is None:
        raise HTTPException(status_code=404, detail="Book not found")

    return book_to_dict(book)


def find_page_count_for_book_service(db: Session, book_id: str, user_id: UUID):
    book = get_book_by_isbn_uid(db, book_id, user_id)
    if book is None:
        raise HTTPException(status_code=404, detail="Book not found")
    if book.total_pages is not None:
        return {
            "found": True,
            "source": book.page_count_source or "existing",
            "book": book_to_dict(book),
        }

    result = lookup_page_count_result(
        book.title,
        book.authors,
        book.isbn_uid,
        book.edition_key,
    )
    update_data = {
        "page_count_checked": True,
        "page_count_source": result.source,
    }
    if result.pages is not None:
        update_data["total_pages"] = result.pages
    updated = update_book(db, book.id, update_data, user_id)
    return {
        "found": result.pages is not None,
        "source": result.source,
        "book": book_to_dict(updated),
    }


def backfill_page_counts_for_user_service(
    db: Session,
    user_id: UUID,
    limit: int = MAX_BACKFILL_BOOKS,
):
    missing_before = (
        db.query(Book)
        .filter(Book.user_id == user_id, Book.total_pages.is_(None))
        .count()
    )
    processed = min(missing_before, limit)
    updated = backfill_missing_page_counts(db, limit=limit, user_id=user_id)
    return {
        "processed": processed,
        "updated": updated,
        "unresolved": processed - updated,
    }


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
        "start_date",
        "end_date",
        "Progress (%)",
        "Pages Read",
        "Total Pages",
        "tracking_mode",
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
    status = getattr(book, "status", "not_started")
    read_status = {
        "not_started": "to-read",
        "reading": "to-read",
        "completed": "read",
        "dnf": "dnf",
    }.get(status, "to-read")
    progress_percent = 100 if status == "completed" else (1 if status == "reading" else 0)
    pages_read = book.total_pages if status == "completed" and book.total_pages else 0
    related_isbns = list(getattr(book, "related_isbns", []) or [])
    librarything_metadata = (
        {
            "librarything": {
                "related_isbns": related_isbns,
                "work_url": None,
                "enriched_at": datetime.now(timezone.utc).isoformat(),
            }
        }
        if related_isbns
        else None
    )
    manual_metadata = {
        key: value
        for key, value in {
            "publisher": getattr(book, "publisher", None),
            "publish_date": getattr(book, "publish_date", None),
            "language": getattr(book, "language", None),
            "edition_type": getattr(book, "edition_type", None),
            "original_title": getattr(book, "original_title", None),
            "notes": getattr(book, "notes", None),
        }.items()
        if value not in (None, "", [])
    }
    book_metadata = librarything_metadata or {}
    if manual_metadata:
        book_metadata["manual"] = manual_metadata
    create_book(
        db,
        {
            "title": book.title,
            "authors": book.author,
            "isbn_uid": getattr(book, "isbn_uid", None) or f"uid-{uuid.uuid4()}",
            "read_status": read_status,
            "star_rating": getattr(book, "star_rating", None) if status == "completed" else None,
            "last_date_read": end_date if status == "completed" else None,
            "start_date": start_date,
            "end_date": end_date,
            "progress_percent": progress_percent,
            "pages_read": pages_read,
            "total_pages": book.total_pages,
            "tracking_mode": normalized_tracking_mode(
                getattr(book, "tracking_mode", None),
                book.total_pages,
            ),
            "page_count_checked": book.total_pages is not None,
            "description": getattr(book, "description", None),
            "cover_url": getattr(book, "cover_url", None),
            "subjects": getattr(book, "subjects", None) or None,
            "genres": getattr(book, "genres", None) or None,
            "first_publish_year": getattr(book, "first_publish_year", None),
            "metadata_source": getattr(book, "metadata_source", None),
            "metadata_enriched_at": datetime.now(timezone.utc)
            if getattr(book, "metadata_source", None)
            else None,
            "work_key": getattr(book, "work_key", None),
            "edition_key": getattr(book, "edition_key", None),
            "language": normalize_language(getattr(book, "language", None)) if getattr(book, "language", None) else None,
            "book_metadata": book_metadata or None,
        },
        user_id,
    )

    return {"message": "Book added"}


def _usable_import_author(author: str | None) -> str | None:
    cleaned = (author or "").strip()
    if not cleaned or cleaned.lower() == "unknown":
        return None
    return cleaned


def _metadata_update_fields(metadata: BookMetadata | None) -> dict:
    if metadata is None:
        return {}
    data = {}
    if metadata.librarything:
        data["book_metadata"] = {"librarything": metadata.librarything}
    if metadata.subjects:
        data["subjects"] = metadata.subjects
    if metadata.genres:
        data["genres"] = metadata.genres
    if metadata.description:
        data["description"] = metadata.description
    if metadata.cover_url:
        data["cover_url"] = metadata.cover_url
    if metadata.first_publish_year:
        data["first_publish_year"] = metadata.first_publish_year
    if metadata.metadata_source:
        data["metadata_source"] = metadata.metadata_source
    if data:
        data["metadata_enriched_at"] = datetime.now(timezone.utc)
    if metadata.language:
        data["language"] = normalize_language(metadata.language)
    if metadata.work_key:
        data["work_key"] = metadata.work_key
    if metadata.edition_key:
        data["edition_key"] = metadata.edition_key
    return data


def _status_patch_value(body) -> str | None:
    return getattr(body, "status", None) or getattr(body, "read_status", None)


def _normalized_status_from_book(book) -> str:
    return normalize_status(
        book.read_status,
        progress_percent=float(book.progress_percent or 0),
        pages_read=int(book.pages_read or 0),
    )


def _apply_status_and_progress(
    update_data: dict,
    status: str | None,
    pages_read: int | None,
    total_pages: int | None,
    current_pages_read: int | None,
    progress_percent: float | None = None,
    current_progress_percent: float | None = None,
    current_status: str = "not_started",
    current_start_date: date | None = None,
    current_end_date: date | None = None,
    current_last_date_read: date | None = None,
    rating: float | None = None,
    current_rating: float | None = None,
):
    next_pages_read = int(pages_read if pages_read is not None else current_pages_read or 0)
    if next_pages_read < 0:
        raise HTTPException(status_code=400, detail="pages_read cannot be negative")

    total_pages_int = int(total_pages) if total_pages is not None else None
    if total_pages_int is not None and next_pages_read > total_pages_int:
        raise HTTPException(status_code=400, detail="pages_read cannot exceed total_pages")

    if status is None and pages_read is None and progress_percent is None:
        return

    next_progress_percent = (
        float(progress_percent)
        if progress_percent is not None
        else float(current_progress_percent or 0)
    )
    if next_progress_percent < 0 or next_progress_percent > 100:
        raise HTTPException(status_code=400, detail="progress_percent must be between 0 and 100")

    if pages_read is not None and total_pages_int is not None and total_pages_int > 0:
        next_progress_percent = round((next_pages_read / total_pages_int) * 100, 2)

    if (
        total_pages_int is not None
        and total_pages_int > 0
        and next_pages_read >= total_pages_int
        and status in (None, "reading")
    ):
        status = "completed"
    if progress_percent is not None and next_progress_percent >= 100 and status in (None, "reading"):
        status = "completed"

    if status == "not_started":
        update_data.update({"read_status": "to-read", "pages_read": 0, "progress_percent": 0})
        return

    if status == "completed":
        if total_pages_int is not None:
            next_pages_read = total_pages_int
        completed_data = {
            "read_status": "read",
            "pages_read": next_pages_read,
            "progress_percent": 100,
            "star_rating": float(rating) if rating is not None else current_rating,
        }
        if current_status != "completed":
            completed_data["last_date_read"] = parse_date_or_today(None)
            completed_data["end_date"] = date.today()
        elif current_last_date_read is not None:
            completed_data["last_date_read"] = current_last_date_read
        if current_end_date is not None:
            completed_data["end_date"] = current_end_date
        update_data.update({key: value for key, value in completed_data.items() if value is not None})
        return

    if status == "reading":
        update_data.update(
            {
                "read_status": "to-read",
                "pages_read": next_pages_read,
                "progress_percent": next_progress_percent,
                "start_date": current_start_date or date.today(),
            }
        )
        return

    if status == "dnf":
        update_data.update(
            {
                "read_status": "dnf",
                "pages_read": next_pages_read,
                "progress_percent": next_progress_percent,
                "star_rating": 1,
                "last_date_read": parse_date_or_today(None),
                "end_date": date.today(),
            }
        )
        return

    if status is None:
        update_data.update(
            {
                "pages_read": next_pages_read,
                "progress_percent": next_progress_percent,
            }
        )
        return

    raise HTTPException(status_code=400, detail="Invalid status")


def import_books_service(db: Session, data, user_id: UUID):
    started = time.perf_counter()
    existing_keys = get_existing_import_keys(db, user_id)
    existing_titles = {title for title, _isbn_uid in existing_keys}
    existing_isbn_uids = {isbn_uid for _title, isbn_uid in existing_keys}

    imported = 0
    skipped = 0
    books_to_create = []
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
        tracking_mode = normalized_tracking_mode(book.tracking_mode, total_pages)
        stored_author = author or "Unknown"
        imported_finish_date = parse_import_finish_date(getattr(book, "last_date_read", None))
        dates_read_start, dates_read_end = parse_dates_read_range(getattr(book, "dates_read", None))
        imported_start_date = parse_reading_date(getattr(book, "start_date", None), field_name="Start Date")
        imported_end_date = parse_reading_date(getattr(book, "end_date", None), field_name="End Date")
        if normalized_status != "not_started" and imported_start_date is None:
            imported_start_date = dates_read_start
        if imported_end_date is None:
            imported_end_date = imported_finish_date
        if normalized_status != "not_started" and imported_end_date is None:
            imported_end_date = dates_read_end
        _validate_date_range(imported_start_date, imported_end_date)

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

        books_to_create.append(
            {
                "title": title,
                "authors": stored_author,
                "isbn_uid": isbn_uid or f"uid-{uuid.uuid4()}",
                "read_status": database_status_from_normalized(normalized_status),
                "star_rating": book.star_rating,
                "last_date_read": imported_end_date if normalized_status == "completed" else None,
                "start_date": imported_start_date,
                "end_date": imported_end_date if normalized_status == "completed" else None,
                "progress_percent": progress_percent,
                "pages_read": pages_read,
                "total_pages": total_pages,
                "tracking_mode": tracking_mode,
                "page_count_checked": total_pages is not None,
            }
        )

        existing_titles.add(title)
        if isbn_uid is not None:
            existing_isbn_uids.add(isbn_uid)
        imported += 1

    create_books_bulk(db, books_to_create, user_id)
    _log_endpoint_timing("POST /books/import", user_id, started, imported + skipped)

    return {
        "imported_count": imported,
        "skipped_count": skipped,
        "duplicate_count": skipped,
        "skipped_duplicates": skipped,
        "enriched_count": 0,
        "enrichment_skipped_count": 0,
        "enrichment_failed_count": 0,
    }


def clear_library_service(db: Session, confirm: bool, user_id: UUID):
    started = time.perf_counter()
    if not confirm:
        raise HTTPException(
            status_code=400,
            detail="Confirmation required to clear the library",
        )

    deleted = delete_books_for_user(db, user_id)
    reset_metadata_progress_if_library_empty(db, user_id)
    _log_endpoint_timing("POST /books/clear", user_id, started, deleted)

    return {"deleted": deleted}


def delete_book_by_id_service(db: Session, book_id: str, user_id: UUID):
    book = get_book_by_isbn_uid(db, book_id, user_id)

    if book is None:
        raise HTTPException(status_code=404, detail="Book not found")

    delete_book(db, book.id, user_id)
    reset_metadata_progress_if_library_empty(db, user_id)

    return {"message": "Book deleted"}


def delete_book_by_title_service(db: Session, title: str, user_id: UUID):
    book = get_book_by_title(db, title, user_id)

    if book is None:
        raise HTTPException(status_code=404, detail="Book not found")

    delete_book(db, book.id, user_id)
    reset_metadata_progress_if_library_empty(db, user_id)
    return {"message": "Book deleted"}


def patch_book_service(db: Session, p, user_id: UUID):
    book = get_book_by_title(db, p.title, user_id)

    if book is None:
        raise HTTPException(status_code=404, detail="Book not found")

    update_data = {}

    if p.new_title and p.new_title != p.title:
        duplicate = get_book_by_title(db, p.new_title, user_id)

        if duplicate is not None:
            raise HTTPException(status_code=400, detail="Title already exists")

        update_data["title"] = p.new_title

    if p.author is not None:
        update_data["authors"] = p.author.strip() or "Unknown"

    if getattr(p, "isbn_uid", None) is not None:
        next_isbn = p.isbn_uid.strip()
        duplicate = get_book_by_isbn_uid_excluding_id(db, next_isbn, book.id, user_id)
        if duplicate is not None:
            raise HTTPException(status_code=400, detail="ISBN/UID already exists")
        update_data["isbn_uid"] = next_isbn

    if p.total_pages is not None:
        update_data["total_pages"] = p.total_pages

    if getattr(p, "tracking_mode", None) is not None:
        update_data["tracking_mode"] = normalized_tracking_mode(
            p.tracking_mode,
            update_data.get("total_pages", book.total_pages),
        )

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

    if (
        _status_patch_value(p) is not None
        or p.pages_read is not None
        or p.progress_percent is not None
        or p.total_pages is not None
    ):
        total_pages = update_data.get("total_pages", book.total_pages)
        _apply_status_and_progress(
            update_data,
            _status_patch_value(p),
            p.pages_read,
            total_pages,
            book.pages_read,
            progress_percent=p.progress_percent,
            current_progress_percent=book.progress_percent,
            current_status=_normalized_status_from_book(book),
            current_start_date=next_start_date,
            current_end_date=next_end_date,
            current_last_date_read=book.last_date_read,
            current_rating=book.star_rating,
        )

    update_book(db, book.id, update_data, user_id)

    return {"message": "Book updated"}


def patch_book_by_id_service(db: Session, book_id: str, body, user_id: UUID):
    book = get_book_by_isbn_uid(db, book_id, user_id)

    if book is None:
        raise HTTPException(status_code=404, detail="Book not found")

    update_data = {}
    fields_set = getattr(body, "model_fields_set", set())

    if "title" in fields_set and body.title is not None:
        title = body.title.strip()
        if not title:
            raise HTTPException(status_code=400, detail="Title is required")
        duplicate = get_book_by_title_excluding_id(db, title, book.id, user_id)
        if duplicate is not None:
            raise HTTPException(status_code=400, detail="Title already exists")
        update_data["title"] = title

    if "author" in fields_set:
        update_data["authors"] = (body.author or "").strip() or "Unknown"

    if "isbn_uid" in fields_set and body.isbn_uid is not None:
        isbn_uid = body.isbn_uid.strip()
        duplicate = get_book_by_isbn_uid_excluding_id(db, isbn_uid, book.id, user_id)
        if duplicate is not None:
            raise HTTPException(status_code=400, detail="ISBN/UID already exists")
        update_data["isbn_uid"] = isbn_uid

    if "total_pages" in fields_set:
        update_data["total_pages"] = body.total_pages

    if "tracking_mode" in fields_set:
        update_data["tracking_mode"] = normalized_tracking_mode(
            body.tracking_mode,
            update_data.get("total_pages", book.total_pages),
        )

    if "star_rating" in fields_set:
        update_data["star_rating"] = body.star_rating

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
    progress_percent = body.progress_percent if "progress_percent" in fields_set else None
    _apply_status_and_progress(
        update_data,
        _status_patch_value(body),
        pages_read,
        total_pages,
        book.pages_read,
        progress_percent=progress_percent,
        current_progress_percent=book.progress_percent,
        current_status=_normalized_status_from_book(book),
        current_start_date=next_start_date,
        current_end_date=next_end_date,
        current_last_date_read=book.last_date_read,
        current_rating=update_data.get("star_rating", book.star_rating),
    )
    if "start_date" in fields_set:
        update_data["start_date"] = next_start_date
    if "end_date" in fields_set:
        update_data["end_date"] = next_end_date

    updated = update_book(db, book.id, update_data, user_id)

    return book_to_dict(updated)


def update_book_progress_by_id_service(db: Session, book_id: str, body, user_id: UUID):
    book = get_book_by_isbn_uid(db, book_id, user_id)

    if book is None:
        raise HTTPException(status_code=404, detail="Book not found")

    previous_pages_read = book.pages_read
    previous_progress_percent = book.progress_percent
    previous_status = _normalized_status_from_book(book)
    update_data = {}
    fields_set = getattr(body, "model_fields_set", set())
    if "total_pages" in fields_set:
        update_data["total_pages"] = body.total_pages

    if "tracking_mode" in fields_set:
        update_data["tracking_mode"] = normalized_tracking_mode(
            body.tracking_mode,
            update_data.get("total_pages", book.total_pages),
        )

    next_start_date = book.start_date
    next_end_date = book.end_date
    if "start_date" in fields_set:
        next_start_date = parse_reading_date(body.start_date, field_name="Start Date")
        update_data["start_date"] = next_start_date
    if "end_date" in fields_set:
        next_end_date = parse_reading_date(body.end_date, field_name="End Date")
        update_data["end_date"] = next_end_date
    _validate_date_range(next_start_date, next_end_date)

    _apply_status_and_progress(
        update_data,
        _status_patch_value(body),
        body.pages_read if "pages_read" in fields_set else None,
        update_data.get("total_pages", book.total_pages),
        book.pages_read,
        progress_percent=body.progress_percent if "progress_percent" in fields_set else None,
        current_progress_percent=book.progress_percent,
        current_status=_normalized_status_from_book(book),
        current_start_date=next_start_date,
        current_end_date=next_end_date,
        current_last_date_read=book.last_date_read,
        current_rating=book.star_rating,
    )
    if "start_date" in fields_set:
        update_data["start_date"] = next_start_date
    if "end_date" in fields_set:
        update_data["end_date"] = next_end_date

    updated = update_book(db, book.id, update_data, user_id)
    record_progress_activity(
        db,
        user_id=user_id,
        book=updated,
        previous_pages_read=previous_pages_read,
        previous_progress_percent=previous_progress_percent,
        previous_status=previous_status,
    )

    return book_to_dict(updated)
