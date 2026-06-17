import csv
import tempfile
import unittest
from pathlib import Path

from backend.db.database import Base
from backend.db.models import Book
from backend.scripts.backfill_ratings_from_csv import backfill_ratings_from_csv
from tests.test_api import TEST_USER_ID, TestingSessionLocal, _seed_book, _seed_profile, engine


class BackfillRatingsFromCsvTests(unittest.TestCase):
    def setUp(self):
        Base.metadata.drop_all(bind=engine)
        Base.metadata.create_all(bind=engine)
        _seed_profile()

    def _write_csv(self, rows):
        temp_dir = tempfile.TemporaryDirectory()
        path = Path(temp_dir.name) / "ratings.csv"
        with path.open("w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=list(rows[0].keys()))
            writer.writeheader()
            writer.writerows(rows)
        return temp_dir, path

    def test_backfills_rating_by_isbn_uid(self):
        _seed_book(title="The Great Gatsby", authors="F. Scott Fitzgerald", isbn_uid="gatsby")
        temp_dir, csv_path = self._write_csv(
            [
                {
                    "Title": "The Great Gatsby",
                    "Authors": "F. Scott Fitzgerald",
                    "ISBN/UID": "gatsby",
                    "Star Rating": "4.75",
                }
            ]
        )
        self.addCleanup(temp_dir.cleanup)

        session = TestingSessionLocal()
        try:
            summary = backfill_ratings_from_csv(session, csv_path, user_id=TEST_USER_ID)
            book = session.query(Book).filter(Book.isbn_uid == "gatsby").one()
            rating = book.star_rating
        finally:
            session.close()

        self.assertEqual(summary["updated"], 1)
        self.assertEqual(rating, 4.75)

    def test_backfills_rating_by_title_and_author_when_isbn_missing(self):
        _seed_book(title="Book Lovers", authors="Emily Henry", isbn_uid="uid-book-lovers")
        temp_dir, csv_path = self._write_csv(
            [{"Title": "Book Lovers", "Authors": "Emily Henry", "My Rating": "5.0"}]
        )
        self.addCleanup(temp_dir.cleanup)

        session = TestingSessionLocal()
        try:
            summary = backfill_ratings_from_csv(session, csv_path, user_id=TEST_USER_ID)
            book = session.query(Book).filter(Book.title == "Book Lovers").one()
            rating = book.star_rating
        finally:
            session.close()

        self.assertEqual(summary["updated"], 1)
        self.assertEqual(rating, 5.0)

    def test_skips_empty_ratings(self):
        _seed_book(title="Unrated", authors="A", isbn_uid="unrated", star_rating=3.5)
        temp_dir, csv_path = self._write_csv(
            [{"Title": "Unrated", "Authors": "A", "ISBN/UID": "unrated", "Rating": ""}]
        )
        self.addCleanup(temp_dir.cleanup)

        session = TestingSessionLocal()
        try:
            summary = backfill_ratings_from_csv(session, csv_path, user_id=TEST_USER_ID)
            book = session.query(Book).filter(Book.isbn_uid == "unrated").one()
            rating = book.star_rating
        finally:
            session.close()

        self.assertEqual(summary["updated"], 0)
        self.assertEqual(summary["skipped_no_rating"], 1)
        self.assertEqual(rating, 3.5)
