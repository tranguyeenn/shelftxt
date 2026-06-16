from uuid import UUID

from sqlalchemy.orm import Session

from backend.db.models import Book


def get_all_books(db: Session, user_id: UUID):
    return (
        db.query(Book)
        .filter(Book.user_id == user_id)
        .order_by(Book.id.asc())
        .all()
    )


def get_book_by_id(db: Session, book_id: int, user_id: UUID):
    return (
        db.query(Book)
        .filter(Book.id == book_id, Book.user_id == user_id)
        .first()
    )


def get_book_by_isbn_uid(db: Session, isbn_uid: str, user_id: UUID):
    return (
        db.query(Book)
        .filter(Book.isbn_uid == isbn_uid, Book.user_id == user_id)
        .first()
    )


def create_book(db: Session, book_data: dict, user_id: UUID):
    book = Book(**book_data, user_id=user_id)

    db.add(book)
    db.commit()
    db.refresh(book)

    return book


def update_book(db: Session, book_id: int, update_data: dict, user_id: UUID):
    book = get_book_by_id(db, book_id, user_id)

    if book is None:
        return None

    for key, value in update_data.items():
        setattr(book, key, value)

    db.commit()
    db.refresh(book)

    return book


def delete_book(db: Session, book_id: int, user_id: UUID):
    book = get_book_by_id(db, book_id, user_id)

    if book is None:
        return False

    db.delete(book)
    db.commit()

    return True