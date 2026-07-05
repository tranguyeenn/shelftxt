import argparse
import logging
import time
from datetime import datetime, timezone

from sqlalchemy.exc import SQLAlchemyError

from backend.db.database import get_session_local
from backend.db.models import Book
from backend.services.page_lookup import (
    lookup_book_cover,
    lookup_book_metadata,
    manual_metadata_for_title,
)

logger = logging.getLogger(__name__)


def _needs_metadata(book: Book) -> bool:
    manual_metadata = manual_metadata_for_title(book.title)
    if manual_metadata and manual_metadata.genres and book.genres != manual_metadata.genres:
        return True
    if book.genres and len(book.genres) > 3:
        return True
    return not (book.genres and book.subjects and book.description)


def _needs_requested_metadata(
    book: Book, *, missing_genres: bool, missing_covers: bool = False
) -> bool:
    if missing_covers:
        return not book.cover_url
    if missing_genres:
        return not book.genres
    return _needs_metadata(book)


def _should_replace_genres(book: Book, metadata) -> bool:
    next_genres = getattr(metadata, "genres", None)
    if not next_genres:
        return False
    if not book.genres:
        return True
    if len(book.genres) > 3:
        return True
    return getattr(metadata, "metadata_source", None) == "manual_override" and book.genres != next_genres


def _apply_metadata(book: Book, metadata) -> bool:
    if metadata is None:
        return False

    changed = False
    librarything_data = getattr(metadata, "librarything", None)
    if librarything_data:
        existing = dict(book.book_metadata or {})
        if existing.get("librarything") != librarything_data:
            existing["librarything"] = librarything_data
            book.book_metadata = existing
            changed = True
    for attr in (
        "description",
        "subjects",
        "genres",
        "first_publish_year",
        "metadata_source",
        "language",
        "work_key",
        "edition_key",
        "cover_url",
    ):
        value = getattr(metadata, attr, None)
        if attr == "genres" and _should_replace_genres(book, metadata):
            setattr(book, attr, value[:3])
            changed = True
        elif value and not getattr(book, attr):
            setattr(book, attr, value)
            changed = True

    if metadata.total_pages and not book.total_pages:
        book.total_pages = metadata.total_pages
        book.page_count_checked = True
        changed = True

    if changed:
        book.metadata_enriched_at = datetime.now(timezone.utc)
    return changed


def _trim_existing_genres(book: Book) -> bool:
    if book.genres and len(book.genres) > 3:
        book.genres = book.genres[:3]
        book.metadata_enriched_at = datetime.now(timezone.utc)
        return True
    return False


def backfill_book_metadata(
    *,
    limit: int = 100,
    batch_size: int = 10,
    sleep_seconds: float = 0.25,
    only_rated: bool = False,
    only_read: bool = False,
    missing_genres: bool = False,
    missing_covers: bool = False,
) -> int:
    session_factory = get_session_local()
    updated = 0
    scanned = 0
    with session_factory() as session:
        query = session.query(Book)
        if only_rated:
            query = query.filter(Book.star_rating.is_not(None))
        if only_read:
            query = query.filter(Book.read_status == "read")

        order_by = [Book.id.asc()]
        if only_rated:
            order_by = [Book.star_rating.desc(), Book.id.asc()]

        books = [
            book
            for book in query.order_by(*order_by).all()
            if _needs_requested_metadata(
                book,
                missing_genres=missing_genres,
                missing_covers=missing_covers,
            )
        ][:limit]
        logger.info("Metadata backfill starting: %s candidate books", len(books))
        for book in books:
            scanned += 1
            if not _needs_requested_metadata(
                book,
                missing_genres=missing_genres,
                missing_covers=missing_covers,
            ):
                logger.info("Skipping already enriched book id=%s title=%r", book.id, book.title)
                continue
            try:
                metadata = (
                    lookup_book_cover(book.title, book.authors, book.isbn_uid)
                    if missing_covers
                    else lookup_book_metadata(book.title, book.authors, book.isbn_uid)
                )
                if _apply_metadata(book, metadata):
                    updated += 1
                    logger.info("Enriched book id=%s title=%r", book.id, book.title)
                elif _trim_existing_genres(book):
                    updated += 1
                    logger.info("Trimmed over-inflated genres for book id=%s title=%r", book.id, book.title)
                else:
                    logger.info("No metadata found for book id=%s title=%r", book.id, book.title)
            except Exception:
                logger.exception("Metadata lookup failed for book id=%s title=%r", book.id, book.title)

            if scanned % batch_size == 0:
                try:
                    session.commit()
                    logger.info("Committed metadata backfill batch scanned=%s updated=%s", scanned, updated)
                except SQLAlchemyError:
                    session.rollback()
                    logger.exception("Metadata backfill batch commit failed")
            time.sleep(max(0.0, sleep_seconds))

        try:
            session.commit()
        except SQLAlchemyError:
            session.rollback()
            logger.exception("Metadata backfill final commit failed")

    logger.info("Metadata backfill finished scanned=%s updated=%s", scanned, updated)
    return updated


def main() -> None:
    parser = argparse.ArgumentParser(description="Backfill ShelfTxt book metadata from Open Library.")
    parser.add_argument("--limit", type=int, default=100)
    parser.add_argument("--batch-size", type=int, default=10)
    parser.add_argument("--sleep", type=float, default=0.25)
    parser.add_argument("--only-rated", action="store_true", help="Only enrich books with star_rating set.")
    parser.add_argument("--only-read", action="store_true", help="Only enrich books with read_status='read'.")
    parser.add_argument("--missing-genres", action="store_true", help="Only enrich books with missing genres.")
    parser.add_argument("--missing-covers", action="store_true", help="Only enrich books with missing cover URLs.")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    backfill_book_metadata(
        limit=args.limit,
        batch_size=args.batch_size,
        sleep_seconds=args.sleep,
        only_rated=args.only_rated,
        only_read=args.only_read,
        missing_genres=args.missing_genres,
        missing_covers=args.missing_covers,
    )


if __name__ == "__main__":
    main()
