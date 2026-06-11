from fastapi import HTTPException
from sqlalchemy.orm import Session

from backend.repository.postgres_books_repository import (
    create_book,
    delete_book,
    get_all_books,
    get_book_by_id,
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


def get_books_service(db: Session, page: int, limit: int):
    books = get_all_books(db)

    total = len(books)
    start = (page - 1) * limit
    results = [book_to_dict(book) for book in books[start : start + limit]]

    return {
        "page": page,
        "limit": limit,
        "total": total,
        "results": results,
    }


def add_book_service(db: Session, book):
    book_data = {
        "title": book.title,
        "authors": book.author,
        "isbn_uid": f"uid-{book.title.lower().replace(' ', '-')}",
        "read_status": "to-read",
        "star_rating": None,
        "last_date_read": None,
        "progress_percent": 0,
        "pages_read": 0,
        "total_pages": book.total_pages,
    }

    create_book(db, book_data)

    return {"message": "Book added"}


def delete_book_by_id_service(db: Session, book_id: int):
    deleted = delete_book(db, book_id)

    if not deleted:
        raise HTTPException(status_code=404, detail="Book not found")

    return {"message": "Book deleted"}


def delete_book_by_title_service(db: Session, title: str):
    books = get_all_books(db)

    for book in books:
        if book.title == title:
            delete_book(db, book.id)
            return {"message": "Book deleted"}

    raise HTTPException(status_code=404, detail="Book not found")


def clear_library_service(db: Session, confirm: bool):
    if not confirm:
        raise HTTPException(
            status_code=400,
            detail="Confirmation required to clear the library",
        )

    books = get_all_books(db)
    deleted = len(books)

    for book in books:
        delete_book(db, book.id)

    return {"message": "Library cleared", "deleted": deleted}


def get_book_by_id_service(db: Session, book_id: int):
    book = get_book_by_id(db, book_id)

    if book is None:
        raise HTTPException(status_code=404, detail="Book not found")

    return book_to_dict(book)