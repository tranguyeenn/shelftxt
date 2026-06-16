import csv
import uuid
from datetime import date
from io import StringIO

from fastapi import HTTPException
from sqlalchemy.orm import Session

from backend.auth.dev_user import get_or_create_dev_user
from backend.repository.postgres_books_repository import (
    create_book,
    delete_book,
    get_all_books,
    get_book_by_isbn_uid,
    update_book,
)


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
        "Progress (%)": book.progress_percent,
        "Pages Read": book.pages_read,
        "Total Pages": book.total_pages,
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


def get_books_service(db: Session, page: int, limit: int):
    user_id = get_or_create_dev_user(db)
    books = get_all_books(db, user_id)
    total = len(books)
    start = (page - 1) * limit

    return {
        "page": page,
        "limit": limit,
        "total": total,
        "results": [book_to_dict(book) for book in books[start : start + limit]],
    }


def get_book_by_id_service(db: Session, book_id: str):
    user_id = get_or_create_dev_user(db)
    book = get_book_by_isbn_uid(db, book_id, user_id)

    if book is None:
        raise HTTPException(status_code=404, detail="Book not found")

    return book_to_dict(book)


def export_library_csv(db: Session) -> str:
    user_id = get_or_create_dev_user(db)
    books = get_all_books(db, user_id)

    fieldnames = [
        "Title",
        "Authors",
        "ISBN/UID",
        "Read Status",
        "Star Rating",
        "Last Date Read",
        "Progress (%)",
        "Pages Read",
        "Total Pages",
    ]

    output = StringIO()
    writer = csv.DictWriter(output, fieldnames=fieldnames)
    writer.writeheader()

    for book in books:
        writer.writerow(book_to_dict(book))

    return output.getvalue()


def add_book_service(db: Session, book):
    user_id = get_or_create_dev_user(db)

    create_book(
        db,
        {
            "title": book.title,
            "authors": book.author,
            "isbn_uid": f"uid-{uuid.uuid4()}",
            "read_status": "to-read",
            "star_rating": None,
            "last_date_read": None,
            "progress_percent": 0,
            "pages_read": 0,
            "total_pages": book.total_pages,
        },
        user_id,
    )

    return {"message": "Book added"}


def import_books_service(db: Session, data):
    user_id = get_or_create_dev_user(db)
    books = get_all_books(db, user_id)
    existing_titles = {book.title for book in books}

    imported = 0
    skipped = 0

    for book in data.books:
        title = (book.title or "").strip()

        if not title or title in existing_titles:
            skipped += 1
            continue

        create_book(
            db,
            {
                "title": title,
                "authors": (book.author or "Unknown").strip(),
                "isbn_uid": f"uid-{uuid.uuid4()}",
                "read_status": "to-read",
                "star_rating": None,
                "last_date_read": None,
                "progress_percent": 0,
                "pages_read": 0,
                "total_pages": book.total_pages,
            },
            user_id,
        )

        existing_titles.add(title)
        imported += 1

    return {
        "imported": imported,
        "skipped": skipped,
    }


def clear_library_service(db: Session, confirm: bool):
    user_id = get_or_create_dev_user(db)

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


def delete_book_by_id_service(db: Session, book_id: str):
    user_id = get_or_create_dev_user(db)
    book = get_book_by_isbn_uid(db, book_id, user_id)

    if book is None:
        raise HTTPException(status_code=404, detail="Book not found")

    delete_book(db, book.id, user_id)

    return {"message": "Book deleted"}


def delete_book_by_title_service(db: Session, title: str):
    user_id = get_or_create_dev_user(db)
    books = get_all_books(db, user_id)

    for book in books:
        if book.title == title:
            delete_book(db, book.id, user_id)
            return {"message": "Book deleted"}

    raise HTTPException(status_code=404, detail="Book not found")


def patch_book_service(db: Session, p):
    user_id = get_or_create_dev_user(db)
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
        update_data["authors"] = p.author

    if p.total_pages is not None:
        update_data["total_pages"] = p.total_pages

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
                }
            )

        else:
            raise HTTPException(status_code=400, detail="Invalid move target")

    update_book(db, book.id, update_data, user_id)

    return {"message": "Book updated"}


def update_book_progress_by_id_service(db: Session, book_id: str, body):
    user_id = get_or_create_dev_user(db)
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
            }
        )

    else:
        raise HTTPException(status_code=400, detail="Invalid status")

    updated = update_book(db, book.id, update_data, user_id)

    return book_to_dict(updated)