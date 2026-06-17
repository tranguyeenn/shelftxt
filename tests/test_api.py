import unittest
from contextlib import ExitStack
from unittest.mock import patch
from uuid import UUID
from datetime import date

import httpx
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from backend import api
from backend.auth.dependencies import get_current_user
from backend.db.database import Base, get_db
from backend.db.models import Book, MetadataJob, Profile
from backend.services.page_lookup import BookMetadata, GoogleBooksRateLimited, OpenLibraryTimeout
from backend.services.recommendation import get_recommendation


TEST_USER_ID = UUID("00000000-0000-0000-0000-000000000001")
OTHER_USER_ID = UUID("00000000-0000-0000-0000-000000000002")

SQLALCHEMY_DATABASE_URL = "sqlite://"

engine = create_engine(
    SQLALCHEMY_DATABASE_URL,
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)

TestingSessionLocal = sessionmaker(
    autocommit=False,
    autoflush=False,
    bind=engine,
)


def override_get_db():
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()


def override_get_current_user():
    db = TestingSessionLocal()
    try:
        return db.query(Profile).filter(Profile.id == TEST_USER_ID).first()
    finally:
        db.close()


api.app.dependency_overrides[get_db] = override_get_db
api.app.dependency_overrides[get_current_user] = override_get_current_user


def _seed_profile(
    *,
    user_id=TEST_USER_ID,
    email="test@shelftxt.local",
    username="test",
):
    db = TestingSessionLocal()
    profile = Profile(
        id=user_id,
        email=email,
        username=username,
    )
    db.add(profile)
    db.commit()
    db.close()


def _seed_book(
    *,
    title="Book",
    authors="Author",
    isbn_uid="book-1",
    user_id=TEST_USER_ID,
    read_status="to-read",
    star_rating=None,
    last_date_read=None,
    start_date=None,
    end_date=None,
    progress_percent=0,
    pages_read=0,
    total_pages=None,
    description=None,
    subjects=None,
    genres=None,
    first_publish_year=None,
    metadata_source=None,
):
    def _date(value):
        if value is None or isinstance(value, date):
            return value
        return date.fromisoformat(value)

    db = TestingSessionLocal()
    book = Book(
        title=title,
        authors=authors,
        isbn_uid=isbn_uid,
        user_id=user_id,
        read_status=read_status,
        star_rating=star_rating,
        last_date_read=_date(last_date_read),
        start_date=_date(start_date),
        end_date=_date(end_date),
        progress_percent=progress_percent,
        pages_read=pages_read,
        total_pages=total_pages,
        description=description,
        subjects=subjects,
        genres=genres,
        first_publish_year=first_publish_year,
        metadata_source=metadata_source,
    )
    db.add(book)
    db.commit()
    db.refresh(book)
    db.close()
    return book


