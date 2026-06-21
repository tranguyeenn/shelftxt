from uuid import UUID

from sqlalchemy.orm import Session

from backend.db.models import Book


def count_books(db: Session, user_id: UUID) -> int:
    return db.query(Book).filter(Book.user_id == user_id).count()


def get_all_books(db: Session, user_id: UUID):
    return (
        db.query(Book)
        .filter(Book.user_id == user_id)
        .order_by(Book.id.asc())
        .all()
    )


def get_books_page(db: Session, user_id: UUID, offset: int, limit: int):
    return (
        db.query(Book)
        .filter(Book.user_id == user_id)
        .order_by(Book.id.asc())
        .offset(offset)
        .limit(limit)
        .all()
    )


def get_books_for_recommendation(db: Session, user_id: UUID, limit: int):
    return (
        db.query(Book)
        .filter(Book.user_id == user_id)
        .order_by(Book.id.asc())
        .limit(limit)
        .all()
    )


def get_existing_import_keys(db: Session, user_id: UUID):
    return db.query(Book.title, Book.isbn_uid).filter(Book.user_id == user_id).all()


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


def get_book_by_title(db: Session, title: str, user_id: UUID):
    return (
        db.query(Book)
        .filter(Book.title == title, Book.user_id == user_id)
        .order_by(Book.id.asc())
        .first()
    )


def get_book_by_title_excluding_id(db: Session, title: str, book_id: int, user_id: UUID):
    return (
        db.query(Book)
        .filter(Book.title == title, Book.user_id == user_id, Book.id != book_id)
        .order_by(Book.id.asc())
        .first()
    )


def get_book_by_isbn_uid_excluding_id(db: Session, isbn_uid: str, book_id: int, user_id: UUID):
    return (
        db.query(Book)
        .filter(Book.isbn_uid == isbn_uid, Book.user_id == user_id, Book.id != book_id)
        .order_by(Book.id.asc())
        .first()
    )


def create_book(db: Session, book_data: dict, user_id: UUID):
    book = Book(**book_data, user_id=user_id)

    db.add(book)
    db.commit()
    db.refresh(book)

    return book


def create_books_bulk(db: Session, books_data: list[dict], user_id: UUID) -> int:
    if not books_data:
        return 0

    db.add_all(Book(**book_data, user_id=user_id) for book_data in books_data)
    db.commit()

    return len(books_data)


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


def delete_books_for_user(db: Session, user_id: UUID) -> int:
    deleted = (
        db.query(Book)
        .filter(Book.user_id == user_id)
        .delete(synchronize_session=False)
    )
    db.commit()

    return deleted
