import argparse
import csv
from pathlib import Path
from typing import Any
from uuid import UUID

from sqlalchemy.orm import Session

from backend.db.database import get_session_local
from backend.db.models import Book
from backend.services.ratings import rating_from_row


TITLE_ALIASES = ("Title", "title")
AUTHOR_ALIASES = ("Authors", "Author", "authors", "author")
ISBN_ALIASES = ("ISBN/UID", "isbn_uid", "isbn", "ISBN")


def _first_value(row: dict[str, Any], aliases: tuple[str, ...]) -> str | None:
    for alias in aliases:
        value = row.get(alias)
        if value is None:
            continue
        text = str(value).strip()
        if text:
            return text
    return None


def _query_matches(session: Session, row: dict[str, Any], user_id: UUID | None) -> list[Book]:
    isbn_uid = _first_value(row, ISBN_ALIASES)
    title = _first_value(row, TITLE_ALIASES)
    authors = _first_value(row, AUTHOR_ALIASES)

    if isbn_uid:
        query = session.query(Book).filter(Book.isbn_uid == isbn_uid)
        if user_id is not None:
            query = query.filter(Book.user_id == user_id)
        return query.all()

    if title and authors:
        query = session.query(Book).filter(Book.title == title, Book.authors == authors)
        if user_id is not None:
            query = query.filter(Book.user_id == user_id)
        return query.all()

    return []


def backfill_ratings_from_csv(
    session: Session,
    csv_path: str | Path,
    *,
    user_id: UUID | None = None,
    dry_run: bool = False,
) -> dict[str, int | str]:
    path = Path(csv_path)
    if not path.exists():
        raise FileNotFoundError(f"CSV file not found: {path}")

    rows_seen = 0
    updated = 0
    unchanged = 0
    skipped_no_rating = 0
    skipped_no_match = 0
    skipped_ambiguous = 0
    skipped_invalid_rating = 0

    with path.open(newline="", encoding="utf-8-sig") as handle:
        reader = csv.DictReader(handle)
        for row in reader:
            rows_seen += 1
            try:
                rating = rating_from_row(row)
            except (TypeError, ValueError):
                skipped_invalid_rating += 1
                continue

            if rating is None:
                skipped_no_rating += 1
                continue
            if not 1 <= rating <= 5:
                skipped_invalid_rating += 1
                continue

            isbn_uid = _first_value(row, ISBN_ALIASES)
            title = _first_value(row, TITLE_ALIASES)
            authors = _first_value(row, AUTHOR_ALIASES)
            matches = _query_matches(session, row, user_id)

            if not matches:
                skipped_no_match += 1
                continue
            if not isbn_uid and title and authors and len(matches) != 1:
                skipped_ambiguous += 1
                continue

            for book in matches:
                if book.star_rating == rating:
                    unchanged += 1
                    continue
                book.star_rating = rating
                updated += 1

    if dry_run:
        session.rollback()
    else:
        session.commit()

    return {
        "csv_path": str(path),
        "rows_seen": rows_seen,
        "updated": updated,
        "unchanged": unchanged,
        "skipped_no_rating": skipped_no_rating,
        "skipped_no_match": skipped_no_match,
        "skipped_ambiguous": skipped_ambiguous,
        "skipped_invalid_rating": skipped_invalid_rating,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Backfill existing ShelfTxt book ratings from a CSV.")
    parser.add_argument("csv_path", help="Path to CSV containing rating values.")
    parser.add_argument("--user-id", type=UUID, default=None, help="Limit updates to one user id.")
    parser.add_argument("--dry-run", action="store_true", help="Report changes without committing them.")
    args = parser.parse_args()

    session_factory = get_session_local()
    with session_factory() as session:
        summary = backfill_ratings_from_csv(
            session,
            args.csv_path,
            user_id=args.user_id,
            dry_run=args.dry_run,
        )

    print("Rating backfill summary")
    print("-----------------------")
    for key, value in summary.items():
        print(f"{key}: {value}")


if __name__ == "__main__":
    main()