class ApiTests(unittest.TestCase):
    def setUp(self):
        Base.metadata.drop_all(bind=engine)
        Base.metadata.create_all(bind=engine)
        _seed_profile()
        self.page_count_http_patcher = patch(
            "backend.services.page_count_lookup.httpx.get",
            side_effect=AssertionError("real HTTP call in API test"),
        )
        self.mock_page_count_http_get = self.page_count_http_patcher.start()
        self.addCleanup(self.page_count_http_patcher.stop)
        self.page_lookup_http_patcher = patch(
            "backend.services.page_lookup.httpx.get",
            side_effect=httpx.TimeoutException("real HTTP call in API test"),
        )
        self.mock_page_lookup_http_get = self.page_lookup_http_patcher.start()
        self.addCleanup(self.page_lookup_http_patcher.stop)
        self.client = TestClient(api.app)

    def external_work_guard(self):
        stack = ExitStack()
        for target in (
            "backend.services.page_lookup.lookup_book_metadata",
            "backend.services.page_lookup.lookup_google_books_by_isbn",
            "backend.services.page_lookup.lookup_open_library_by_isbn",
            "backend.services.page_lookup.lookup_open_library_by_title",
            "backend.services.page_lookup.httpx.get",
            "backend.services.page_count_lookup.lookup_page_count",
            "backend.services.page_count_lookup.lookup_page_count_by_title",
            "backend.services.page_count_lookup.lookup_page_count_result",
            "backend.services.page_count_lookup.backfill_missing_page_counts",
            "backend.services.page_count_lookup.httpx.get",
        ):
            stack.enter_context(
                patch(
                    target,
                    side_effect=AssertionError(
                        f"user-facing endpoint attempted external/background work via {target}"
                    ),
                )
            )
        return stack

    def test_get_books_default_pagination(self):
        for i in range(25):
            _seed_book(
                title=f"Book {i}",
                authors=f"Author {i}",
                isbn_uid=f"id-{i}",
            )

        response = self.client.get("/books")

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["page"], 1)
        self.assertEqual(payload["limit"], 20)
        self.assertEqual(payload["total"], 25)
        self.assertEqual(len(payload["results"]), 20)
        self.assertEqual(payload["results"][0]["Title"], "Book 0")
        self.assertEqual(payload["results"][-1]["Title"], "Book 19")

    def test_import_schema_includes_csv_progress_fields(self):
        schema = api.app.openapi()["components"]["schemas"]
        import_row_properties = schema["ImportRow"]["properties"]

        self.assertIn("title", import_row_properties)
        self.assertIn("isbn_uid", import_row_properties)
        self.assertIn("author", import_row_properties)
        self.assertIn("total_pages", import_row_properties)
        self.assertIn("read_status", import_row_properties)
        self.assertIn("Star Rating", import_row_properties)
        self.assertIn("pages_read", import_row_properties)
        self.assertIn("progress_percent", import_row_properties)

        example_row = schema["ImportBooks"]["examples"][0]["books"][0]
        self.assertEqual(example_row["read_status"], "reading")
        self.assertEqual(example_row["star_rating"], 4.75)
        self.assertEqual(example_row["pages_read"], 120)
        self.assertEqual(example_row["progress_percent"], 39.47)

    def test_get_books_explicit_page_and_limit(self):
        for i in range(12):
            _seed_book(
                title=f"Book {i}",
                authors=f"Author {i}",
                isbn_uid=f"id-{i}",
            )

        response = self.client.get("/books?page=2&limit=5")

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["page"], 2)
        self.assertEqual(payload["limit"], 5)
        self.assertEqual(payload["total"], 12)
        self.assertEqual(len(payload["results"]), 5)
        self.assertEqual(
            [row["Title"] for row in payload["results"]],
            ["Book 5", "Book 6", "Book 7", "Book 8", "Book 9"],
        )

    def test_get_books_page_past_end_returns_empty_results(self):
        for i in range(3):
            _seed_book(
                title=f"Book {i}",
                authors=f"Author {i}",
                isbn_uid=f"id-{i}",
            )

        response = self.client.get("/books?page=10&limit=5")

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["total"], 3)
        self.assertEqual(payload["results"], [])

    def test_get_books_rejects_invalid_query_params(self):
        for query in (
            "page=0",
            "limit=0",
            "page=-1",
            "limit=-5",
            "page=abc",
            "limit=xyz",
            "limit=101",
        ):
            with self.subTest(query=query):
                response = self.client.get(f"/books?{query}")
                self.assertEqual(response.status_code, 422)

    def test_get_books_only_returns_current_user_books(self):
        _seed_profile(
            user_id=OTHER_USER_ID,
            email="other@shelftxt.local",
            username="other",
        )

        _seed_book(title="Mine", authors="A", isbn_uid="mine")
        _seed_book(
            title="Not Mine",
            authors="B",
            isbn_uid="not-mine",
            user_id=OTHER_USER_ID,
        )

        response = self.client.get("/books")

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["total"], 1)
        self.assertEqual(payload["results"][0]["Title"], "Mine")

    def test_get_books_does_not_trigger_external_or_background_work(self):
        _seed_book(title="Mine", authors="A", isbn_uid="mine")

        with self.external_work_guard():
            response = self.client.get("/books")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["total"], 1)

    def test_get_book_by_id(self):
        _seed_book(title="Existing", authors="Author A", isbn_uid="book-1")

        response = self.client.get("/books/book-1")

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["Title"], "Existing")
        self.assertEqual(payload["Authors"], "Author A")
        self.assertEqual(payload["ISBN/UID"], "book-1")

    def test_get_book_by_id_not_found(self):
        response = self.client.get("/books/missing-id")

        self.assertEqual(response.status_code, 404)

    def test_get_book_by_id_cannot_access_other_user_book(self):
        _seed_profile(
            user_id=OTHER_USER_ID,
            email="other@shelftxt.local",
            username="other",
        )

        _seed_book(
            title="Not Mine",
            authors="B",
            isbn_uid="not-mine",
            user_id=OTHER_USER_ID,
        )

        response = self.client.get("/books/not-mine")

        self.assertEqual(response.status_code, 404)

    def test_add_book_appends_new_tbr_row(self):
        response = self.client.post(
            "/books",
            json={"title": "New Book", "author": "New Author"},
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"message": "Book added"})

        books_response = self.client.get("/books")
        payload = books_response.json()

        self.assertEqual(payload["total"], 1)
        book = payload["results"][0]
        self.assertEqual(book["Title"], "New Book")
        self.assertEqual(book["Authors"], "New Author")
        self.assertEqual(book["Read Status"], "to-read")
        self.assertEqual(book["Progress (%)"], 0)
        self.assertEqual(book["Pages Read"], 0)
        self.assertTrue(book["ISBN/UID"].startswith("uid-"))

    def test_add_book_does_not_trigger_external_or_background_work(self):
        with self.external_work_guard():
            response = self.client.post(
                "/books",
                json={"title": "Fast Add", "author": "Author"},
            )

        self.assertEqual(response.status_code, 200)
        book = self.client.get("/books").json()["results"][0]
        self.assertEqual(book["Title"], "Fast Add")

    @patch("backend.services.page_lookup.lookup_book_metadata")
    def test_add_book_does_not_lookup_metadata(self, mock_lookup):
        response = self.client.post(
            "/books",
            json={"title": "Kindred", "author": "Octavia E. Butler"},
        )

        self.assertEqual(response.status_code, 200)
        book = self.client.get("/books").json()["results"][0]
        self.assertIsNone(book["Description"])
        self.assertIsNone(book["Subjects"])
        self.assertIsNone(book["Genres"])
        self.assertIsNone(book["First Publish Year"])
        self.assertIsNone(book["metadata_source"])
        self.assertIsNone(book["metadata_enriched_at"])
        mock_lookup.assert_not_called()

    def test_delete_book_removes_row(self):
        _seed_book(title="Keep", authors="Author A", isbn_uid="keep-id")
        _seed_book(title="Remove", authors="Author B", isbn_uid="remove-id")

        response = self.client.delete("/books?title=Remove")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"message": "Book deleted"})

        payload = self.client.get("/books").json()
        self.assertEqual(payload["total"], 1)
        self.assertEqual(payload["results"][0]["Title"], "Keep")

    def test_delete_book_by_id(self):
        _seed_book(title="Keep", authors="A", isbn_uid="keep-id")
        _seed_book(title="Remove", authors="B", isbn_uid="remove-id")

        response = self.client.delete("/books/remove-id")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"message": "Book deleted"})

        payload = self.client.get("/books").json()
        self.assertEqual(payload["total"], 1)
        self.assertEqual(payload["results"][0]["ISBN/UID"], "keep-id")

    def test_delete_book_by_id_does_not_trigger_external_or_background_work(self):
        _seed_book(title="Remove", authors="B", isbn_uid="remove-id")

        with self.external_work_guard():
            response = self.client.delete("/books/remove-id")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"message": "Book deleted"})

    def test_delete_book_by_id_cannot_delete_other_user_book(self):
        _seed_profile(
            user_id=OTHER_USER_ID,
            email="other@shelftxt.local",
            username="other",
        )

        _seed_book(title="Mine", authors="A", isbn_uid="mine")
        _seed_book(
            title="Not Mine",
            authors="B",
            isbn_uid="not-mine",
            user_id=OTHER_USER_ID,
        )

        response = self.client.delete("/books/not-mine")

        self.assertEqual(response.status_code, 404)

        payload = self.client.get("/books").json()
        self.assertEqual(payload["total"], 1)
        self.assertEqual(payload["results"][0]["ISBN/UID"], "mine")

        db = TestingSessionLocal()
        try:
            other_book = (
                db.query(Book)
                .filter(Book.user_id == OTHER_USER_ID)
                .filter(Book.isbn_uid == "not-mine")
                .first()
            )
        finally:
            db.close()

        self.assertIsNotNone(other_book)

    def test_patch_move_to_dnf(self):
        _seed_book(
            title="T",
            authors="A",
            isbn_uid="1",
            total_pages=100,
        )

        response = self.client.patch(
            "/books",
            json={"title": "T", "move_to": "dnf"},
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"message": "Book updated"})

        payload = self.client.get("/books/1").json()
        self.assertEqual(payload["Read Status"], "dnf")
        self.assertEqual(payload["Star Rating"], 1)

    def test_patch_book_by_id_updates_editable_metadata(self):
        _seed_book(
            title="Old",
            authors="A",
            isbn_uid="old-id",
            total_pages=100,
            pages_read=20,
            progress_percent=20,
        )

        response = self.client.patch(
            "/books/old-id",
            json={
                "title": "New",
                "author": "",
                "isbn_uid": "new-id",
                "total_pages": 120,
                "status": "completed",
                "pages_read": 10,
            },
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["Title"], "New")
        self.assertEqual(payload["Authors"], "Unknown")
        self.assertEqual(payload["ISBN/UID"], "new-id")
        self.assertEqual(payload["Total Pages"], 120)
        self.assertEqual(payload["Pages Read"], 120)
        self.assertEqual(payload["Read Status"], "read")

    def test_patch_pages_read_at_total_auto_completes(self):
        _seed_book(
            title="Almost",
            authors="A",
            isbn_uid="almost-id",
            total_pages=120,
            pages_read=40,
            progress_percent=33.33,
        )

        response = self.client.patch(
            "/books/almost-id",
            json={"pages_read": 120},
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["Read Status"], "read")
        self.assertEqual(payload["Pages Read"], 120)
        self.assertEqual(payload["Progress (%)"], 100)

    def test_patch_book_by_id_does_not_trigger_external_or_background_work(self):
        _seed_book(
            title="Old",
            authors="A",
            isbn_uid="old-id",
            total_pages=100,
        )

        with self.external_work_guard():
            response = self.client.patch(
                "/books/old-id",
                json={"title": "New", "author": "B"},
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["Title"], "New")

    def test_patch_cannot_update_other_user_book(self):
        _seed_profile(
            user_id=OTHER_USER_ID,
            email="other@shelftxt.local",
            username="other",
        )

        _seed_book(
            title="Not Mine",
            authors="B",
            isbn_uid="not-mine",
            user_id=OTHER_USER_ID,
            total_pages=100,
        )

        response = self.client.patch(
            "/books",
            json={"title": "Not Mine", "move_to": "dnf"},
        )

        self.assertEqual(response.status_code, 404)

    def test_update_book_progress_by_id(self):
        _seed_book(
            title="In Progress",
            authors="A",
            isbn_uid="book-1",
            progress_percent=10,
            pages_read=50,
            total_pages=500,
        )

        response = self.client.patch(
            "/books/book-1/progress",
            json={"status": "reading", "pages_read": 120},
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["Pages Read"], 120)
        self.assertEqual(payload["Read Status"], "to-read")
        self.assertEqual(payload["Progress (%)"], 24)

    def test_update_book_progress_auto_completes(self):
        _seed_book(
            title="Almost Done",
            authors="A",
            isbn_uid="book-2",
            progress_percent=90,
            pages_read=450,
            total_pages=500,
        )

        response = self.client.patch(
            "/books/book-2/progress",
            json={"status": "reading", "pages_read": 500},
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["Read Status"], "read")
        self.assertEqual(payload["Pages Read"], 500)
        self.assertEqual(payload["Progress (%)"], 100)

    def test_update_book_progress_rejects_pages_over_total(self):
        _seed_book(
            title="TBR",
            authors="A",
            isbn_uid="book-3",
            total_pages=500,
        )

        response = self.client.patch(
            "/books/book-3/progress",
            json={"status": "reading", "pages_read": 600},
        )

        self.assertEqual(response.status_code, 400)

    def test_update_book_progress_cannot_update_other_user_book(self):
        _seed_profile(
            user_id=OTHER_USER_ID,
            email="other@shelftxt.local",
            username="other",
        )

        _seed_book(
            title="Not Mine",
            authors="B",
            isbn_uid="not-mine",
            user_id=OTHER_USER_ID,
            total_pages=100,
        )

        response = self.client.patch(
            "/books/not-mine/progress",
            json={"status": "reading", "pages_read": 20},
        )

        self.assertEqual(response.status_code, 404)

    @patch(
        "backend.services.postgres_books.get_all_books",
        side_effect=AssertionError("clear should use direct scoped delete"),
    )
    def test_clear_library(self, mock_get_all_books):
        _seed_book(title="Gone", authors="A", isbn_uid="1")

        response = self.client.post("/books/clear", json={"confirm": True})

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"deleted": 1})
        mock_get_all_books.assert_not_called()

        payload = self.client.get("/books").json()
        self.assertEqual(payload["total"], 0)

    def test_clear_library_requires_confirm(self):
        response = self.client.post("/books/clear", json={"confirm": False})

        self.assertEqual(response.status_code, 400)

    def test_clear_library_only_clears_current_user_books(self):
        _seed_profile(
            user_id=OTHER_USER_ID,
            email="other@shelftxt.local",
            username="other",
        )

        _seed_book(title="Mine", authors="A", isbn_uid="mine")
        _seed_book(
            title="Not Mine",
            authors="B",
            isbn_uid="not-mine",
            user_id=OTHER_USER_ID,
        )

        response = self.client.post("/books/clear", json={"confirm": True})

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["deleted"], 1)

        db = TestingSessionLocal()
        try:
            current_user_books = (
                db.query(Book)
                .filter(Book.user_id == TEST_USER_ID)
                .all()
            )
            other_book = (
                db.query(Book)
                .filter(Book.user_id == OTHER_USER_ID)
                .filter(Book.isbn_uid == "not-mine")
                .first()
            )
        finally:
            db.close()

        self.assertEqual(current_user_books, [])
        self.assertIsNotNone(other_book)

    def test_clear_library_does_not_trigger_external_or_background_work(self):
        _seed_book(title="Gone", authors="A", isbn_uid="gone")

        with self.external_work_guard():
            response = self.client.post("/books/clear", json={"confirm": True})

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"deleted": 1})

    def test_import_skips_duplicate_title(self):
        _seed_book(
            title="Existing",
            authors="A",
            isbn_uid="1",
        )

        response = self.client.post(
            "/books/import",
            json={
                "books": [
                    {"title": "Existing", "author": "X"},
                    {"title": "New", "author": "Y"},
                ]
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["imported_count"], 1)
        self.assertEqual(response.json()["skipped_count"], 1)
        self.assertEqual(response.json()["duplicate_count"], 1)
        self.assertEqual(response.json()["skipped_duplicates"], 1)

        payload = self.client.get("/books").json()
        self.assertEqual(payload["total"], 2)

        titles = [book["Title"] for book in payload["results"]]
        self.assertIn("Existing", titles)
        self.assertIn("New", titles)

    def test_import_skips_if_no_books_added(self):
        _seed_book(
            title="Existing Book",
            authors="A",
            isbn_uid="existing-book",
        )

        response = self.client.post(
            "/books/import",
            json={"books": [{"title": "Existing Book", "author": "X"}]},
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["imported_count"], 0)
        self.assertEqual(response.json()["skipped_duplicates"], 1)

        payload = self.client.get("/books").json()
        self.assertEqual(payload["total"], 1)
        self.assertEqual(payload["results"][0]["Title"], "Existing Book")

    def test_import_adds_books_to_current_user(self):
        _seed_profile(
            user_id=OTHER_USER_ID,
            email="other@shelftxt.local",
            username="other",
        )

        response = self.client.post(
            "/books/import",
            json={"books": [{"title": "Imported Mine", "author": "A"}]},
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["imported_count"], 1)

        db = TestingSessionLocal()
        try:
            current_user_book = (
                db.query(Book)
                .filter(Book.user_id == TEST_USER_ID)
                .filter(Book.title == "Imported Mine")
                .first()
            )
            other_user_book = (
                db.query(Book)
                .filter(Book.user_id == OTHER_USER_ID)
                .filter(Book.title == "Imported Mine")
                .first()
            )
        finally:
            db.close()

        self.assertIsNotNone(current_user_book)
        self.assertIsNone(other_user_book)

    def test_import_does_not_trigger_external_or_background_work(self):
        with self.external_work_guard():
            response = self.client.post(
                "/books/import",
                json={"books": [{"title": "Imported", "author": "A"}]},
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["imported_count"], 1)

    @patch("backend.services.page_lookup.lookup_open_library_by_title", return_value=None)
    def test_import_star_rating_persists(self, mock_lookup_open_library_by_title):
        response = self.client.post(
            "/books/import",
            json={
                "books": [
                    {
                        "title": "The Great Gatsby",
                        "author": "F. Scott Fitzgerald",
                        "Star Rating": "4.00",
                    }
                ]
            },
        )

        self.assertEqual(response.status_code, 200)
        book = self.client.get("/books").json()["results"][0]
        self.assertEqual(book["Star Rating"], 4.0)
        mock_lookup_open_library_by_title.assert_not_called()

    @patch("backend.services.page_lookup.lookup_open_library_by_title", return_value=None)
    def test_import_rating_aliases_and_decimal_values_persist(self, mock_lookup_open_library_by_title):
        response = self.client.post(
            "/books/import",
            json={
                "books": [
                    {"title": "Rating A", "author": "A", "Star Rating": 5},
                    {"title": "Rating B", "author": "A", "star_rating": 5.0},
                    {"title": "Rating C", "author": "A", "rating": 4.75},
                    {"title": "Rating D", "author": "A", "Rating": "4.5"},
                    {"title": "Rating E", "author": "A", "Stars": "3.25"},
                    {"title": "Rating F", "author": "A", "My Rating": "2.5"},
                    {"title": "Rating G", "author": "A", "Star Rating": "0.25"},
                ]
            },
        )

        self.assertEqual(response.status_code, 200)
        books = {
            row["Title"]: row["Star Rating"]
            for row in self.client.get("/books?limit=100").json()["results"]
        }
        self.assertEqual(books["Rating A"], 5.0)
        self.assertEqual(books["Rating B"], 5.0)
        self.assertEqual(books["Rating C"], 4.75)
        self.assertEqual(books["Rating D"], 4.5)
        self.assertEqual(books["Rating E"], 3.25)
        self.assertEqual(books["Rating F"], 2.5)
        self.assertEqual(books["Rating G"], 0.25)
        mock_lookup_open_library_by_title.assert_not_called()

    @patch("backend.services.page_lookup.lookup_open_library_by_title", return_value=None)
    def test_import_empty_and_nan_ratings_become_none(self, mock_lookup_open_library_by_title):
        response = self.client.post(
            "/books/import",
            json={
                "books": [
                    {"title": "Empty Rating", "author": "A", "Star Rating": ""},
                    {"title": "Nan Rating", "author": "A", "Rating": "NaN"},
                ]
            },
        )

        self.assertEqual(response.status_code, 200)
        books = {
            row["Title"]: row["Star Rating"]
            for row in self.client.get("/books").json()["results"]
        }
        self.assertIsNone(books["Empty Rating"])
        self.assertIsNone(books["Nan Rating"])
        mock_lookup_open_library_by_title.assert_not_called()

    def test_import_rejects_negative_rating(self):
        response = self.client.post(
            "/books/import",
            json={"books": [{"title": "Negative Rating", "author": "A", "Star Rating": -0.25}]},
        )

        self.assertEqual(response.status_code, 422)

    def test_import_rejects_rating_above_five(self):
        response = self.client.post(
            "/books/import",
            json={"books": [{"title": "Too High Rating", "author": "A", "Star Rating": 5.25}]},
        )

        self.assertEqual(response.status_code, 422)

    @patch("backend.services.page_lookup.lookup_open_library_by_title")
    def test_import_accepts_authors_alias(self, mock_lookup_open_library_by_title):
        response = self.client.post(
            "/books/import",
            json={"books": [{"title": "Dune", "Authors": "Frank Herbert", "total_pages": 592}]},
        )

        self.assertEqual(response.status_code, 200)
        book = self.client.get("/books").json()["results"][0]
        self.assertEqual(book["Authors"], "Frank Herbert")
        self.assertEqual(book["Total Pages"], 592)
        mock_lookup_open_library_by_title.assert_not_called()

    @patch("backend.services.page_lookup.lookup_open_library_by_title")
    def test_import_title_only_uses_csv_fields(self, mock_lookup_open_library_by_title):
        response = self.client.post(
            "/books/import",
            json={"books": [{"title": "Dune"}]},
        )

        self.assertEqual(response.status_code, 200)
        book = self.client.get("/books").json()["results"][0]
        self.assertEqual(book["Authors"], "Unknown")
        self.assertIsNone(book["Total Pages"])
        mock_lookup_open_library_by_title.assert_not_called()

    @patch("backend.services.page_lookup.lookup_google_books_by_isbn")
    @patch("backend.services.page_lookup.lookup_open_library_by_isbn")
    def test_import_preserves_isbn_uid_without_metadata_lookup(
        self, mock_lookup_open_library_by_isbn, mock_lookup_google_books_by_isbn
    ):
        response = self.client.post(
            "/books/import",
            json={
                "books": [
                    {
                        "title": "Dune",
                        "author": "Frank Herbert",
                        "ISBN/UID": "9780441172719",
                        "total_pages": 592,
                    }
                ]
            },
        )

        self.assertEqual(response.status_code, 200)
        book = self.client.get("/books").json()["results"][0]
        self.assertEqual(book["ISBN/UID"], "9780441172719")
        self.assertEqual(book["Authors"], "Frank Herbert")
        self.assertEqual(book["Total Pages"], 592)
        self.assertIsNone(book["Description"])
        self.assertIsNone(book["Subjects"])
        self.assertIsNone(book["Genres"])
        self.assertIsNone(book["First Publish Year"])
        self.assertIsNone(book["metadata_source"])
        self.assertIsNone(book["metadata_enriched_at"])
        mock_lookup_open_library_by_isbn.assert_not_called()
        mock_lookup_google_books_by_isbn.assert_not_called()

    @patch(
        "backend.services.page_lookup.lookup_google_books_by_isbn",
        side_effect=GoogleBooksRateLimited("rate limited"),
    )
    @patch(
        "backend.services.page_lookup.lookup_open_library_by_isbn",
        side_effect=OpenLibraryTimeout("timeout"),
    )
    @patch(
        "backend.services.page_lookup.lookup_open_library_by_title",
        side_effect=RuntimeError("external API should not be called"),
    )
    def test_import_does_not_call_external_lookup_functions(
        self,
        mock_lookup_open_library_by_title,
        mock_lookup_open_library_by_isbn,
        mock_lookup_google_books_by_isbn,
    ):
        response = self.client.post(
            "/books/import",
            json={
                "books": [
                    {"title": "Fast Import", "author": "Author", "ISBN/UID": "9780000000001"}
                ]
            },
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["imported_count"], 1)
        self.assertEqual(payload["enriched_count"], 0)
        self.assertEqual(payload["enrichment_failed_count"], 0)
        self.assertEqual(payload["enrichment_skipped_count"], 0)
        mock_lookup_open_library_by_title.assert_not_called()
        mock_lookup_open_library_by_isbn.assert_not_called()
        mock_lookup_google_books_by_isbn.assert_not_called()

    @patch("backend.services.page_lookup.lookup_google_books_by_isbn")
    @patch("backend.services.page_lookup.lookup_open_library_by_isbn")
    def test_import_with_isbns_completes_without_enrichment(
        self, mock_lookup_open_library_by_isbn, mock_lookup_google_books_by_isbn
    ):
        response = self.client.post(
            "/books/import",
            json={
                "books": [
                    {"title": f"ISBN Book {i}", "ISBN/UID": f"978000000000{i}"}
                    for i in range(3)
                ]
            },
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["imported_count"], 3)
        self.assertEqual(payload["enriched_count"], 0)
        self.assertEqual(payload["enrichment_failed_count"], 0)
        mock_lookup_google_books_by_isbn.assert_not_called()
        mock_lookup_open_library_by_isbn.assert_not_called()

    @patch("backend.services.page_lookup.lookup_open_library_by_title")
    def test_import_unknown_author_does_not_lookup(
        self, mock_lookup_open_library_by_title
    ):
        response = self.client.post(
            "/books/import",
            json={"books": [{"title": "Dune", "author": "Unknown"}]},
        )

        self.assertEqual(response.status_code, 200)
        book = self.client.get("/books").json()["results"][0]
        self.assertEqual(book["Authors"], "Unknown")
        self.assertIsNone(book["Total Pages"])
        mock_lookup_open_library_by_title.assert_not_called()

    @patch("backend.services.page_lookup.lookup_open_library_by_title", side_effect=RuntimeError("boom"))
    def test_import_does_not_crash_when_external_api_is_down(
        self, mock_lookup_open_library_by_title
    ):
        response = self.client.post(
            "/books/import",
            json={"books": [{"title": "Dune", "read_status": "To Read"}]},
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["imported_count"], 1)
        self.assertEqual(response.json()["skipped_duplicates"], 0)
        self.assertEqual(response.json()["enrichment_failed_count"], 0)

        book = self.client.get("/books").json()["results"][0]
        self.assertEqual(book["Title"], "Dune")
        self.assertEqual(book["Authors"], "Unknown")
        self.assertIsNone(book["Total Pages"])
        mock_lookup_open_library_by_title.assert_not_called()

    @patch("backend.services.page_lookup.lookup_open_library_by_title")
    def test_bulk_import_does_not_lookup_metadata(
        self,
        mock_lookup_open_library_by_title,
    ):
        response = self.client.post(
            "/books/import",
            json={
                "books": [
                    {"title": f"Bulk Book {i}", "author": "Author"}
                    for i in range(100)
                ]
            },
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["imported_count"], 100)
        self.assertEqual(payload["enriched_count"], 0)
        self.assertEqual(payload["enrichment_skipped_count"], 0)
        self.assertEqual(payload["enrichment_failed_count"], 0)
        mock_lookup_open_library_by_title.assert_not_called()
        self.mock_page_count_http_get.assert_not_called()

    @patch("backend.services.page_lookup.lookup_open_library_by_title", return_value=None)
    def test_import_normalizes_read_to_completed(self, mock_lookup_open_library_by_title):
        response = self.client.post(
            "/books/import",
            json={"books": [{"title": "Read Book", "author": "A", "Read Status": "Read"}]},
        )

        self.assertEqual(response.status_code, 200)
        payload = self.client.get("/books").json()
        book = payload["results"][0]
        self.assertEqual(book["Read Status"], "read")
        self.assertEqual(book["Progress (%)"], 100)
        mock_lookup_open_library_by_title.assert_not_called()

    @patch("backend.services.page_lookup.lookup_open_library_by_title", return_value=None)
    def test_import_stores_last_date_read_from_slash_date(self, mock_lookup_open_library_by_title):
        response = self.client.post(
            "/books/import",
            json={
                "books": [
                    {
                        "title": "Dated Book",
                        "author": "A",
                        "Read Status": "Read",
                        "Last Date Read": "2025/02/02",
                    }
                ]
            },
        )

        self.assertEqual(response.status_code, 200)
        book = self.client.get("/books").json()["results"][0]
        self.assertEqual(book["Read Status"], "read")
        self.assertEqual(book["Last Date Read"], "2025-02-02")
        mock_lookup_open_library_by_title.assert_not_called()

    @patch("backend.services.page_lookup.lookup_open_library_by_title", return_value=None)
    def test_import_stores_last_date_read_from_us_date(self, mock_lookup_open_library_by_title):
        response = self.client.post(
            "/books/import",
            json={
                "books": [
                    {
                        "title": "US Dated Book",
                        "author": "A",
                        "read_status": "Finished",
                        "last_date_read": "02/03/2025",
                    }
                ]
            },
        )

        self.assertEqual(response.status_code, 200)
        book = self.client.get("/books").json()["results"][0]
        self.assertEqual(book["Read Status"], "read")
        self.assertEqual(book["Last Date Read"], "2025-02-03")
        self.assertEqual(book["End Date"], "2025-02-03")
        mock_lookup_open_library_by_title.assert_not_called()

    @patch("backend.services.page_lookup.lookup_open_library_by_title", return_value=None)
    def test_import_preserves_start_and_end_dates(self, mock_lookup_open_library_by_title):
        response = self.client.post(
            "/books/import",
            json={
                "books": [
                    {
                        "title": "Dated Range",
                        "author": "A",
                        "read_status": "Read",
                        "Start Date": "2026-01-05",
                        "End Date": "01/12/2026",
                    }
                ]
            },
        )

        self.assertEqual(response.status_code, 200)
        book = self.client.get("/books").json()["results"][0]
        self.assertEqual(book["Start Date"], "2026-01-05")
        self.assertEqual(book["End Date"], "2026-01-12")
        mock_lookup_open_library_by_title.assert_not_called()

    @patch("backend.services.page_lookup.lookup_open_library_by_title", return_value=None)
    def test_import_accepts_blank_reading_dates(self, mock_lookup_open_library_by_title):
        response = self.client.post(
            "/books/import",
            json={
                "books": [
                    {
                        "title": "Blank Dates",
                        "author": "A",
                        "read_status": "To Read",
                        "Start Date": "",
                        "End Date": "",
                    }
                ]
            },
        )

        self.assertEqual(response.status_code, 200)
        book = self.client.get("/books").json()["results"][0]
        self.assertIsNone(book["Start Date"])
        self.assertIsNone(book["End Date"])
        mock_lookup_open_library_by_title.assert_not_called()

    @patch("backend.services.page_lookup.lookup_open_library_by_title", return_value=None)
    def test_import_rejects_start_date_after_end_date(self, mock_lookup_open_library_by_title):
        response = self.client.post(
            "/books/import",
            json={
                "books": [
                    {
                        "title": "Bad Dates",
                        "author": "A",
                        "read_status": "Read",
                        "start_date": "2026-02-01",
                        "end_date": "2026-01-01",
                    }
                ]
            },
        )

        self.assertEqual(response.status_code, 400)
        mock_lookup_open_library_by_title.assert_not_called()

    @patch("backend.services.page_lookup.lookup_open_library_by_title", return_value=None)
    def test_import_normalizes_completed_to_completed(self, mock_lookup_open_library_by_title):
        response = self.client.post(
            "/books/import",
            json={
                "books": [
                    {
                        "title": "Completed Book",
                        "author": "A",
                        "status": "Completed",
                        "total_pages": 321,
                    }
                ]
            },
        )

        self.assertEqual(response.status_code, 200)
        book = self.client.get("/books").json()["results"][0]
        self.assertEqual(book["Read Status"], "read")
        self.assertEqual(book["Pages Read"], 321)
        self.assertEqual(book["Progress (%)"], 100)
        mock_lookup_open_library_by_title.assert_not_called()

    def test_import_completed_without_total_pages_does_not_crash(self):
        response = self.client.post(
            "/books/import",
            json={"books": [{"title": "Completed No Pages", "author": "A", "status": "Completed"}]},
        )

        self.assertEqual(response.status_code, 200)
        book = self.client.get("/books").json()["results"][0]
        self.assertEqual(book["Read Status"], "read")
        self.assertEqual(book["Pages Read"], 0)
        self.assertEqual(book["Progress (%)"], 100)

    @patch("backend.services.page_lookup.lookup_open_library_by_title", return_value=None)
    def test_import_normalizes_finished_to_completed(self, mock_lookup_open_library_by_title):
        response = self.client.post(
            "/books/import",
            json={"books": [{"title": "Finished Book", "author": "A", "read_status": "Finished"}]},
        )

        self.assertEqual(response.status_code, 200)
        book = self.client.get("/books").json()["results"][0]
        self.assertEqual(book["Read Status"], "read")
        self.assertEqual(book["Progress (%)"], 100)
        mock_lookup_open_library_by_title.assert_not_called()

    @patch("backend.services.page_lookup.lookup_open_library_by_title")
    def test_import_normalizes_reading_to_reading(self, mock_lookup_open_library_by_title):
        response = self.client.post(
            "/books/import",
            json={
                "books": [
                    {
                        "title": "Reading Book",
                        "author": "A",
                        "read_status": "Reading",
                        "pages_read": 75,
                        "total_pages": 300,
                    }
                ]
            },
        )

        self.assertEqual(response.status_code, 200)
        book = self.client.get("/books").json()["results"][0]
        self.assertEqual(book["Read Status"], "to-read")
        self.assertEqual(book["Pages Read"], 75)
        self.assertEqual(book["Total Pages"], 300)
        self.assertEqual(book["Progress (%)"], 25)
        mock_lookup_open_library_by_title.assert_not_called()

    @patch("backend.services.page_lookup.lookup_open_library_by_title", return_value=None)
    def test_import_normalizes_to_read_to_not_started(self, mock_lookup_open_library_by_title):
        response = self.client.post(
            "/books/import",
            json={"books": [{"title": "Unread Book", "author": "A", "Read Status": "To Read"}]},
        )

        self.assertEqual(response.status_code, 200)
        book = self.client.get("/books").json()["results"][0]
        self.assertEqual(book["Read Status"], "to-read")
        self.assertEqual(book["Pages Read"], 0)
        self.assertEqual(book["Progress (%)"], 0)
        mock_lookup_open_library_by_title.assert_not_called()

    def test_import_to_read_defaults_to_zero_progress(self):
        response = self.client.post(
            "/books/import",
            json={"books": [{"title": "Default TBR", "author": "A", "read_status": "Unread", "total_pages": 250}]},
        )

        self.assertEqual(response.status_code, 200)
        book = self.client.get("/books").json()["results"][0]
        self.assertEqual(book["Read Status"], "to-read")
        self.assertEqual(book["Pages Read"], 0)
        self.assertEqual(book["Progress (%)"], 0)

    @patch("backend.services.page_lookup.lookup_open_library_by_title")
    def test_import_missing_page_count_stays_empty(self, mock_lookup_open_library_by_title):
        response = self.client.post(
            "/books/import",
            json={"books": [{"title": "Needs Pages", "author": "A"}]},
        )

        self.assertEqual(response.status_code, 200)
        book = self.client.get("/books").json()["results"][0]
        self.assertIsNone(book["Total Pages"])
        mock_lookup_open_library_by_title.assert_not_called()

    @patch("backend.services.page_lookup.lookup_open_library_by_title", return_value=None)
    def test_import_without_page_count_does_not_lookup(self, mock_lookup_open_library_by_title):
        response = self.client.post(
            "/books/import",
            json={"books": [{"title": "No Pages Found", "author": "A"}]},
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["imported_count"], 1)
        self.assertEqual(response.json()["skipped_duplicates"], 0)
        self.assertEqual(response.json()["enrichment_failed_count"], 0)
        book = self.client.get("/books").json()["results"][0]
        self.assertIsNone(book["Total Pages"])
        mock_lookup_open_library_by_title.assert_not_called()

    def test_metadata_status_counts_current_user_genres(self):
        _seed_profile(
            user_id=OTHER_USER_ID,
            email="other@shelftxt.local",
            username="other",
        )
        _seed_book(title="With Genre", authors="A", isbn_uid="with-genre", genres=["fiction"])
        _seed_book(title="Without Genre", authors="A", isbn_uid="without-genre")
        _seed_book(
            title="Other Genre",
            authors="B",
            isbn_uid="other-genre",
            user_id=OTHER_USER_ID,
            genres=["history"],
        )

        response = self.client.get("/metadata/status")

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["books_with_genres"], 1)
        self.assertEqual(payload["total_books"], 2)
        self.assertEqual(payload["job"]["status"], "completed")

    @patch("backend.routes.metadata.process_metadata_job")
    def test_metadata_generate_creates_user_job_without_blocking(self, mock_process_metadata_job):
        _seed_book(title="Needs Genre", authors="A", isbn_uid="needs-genre")
        _seed_book(title="Has Genre", authors="A", isbn_uid="has-genre", genres=["fiction"])

        response = self.client.post("/metadata/generate")

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["books_with_genres"], 1)
        self.assertEqual(payload["total_books"], 2)
        self.assertEqual(payload["job"]["status"], "pending")
        self.assertEqual(payload["job"]["processed_count"], 0)
        self.assertEqual(payload["job"]["total_count"], 1)
        mock_process_metadata_job.assert_called_once()

    @patch("backend.services.metadata_jobs.get_session_local", return_value=TestingSessionLocal)
    @patch("backend.services.metadata_jobs.page_lookup.lookup_book_metadata")
    def test_metadata_job_processes_only_current_user_missing_genres(self, mock_lookup, _mock_session):
        _seed_profile(
            user_id=OTHER_USER_ID,
            email="other@shelftxt.local",
            username="other",
        )
        current = _seed_book(title="Needs Genre", authors="A", isbn_uid="needs-genre")
        _seed_book(title="Already Done", authors="A", isbn_uid="has-genre", genres=["fiction"])
        other = _seed_book(
            title="Other Missing",
            authors="B",
            isbn_uid="other-missing",
            user_id=OTHER_USER_ID,
        )
        mock_lookup.return_value = BookMetadata(genres=["science fiction"])

        db = TestingSessionLocal()
        try:
            job = MetadataJob(user_id=TEST_USER_ID, status="pending", total_count=1)
            db.add(job)
            db.commit()
            job_id = job.id
        finally:
            db.close()

        from backend.services.metadata_jobs import process_metadata_job

        process_metadata_job(job_id)

        db = TestingSessionLocal()
        try:
            updated_current = db.get(Book, current.id)
            untouched_other = db.get(Book, other.id)
            completed_job = db.get(MetadataJob, job_id)
            self.assertEqual(updated_current.genres, ["science fiction"])
            self.assertIsNone(untouched_other.genres)
            self.assertEqual(completed_job.status, "completed")
            self.assertEqual(completed_job.processed_count, 1)
        finally:
            db.close()

    def test_export_library_csv(self):
        _seed_book(
            title="Export Me",
            authors="Author",
            isbn_uid="1",
            total_pages=100,
        )

        response = self.client.get("/books/export")

        self.assertEqual(response.status_code, 200)
        self.assertIn("text/csv", response.headers.get("content-type", ""))
        self.assertIn("Export Me", response.text)
        self.assertIn("Author", response.text)
        self.assertIn("ISBN/UID", response.text)
        self.assertIn("Start Date", response.text)
        self.assertIn("End Date", response.text)

    @patch("backend.services.page_lookup.lookup_open_library_by_title", return_value=None)
    def test_export_import_round_trip_preserves_reading_dates(self, mock_lookup_open_library_by_title):
        _seed_book(
            title="Round Trip",
            authors="Author",
            isbn_uid="round-trip",
            read_status="read",
            start_date="2026-01-05",
            end_date="2026-01-12",
            last_date_read="2026-01-12",
            total_pages=100,
        )

        exported = self.client.get("/books/export")
        self.assertEqual(exported.status_code, 200)
        self.client.post("/books/clear", json={"confirm": True})

        import csv
        from io import StringIO

        rows = list(csv.DictReader(StringIO(exported.text)))
        response = self.client.post("/books/import", json={"books": rows})

        self.assertEqual(response.status_code, 200)
        book = self.client.get("/books").json()["results"][0]
        self.assertEqual(book["Start Date"], "2026-01-05")
        self.assertEqual(book["End Date"], "2026-01-12")
        mock_lookup_open_library_by_title.assert_not_called()

    def test_export_only_exports_current_user_books(self):
        _seed_profile(
            user_id=OTHER_USER_ID,
            email="other@shelftxt.local",
            username="other",
        )

        _seed_book(title="Mine", authors="A", isbn_uid="mine")
        _seed_book(
            title="Not Mine",
            authors="B",
            isbn_uid="not-mine",
            user_id=OTHER_USER_ID,
        )

        response = self.client.get("/books/export")

        self.assertEqual(response.status_code, 200)
        self.assertIn("Mine", response.text)
        self.assertNotIn("Not Mine", response.text)

    @patch("backend.routes.recommendation.get_recommendation")
    def test_recommend_returns_structured_payload(self, mock_get_recommendation):
        mock_get_recommendation.return_value = [
            {
                "recommended_book": {
                    "id": "1",
                    "title": "Snow Crash",
                    "author": "Neal Stephenson",
                },
                "book": {
                    "id": "1",
                    "title": "Snow Crash",
                    "author": "Neal Stephenson",
                },
                "score": 0.93,
                "reason": "Shares cyberpunk with Neuromancer, which you rated 5★.",
                "explanation": "Recommended because you rated Neal Stephenson highly.",
                "matched_genres": ["cyberpunk"],
                "matched_subjects": [],
                "matched_authors": ["Neal Stephenson"],
                "matched_liked_books": [
                    {"id": "2", "title": "Cryptonomicon", "author": "Neal Stephenson", "rating": 5}
                ],
                "score_breakdown": {"overall": 0.93},
                "similar_books": [
                    {"id": "2", "title": "Cryptonomicon", "author": "Neal Stephenson"}
                ],
            }
        ]

        response = self.client.get("/recommend")

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertIsInstance(payload, list)
        self.assertEqual(payload[0]["book"]["title"], "Snow Crash")
        self.assertEqual(payload[0]["recommended_book"]["title"], "Snow Crash")
        self.assertIn("reason", payload[0])
        self.assertEqual(payload[0]["matched_genres"], ["cyberpunk"])
        self.assertEqual(payload[0]["matched_liked_books"][0]["title"], "Cryptonomicon")
        self.assertIn("explanation", payload[0])
        self.assertIn("similar_books", payload[0])

        self.assertEqual(mock_get_recommendation.call_count, 1)
        self.assertEqual(mock_get_recommendation.call_args.args[1], TEST_USER_ID)
        self.assertEqual(mock_get_recommendation.call_args.kwargs["style"], "balanced")
        self.assertEqual(mock_get_recommendation.call_args.kwargs["refresh"], False)
        self.assertEqual(mock_get_recommendation.call_args.kwargs["exclude_ids"], set())

    @patch("backend.routes.recommendation.get_recommendation")
    def test_recommend_refresh_passes_refresh_flag(self, mock_get_recommendation):
        mock_get_recommendation.return_value = []

        response = self.client.get("/recommend?style=balanced&refresh=true&exclude_ids=1,2,,3")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(mock_get_recommendation.call_count, 1)
        self.assertEqual(mock_get_recommendation.call_args.kwargs["refresh"], True)
        self.assertEqual(mock_get_recommendation.call_args.kwargs["exclude_ids"], {"1", "2", "3"})

    @patch("backend.routes.recommendation.get_recommendation")
    def test_recommend_returns_empty_when_no_pick(self, mock_get_recommendation):
        mock_get_recommendation.return_value = []

        response = self.client.get("/recommend")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), [])

        self.assertEqual(mock_get_recommendation.call_count, 1)
        self.assertEqual(mock_get_recommendation.call_args.args[1], TEST_USER_ID)
        self.assertEqual(mock_get_recommendation.call_args.kwargs["style"], "balanced")

    def test_recommendation_empty_state_returns_empty_list(self):
        db = TestingSessionLocal()
        try:
            result = get_recommendation(
                db,
                TEST_USER_ID,
                style="balanced",
            )
        finally:
            db.close()

        self.assertEqual(result, [])

    def test_recommendation_only_uses_current_user_books(self):
        _seed_profile(
            user_id=OTHER_USER_ID,
            email="other@shelftxt.local",
            username="other",
        )

        _seed_book(
            title="Other User Book",
            authors="Other Author",
            isbn_uid="other-book",
            user_id=OTHER_USER_ID,
            read_status="to-read",
            total_pages=300,
        )

        db = TestingSessionLocal()
        try:
            result = get_recommendation(
                db,
                TEST_USER_ID,
                style="balanced",
            )
        finally:
            db.close()

        self.assertEqual(result, [])

    def test_recommendation_falls_back_when_metadata_is_missing(self):
        _seed_book(
            title="Rated Book",
            authors="Author A",
            isbn_uid="rated-book",
            read_status="read",
            star_rating=4.5,
            total_pages=300,
        )
        _seed_book(
            title="Candidate Book",
            authors="Author B",
            isbn_uid="candidate-book",
            read_status="to-read",
            total_pages=250,
        )

        db = TestingSessionLocal()
        try:
            result = get_recommendation(db, TEST_USER_ID, style="balanced")
        finally:
            db.close()

        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["book"]["title"], "Candidate Book")
        self.assertEqual(result[0]["recommended_book"]["title"], "Candidate Book")
        self.assertIn("reason", result[0])
        self.assertEqual(
            result[0]["reason"],
            "Genre metadata has not been generated yet, so this uses rating and author signals only.",
        )

    def test_recommend_endpoint_does_not_trigger_external_or_background_work(self):
        _seed_book(
            title="Read Book",
            authors="Author",
            isbn_uid="read-book",
            read_status="read",
            star_rating=5,
            total_pages=300,
            subjects=["space"],
            genres=["science fiction"],
        )
        _seed_book(
            title="Unread Book",
            authors="Author",
            isbn_uid="unread-book",
            read_status="to-read",
            total_pages=250,
            subjects=["space"],
            genres=["science fiction"],
        )

        with self.external_work_guard():
            response = self.client.get("/recommend?refresh=true")

        self.assertEqual(response.status_code, 200)
        self.assertIsInstance(response.json(), list)

    @patch(
        "backend.services.page_lookup.httpx.get",
        side_effect=AssertionError("metadata HTTP call in recommendation test"),
    )
    @patch(
        "backend.services.page_count_lookup.httpx.get",
        side_effect=AssertionError("page-count HTTP call in recommendation test"),
    )
    @patch(
        "backend.services.page_count_lookup.backfill_missing_page_counts",
        side_effect=AssertionError("background backfill in recommendation test"),
    )
    def test_recommendation_makes_no_external_lookup_requests(
        self,
        mock_backfill,
        mock_page_count_http,
        mock_metadata_http,
    ):
        _seed_book(
            title="Read Book",
            authors="Author",
            isbn_uid="read-book",
            read_status="read",
            star_rating=5,
            total_pages=300,
            subjects=["space"],
            genres=["science fiction"],
        )
        _seed_book(
            title="Unread Book",
            authors="Author",
            isbn_uid="unread-book",
            read_status="to-read",
            total_pages=250,
            subjects=["space"],
            genres=["science fiction"],
        )

        db = TestingSessionLocal()
        try:
            result = get_recommendation(db, TEST_USER_ID, style="balanced")
        finally:
            db.close()

        self.assertGreaterEqual(len(result), 1)
        mock_backfill.assert_not_called()
        mock_page_count_http.assert_not_called()
        mock_metadata_http.assert_not_called()


if __name__ == "__main__":
    unittest.main()
