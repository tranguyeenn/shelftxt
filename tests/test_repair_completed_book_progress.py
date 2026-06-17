from tests.test_api import TEST_USER_ID, TestingSessionLocal, _seed_book, engine
from backend.db.database import Base
from backend.db.models import Book
from backend.scripts.repair_completed_book_progress import repair_completed_book_progress


def setup_function():
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)


def test_repair_completed_book_progress_updates_legacy_rows():
    _seed_book(
        title="Legacy",
        authors="A",
        isbn_uid="legacy",
        read_status="read",
        total_pages=300,
        pages_read=0,
        progress_percent=0,
    )

    session = TestingSessionLocal()
    try:
        updated = repair_completed_book_progress(session)
        book = session.query(Book).filter(Book.isbn_uid == "legacy").one()
        assert updated == 1
        assert book.pages_read == 300
        assert book.progress_percent == 100
    finally:
        session.close()


def test_repair_completed_book_progress_dry_run_does_not_mutate():
    _seed_book(
        title="Legacy",
        authors="A",
        isbn_uid="legacy",
        read_status="read",
        total_pages=300,
        pages_read=0,
        progress_percent=0,
    )

    session = TestingSessionLocal()
    try:
        updated = repair_completed_book_progress(session, user_id=TEST_USER_ID, dry_run=True)
        book = session.query(Book).filter(Book.isbn_uid == "legacy").one()
        assert updated == 1
        assert book.pages_read == 0
        assert book.progress_percent == 0
    finally:
        session.close()
