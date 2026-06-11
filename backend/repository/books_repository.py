from sqlalchemy.orm import Session

from backend.db.models import Book


def get_all_books(db: Session) -> list[Book]:
    return db.query(Book).order_by(Book.id).all()


def get_book_by_id(db: Session, book_id: int) -> Book | None:
    return db.query(Book).filter(Book.id == book_id).first()


def create_book(db: Session, book_data: dict) -> Book:
    book = Book(**book_data)
    db.add(book)
    db.commit()
    db.refresh(book)
    return book


def update_book(db: Session, book_id: int, book_data: dict) -> Book | None:
    book = get_book_by_id(db, book_id)

    if book is None:
        return None

    for key, value in book_data.items():
        if hasattr(book, key):
            setattr(book, key, value)

    db.commit()
    db.refresh(book)
    return book


def delete_book(db: Session, book_id: int) -> bool:
    book = get_book_by_id(db, book_id)

    if book is None:
        return False

    db.delete(book)
    db.commit()
    return True