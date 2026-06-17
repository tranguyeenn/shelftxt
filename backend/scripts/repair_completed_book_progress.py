import argparse
from uuid import UUID

from sqlalchemy.orm import Session

from backend.db.database import get_session_local
from backend.db.models import Book

COMPLETED_DATABASE_STATUSES = {"read", "completed", "finished"}


def repair_completed_book_progress(
    session: Session,
    *,
    user_id: UUID | None = None,
    dry_run: bool = False,
) -> int:
    query = (
        session.query(Book)
        .filter(Book.read_status.in_(COMPLETED_DATABASE_STATUSES))
        .filter(Book.total_pages.is_not(None))
        .filter(Book.total_pages > 0)
    )
    if user_id is not None:
        query = query.filter(Book.user_id == user_id)

    books = [
        book
        for book in query.all()
        if book.pages_read is None or int(book.pages_read or 0) < int(book.total_pages or 0)
    ]

    if dry_run:
        return len(books)

    for book in books:
        book.pages_read = int(book.total_pages)
        book.progress_percent = 100

    session.commit()
    return len(books)


def main() -> None:
    parser = argparse.ArgumentParser(description="Repair completed books with incomplete page progress.")
    parser.add_argument("--user-id", type=UUID, default=None)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    session_factory = get_session_local()
    with session_factory() as session:
        count = repair_completed_book_progress(
            session,
            user_id=args.user_id,
            dry_run=args.dry_run,
        )
    action = "Would update" if args.dry_run else "Updated"
    print(f"{action} {count} completed book progress rows.")


if __name__ == "__main__":
    main()
