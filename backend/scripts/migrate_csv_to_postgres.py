import argparse
import math
from pathlib import Path
from typing import TypedDict

import pandas as pd
from sqlalchemy.orm import Session

from backend.db.database import SessionLocal
from backend.repository.postgres_books_repository import (
    create_book,
    get_all_books,
)


DEFAULT_CSV_PATH = Path("backend/data/processed/books.csv")


class MigrationError(TypedDict):
    row: int
    error: str


class MigrationSummary(TypedDict):
    csv_path: str
    rows_seen: int
    imported: int
    skipped_duplicates: int
    skipped_invalid: int
    errors: list[MigrationError]


def clean_string(value, default=None):
    if value is None:
        return default

    if isinstance(value, float) and math.isnan(value):
        return default

    text = str(value).strip()

    if not text or text.lower() in {"nan", "none", "null"}:
        return default

    return text


def clean_int(value, default=None):
    if value is None:
        return default

    try:
        if pd.isna(value):
            return default

        return int(float(value))
    except (TypeError, ValueError):
        return default


def clean_float(value, default=None):
    if value is None:
        return default

    try:
        if pd.isna(value):
            return default

        return float(value)
    except (TypeError, ValueError):
        return default


def clean_date(value):
    if value is None:
        return None

    try:
        if pd.isna(value):
            return None

        parsed = pd.to_datetime(value, errors="coerce")

        if pd.isna(parsed):
            return None

        return parsed.date()
    except (TypeError, ValueError):
        return None


def normalize_book_row(row):
    title = clean_string(row.get("Title"))
    authors = clean_string(row.get("Authors"), default="Unknown")
    isbn_uid = clean_string(row.get("ISBN/UID"))

    if not title:
        raise ValueError("Missing title")

    if not isbn_uid:
        raise ValueError(f"Missing ISBN/UID for title: {title}")

    total_pages = clean_int(row.get("Total Pages"))
    tracking_mode = clean_string(row.get("tracking_mode") or row.get("Tracking Mode"))
    if tracking_mode not in {"percentage", "pages"}:
        tracking_mode = "pages" if total_pages is not None else "percentage"

    return {
        "title": title,
        "authors": authors,
        "isbn_uid": isbn_uid,
        "read_status": clean_string(row.get("Read Status"), default="to-read"),
        "star_rating": clean_float(row.get("Star Rating")),
        "last_date_read": clean_date(row.get("Last Date Read")),
        "start_date": clean_date(row.get("start_date") or row.get("Start Date")),
        "end_date": clean_date(row.get("end_date") or row.get("End Date")),
        "progress_percent": clean_float(row.get("Progress (%)"), default=0),
        "pages_read": clean_int(row.get("Pages Read"), default=0),
        "total_pages": total_pages,
        "tracking_mode": tracking_mode,
    }


def migrate_csv_to_postgres(db: Session, csv_path: Path) -> MigrationSummary:
    if not csv_path.exists():
        raise FileNotFoundError(f"CSV file not found: {csv_path}")

    df = pd.read_csv(csv_path)

    existing_books = get_all_books(db)
    existing_isbn_uids = {book.isbn_uid for book in existing_books}
    existing_titles = {book.title for book in existing_books}

    imported = 0
    skipped_duplicates = 0
    skipped_invalid = 0
    errors: list[MigrationError] = []

    for csv_row_number, (_, row) in enumerate(df.iterrows(), start=2):
        try:
            book_data = normalize_book_row(row)

            if (
                book_data["isbn_uid"] in existing_isbn_uids
                or book_data["title"] in existing_titles
            ):
                skipped_duplicates += 1
                continue

            create_book(db, book_data)

            existing_isbn_uids.add(book_data["isbn_uid"])
            existing_titles.add(book_data["title"])
            imported += 1

        except Exception as exc:
            skipped_invalid += 1
            errors.append(
                {
                    "row": csv_row_number,
                    "error": str(exc),
                }
            )

    return {
        "csv_path": str(csv_path),
        "rows_seen": len(df),
        "imported": imported,
        "skipped_duplicates": skipped_duplicates,
        "skipped_invalid": skipped_invalid,
        "errors": errors,
    }


def main():
    parser = argparse.ArgumentParser(
        description="Migrate ShelfTxt books CSV data into PostgreSQL."
    )
    parser.add_argument(
        "--csv",
        default=str(DEFAULT_CSV_PATH),
        help="Path to books CSV file.",
    )

    args = parser.parse_args()
    csv_path = Path(args.csv)

    db = SessionLocal()

    try:
        summary = migrate_csv_to_postgres(db, csv_path)

        print("CSV migration summary")
        print("---------------------")
        print(f"CSV path: {summary['csv_path']}")
        print(f"Rows seen: {summary['rows_seen']}")
        print(f"Imported: {summary['imported']}")
        print(f"Skipped duplicates: {summary['skipped_duplicates']}")
        print(f"Skipped invalid: {summary['skipped_invalid']}")

        if summary["errors"]:
            print()
            print("Errors:")
            for error in summary["errors"]:
                print(f"- Row {error['row']}: {error['error']}")

    finally:
        db.close()


if __name__ == "__main__":
    main()
