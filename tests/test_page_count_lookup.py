import unittest
from unittest.mock import patch
from uuid import UUID

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from backend.db.database import Base
from backend.db.models import Book, Profile
from backend.services.page_count_lookup import (
    backfill_missing_page_counts,
    fetch_openlibrary_pages_by_isbn,
    fetch_openlibrary_pages_by_title,
    lookup_page_count,
)


class FakeResponse:
    def __init__(self, payload):
        self.payload = payload

    def raise_for_status(self):
        return None

    def json(self):
        return self.payload


class PageCountLookupTests(unittest.TestCase):
    def test_isbn_lookup_returns_page_count(self):
        with patch("backend.services.page_count_lookup.httpx.get") as mock_get:
            mock_get.return_value = FakeResponse({"number_of_pages": 321})

            self.assertEqual(fetch_openlibrary_pages_by_isbn("978-1-234567-89-0"), 321)

    def test_isbn_failure_falls_back_to_title_lookup(self):
        with (
            patch("backend.services.page_count_lookup.fetch_openlibrary_pages_by_isbn", return_value=None),
            patch("backend.services.page_count_lookup.fetch_openlibrary_pages_by_title", return_value=222) as title_lookup,
        ):
            self.assertEqual(lookup_page_count("Title", "Author", "9781234567890"), 222)
            title_lookup.assert_called_once_with("Title", "Author")

    def test_title_lookup_fetches_edition_records(self):
        with patch("backend.services.page_count_lookup.httpx.get") as mock_get:
            mock_get.side_effect = [
                FakeResponse({"docs": [{"edition_key": ["OL1M", "OL2M"]}]}),
                FakeResponse({"number_of_pages": None}),
                FakeResponse({"number_of_pages": 444}),
            ]

            self.assertEqual(fetch_openlibrary_pages_by_title("Kindred", "Octavia Butler"), 444)
            self.assertEqual(mock_get.call_count, 3)

    def test_backfill_only_processes_unchecked_and_does_not_overwrite(self):
        engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
        SessionLocal = sessionmaker(bind=engine)
        Base.metadata.create_all(bind=engine)
        user_id = UUID("00000000-0000-0000-0000-000000000001")
        session = SessionLocal()
        session.add(Profile(id=user_id, email="a@example.com", username="a"))
        session.add_all(
            [
                Book(title="Needs Pages", authors="A", isbn_uid="n", user_id=user_id, total_pages=None, page_count_checked=False),
                Book(title="Already Has Pages", authors="A", isbn_uid="h", user_id=user_id, total_pages=100, page_count_checked=False),
                Book(title="Checked", authors="A", isbn_uid="c", user_id=user_id, total_pages=None, page_count_checked=True),
            ]
        )
        session.commit()

        with patch("backend.services.page_count_lookup.lookup_page_count", return_value=250) as mock_lookup:
            updated = backfill_missing_page_counts(session)

        books = {book.title: book for book in session.query(Book).all()}
        self.assertEqual(updated, 1)
        self.assertEqual(books["Needs Pages"].total_pages, 250)
        self.assertTrue(books["Needs Pages"].page_count_checked)
        self.assertEqual(books["Already Has Pages"].total_pages, 100)
        self.assertIsNone(books["Checked"].total_pages)
        mock_lookup.assert_called_once()
        session.close()

    def test_failed_lookup_sets_page_count_checked_true(self):
        engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
        SessionLocal = sessionmaker(bind=engine)
        Base.metadata.create_all(bind=engine)
        user_id = UUID("00000000-0000-0000-0000-000000000002")
        session = SessionLocal()
        session.add(Profile(id=user_id, email="b@example.com", username="b"))
        session.add(Book(title="Missing", authors="A", isbn_uid="m", user_id=user_id, total_pages=None, page_count_checked=False))
        session.commit()

        with patch("backend.services.page_count_lookup.lookup_page_count", return_value=None):
            updated = backfill_missing_page_counts(session)

        book = session.query(Book).filter_by(title="Missing").one()
        self.assertEqual(updated, 0)
        self.assertIsNone(book.total_pages)
        self.assertTrue(book.page_count_checked)
        session.close()
