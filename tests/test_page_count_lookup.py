import unittest
from unittest.mock import patch
from uuid import UUID

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from backend.db.database import Base
from backend.db.models import Book, Profile
from backend.services.page_count_lookup import (
    PageCountResult,
    backfill_missing_page_counts,
    filter_page_count_outliers,
    fetch_google_pages_by_isbn,
    fetch_openlibrary_pages_by_isbn,
    fetch_openlibrary_pages_by_title,
    fetch_google_title_page_candidates,
    fetch_openlibrary_title_page_candidates,
    lookup_page_count,
    lookup_page_count_result,
    median_page_count,
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

    def test_google_isbn_lookup_returns_page_count(self):
        with patch("backend.services.page_count_lookup.httpx.get") as mock_get:
            mock_get.return_value = FakeResponse(
                {"items": [{"volumeInfo": {"pageCount": 298}}]}
            )

            self.assertEqual(fetch_google_pages_by_isbn("978-1-234567-89-0"), 298)

    def test_google_isbn_runs_after_open_library_before_title_fallback(self):
        with (
            patch(
                "backend.services.page_count_lookup.fetch_openlibrary_pages_by_isbn",
                return_value=None,
            ),
            patch(
                "backend.services.page_count_lookup.fetch_google_pages_by_isbn",
                return_value=298,
            ),
            patch("backend.services.page_count_lookup.lookup_page_count_by_title") as title_lookup,
        ):
            result = lookup_page_count_result("Title", "Author", "9781234567890")

        self.assertEqual(result, PageCountResult(298, "google_books_isbn", 1))
        title_lookup.assert_not_called()

    def test_isbn_failure_falls_back_to_title_lookup(self):
        with (
            patch("backend.services.page_count_lookup.fetch_openlibrary_pages_by_isbn", return_value=None),
            patch(
                "backend.services.page_count_lookup.lookup_page_count_by_title",
                return_value=type("Result", (), {"pages": 222, "source": "median_editions"})(),
            ) as title_lookup,
        ):
            self.assertEqual(lookup_page_count("Title", "Author", "9781234567890"), 222)
            title_lookup.assert_called_once_with("Title", "Author")

    def test_single_title_match_is_not_enough_for_median(self):
        with patch("backend.services.page_count_lookup.httpx.get") as mock_get:
            mock_get.side_effect = [
                FakeResponse(
                    {
                        "docs": [
                            {
                                "title": "Kindred",
                                "author_name": ["Octavia Butler"],
                                "edition_key": ["OL2M"],
                            }
                        ]
                    }
                ),
                FakeResponse({"number_of_pages": 444}),
                FakeResponse({"items": []}),
            ]

            self.assertIsNone(fetch_openlibrary_pages_by_title("Kindred", "Octavia Butler"))
            self.assertEqual(mock_get.call_count, 3)

    def test_multiple_editions_return_median(self):
        self.assertEqual(median_page_count([180, 208, 256, 270, 272, 280, 300]), 270)

    def test_outlier_editions_are_removed(self):
        values = [180, 208, 256, 270, 272, 280, 300, 1200]

        self.assertEqual(filter_page_count_outliers(values), [180, 208, 256, 270, 272, 280, 300])
        self.assertEqual(median_page_count(values), 270)

    def test_empty_edition_list_returns_none(self):
        with patch("backend.services.page_count_lookup.httpx.get") as mock_get:
            mock_get.return_value = FakeResponse({"docs": [{"edition_key": []}]})

            self.assertIsNone(fetch_openlibrary_pages_by_title("Missing", "A"))

    def test_title_median_requires_three_matching_counts(self):
        with (
            patch(
                "backend.services.page_count_lookup.fetch_openlibrary_title_page_candidates",
                return_value=[240, 250],
            ),
            patch(
                "backend.services.page_count_lookup.fetch_google_title_page_candidates",
                return_value=[260],
            ),
        ):
            result = lookup_page_count_result("Known", "A")

        self.assertEqual(result.pages, 250)
        self.assertEqual(result.source, "median_title_author")
        self.assertEqual(result.editions_used, 3)

    def test_isbn_lookup_takes_precedence_over_median_calculation(self):
        with (
            patch("backend.services.page_count_lookup.fetch_openlibrary_pages_by_isbn", return_value=321),
            patch("backend.services.page_count_lookup.lookup_page_count_by_title") as title_lookup,
        ):
            result = lookup_page_count_result("Title", "Author", "9781234567890")

        self.assertEqual(result.pages, 321)
        self.assertEqual(result.source, "open_library_isbn")
        title_lookup.assert_not_called()

    def test_exact_edition_lookup_runs_before_title_median(self):
        with (
            patch("backend.services.page_count_lookup.fetch_openlibrary_pages_by_isbn", return_value=None),
            patch("backend.services.page_count_lookup.fetch_google_pages_by_isbn", return_value=None),
            patch("backend.services.page_count_lookup.fetch_openlibrary_pages_by_edition", return_value=333),
            patch("backend.services.page_count_lookup.lookup_page_count_by_title") as title_lookup,
        ):
            result = lookup_page_count_result("Title", "Author", "9781234567890", "OL123M")

        self.assertEqual(result.pages, 333)
        self.assertEqual(result.source, "open_library_edition")
        title_lookup.assert_not_called()

    def test_backfill_retries_missing_counts_and_does_not_overwrite(self):
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

        with patch(
            "backend.services.page_count_lookup.lookup_page_count_result",
            return_value=type("Result", (), {"pages": 250, "source": "median_editions"})(),
        ) as mock_lookup:
            updated = backfill_missing_page_counts(session)

        books = {book.title: book for book in session.query(Book).all()}
        self.assertEqual(updated, 2)
        self.assertEqual(books["Needs Pages"].total_pages, 250)
        self.assertEqual(books["Needs Pages"].page_count_source, "median_editions")
        self.assertTrue(books["Needs Pages"].page_count_checked)
        self.assertEqual(books["Already Has Pages"].total_pages, 100)
        self.assertEqual(books["Checked"].total_pages, 250)
        mock_lookup.assert_called()
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

        with patch(
            "backend.services.page_count_lookup.lookup_page_count_result",
            return_value=type("Result", (), {"pages": None, "source": "unavailable"})(),
        ):
            updated = backfill_missing_page_counts(session)

        book = session.query(Book).filter_by(title="Missing").one()
        self.assertEqual(updated, 0)
        self.assertIsNone(book.total_pages)
        self.assertTrue(book.page_count_checked)
        self.assertEqual(book.page_count_source, "unavailable")
        session.close()

    def test_backfill_respects_limit(self):
        engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
        SessionLocal = sessionmaker(bind=engine)
        Base.metadata.create_all(bind=engine)
        user_id = UUID("00000000-0000-0000-0000-000000000003")
        session = SessionLocal()
        session.add(Profile(id=user_id, email="c@example.com", username="c"))
        session.add_all(
            [
                Book(
                    title=f"Missing {i}",
                    authors="A",
                    isbn_uid=f"m-{i}",
                    user_id=user_id,
                    total_pages=None,
                    page_count_checked=False,
                )
                for i in range(5)
            ]
        )
        session.commit()

        with patch(
            "backend.services.page_count_lookup.lookup_page_count_result",
            return_value=PageCountResult(123, "median_editions"),
        ) as mock_lookup:
            updated = backfill_missing_page_counts(session, limit=2)

        self.assertEqual(updated, 2)
        self.assertEqual(mock_lookup.call_count, 2)
        checked_count = session.query(Book).filter(Book.page_count_checked.is_(True)).count()
        unchecked_count = session.query(Book).filter(Book.page_count_checked.is_(False)).count()
        self.assertEqual(checked_count, 2)
        self.assertEqual(unchecked_count, 3)
        session.close()
