import unittest
from unittest.mock import patch
from uuid import UUID

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from backend import api
from backend.auth.dependencies import get_current_user
from backend.db.database import Base, get_db
from backend.db.models import Book, Profile
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
    progress_percent=0,
    pages_read=0,
    total_pages=None,
):
    db = TestingSessionLocal()
    book = Book(
        title=title,
        authors=authors,
        isbn_uid=isbn_uid,
        user_id=user_id,
        read_status=read_status,
        star_rating=star_rating,
        last_date_read=last_date_read,
        progress_percent=progress_percent,
        pages_read=pages_read,
        total_pages=total_pages,
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
        self.client = TestClient(api.app)

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
        self.assertIn("author", import_row_properties)
        self.assertIn("total_pages", import_row_properties)
        self.assertIn("read_status", import_row_properties)
        self.assertIn("pages_read", import_row_properties)
        self.assertIn("progress_percent", import_row_properties)

        example_row = schema["ImportBooks"]["examples"][0]["books"][0]
        self.assertEqual(example_row["read_status"], "reading")
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

    def test_clear_library(self):
        _seed_book(title="Gone", authors="A", isbn_uid="1")

        response = self.client.post("/books/clear", json={"confirm": True})

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["deleted"], 1)

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
        self.assertEqual(response.json(), {"imported": 1, "skipped": 1})

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
        self.assertEqual(response.json()["imported"], 0)
        self.assertEqual(response.json()["skipped"], 1)

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
        self.assertEqual(response.json()["imported"], 1)

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

    @patch("backend.services.postgres_books.lookup_author_name", return_value=None)
    @patch("backend.services.postgres_books.lookup_total_pages", return_value=592)
    def test_import_accepts_authors_alias(self, mock_lookup_total_pages, mock_lookup_author_name):
        response = self.client.post(
            "/books/import",
            json={"books": [{"title": "Dune", "Authors": "Frank Herbert"}]},
        )

        self.assertEqual(response.status_code, 200)
        book = self.client.get("/books").json()["results"][0]
        self.assertEqual(book["Authors"], "Frank Herbert")
        self.assertEqual(book["Total Pages"], 592)
        mock_lookup_total_pages.assert_called_once_with("Dune", "Frank Herbert")
        mock_lookup_author_name.assert_not_called()

    @patch("backend.services.postgres_books.lookup_author_name", return_value="Frank Herbert")
    @patch("backend.services.postgres_books.lookup_total_pages", return_value=592)
    def test_import_title_only_enriches_pages_and_author(
        self, mock_lookup_total_pages, mock_lookup_author_name
    ):
        response = self.client.post(
            "/books/import",
            json={"books": [{"title": "Dune"}]},
        )

        self.assertEqual(response.status_code, 200)
        book = self.client.get("/books").json()["results"][0]
        self.assertEqual(book["Authors"], "Frank Herbert")
        self.assertEqual(book["Total Pages"], 592)
        mock_lookup_total_pages.assert_called_once_with("Dune", None)
        mock_lookup_author_name.assert_called_once_with("Dune")

    @patch("backend.services.postgres_books.lookup_author_name", return_value=None)
    @patch("backend.services.postgres_books.lookup_total_pages", return_value=592)
    def test_import_unknown_author_uses_authorless_lookup(
        self, mock_lookup_total_pages, mock_lookup_author_name
    ):
        response = self.client.post(
            "/books/import",
            json={"books": [{"title": "Dune", "author": "Unknown"}]},
        )

        self.assertEqual(response.status_code, 200)
        book = self.client.get("/books").json()["results"][0]
        self.assertEqual(book["Authors"], "Unknown")
        self.assertEqual(book["Total Pages"], 592)
        mock_lookup_total_pages.assert_called_once_with("Dune", None)
        mock_lookup_author_name.assert_called_once_with("Dune")

    @patch("backend.services.postgres_books.lookup_total_pages", return_value=None)
    def test_import_normalizes_read_to_completed(self, mock_lookup_total_pages):
        response = self.client.post(
            "/books/import",
            json={"books": [{"title": "Read Book", "author": "A", "Read Status": "Read"}]},
        )

        self.assertEqual(response.status_code, 200)
        payload = self.client.get("/books").json()
        book = payload["results"][0]
        self.assertEqual(book["Read Status"], "read")
        self.assertEqual(book["Progress (%)"], 100)
        mock_lookup_total_pages.assert_called_once()

    @patch("backend.services.postgres_books.lookup_total_pages", return_value=None)
    def test_import_normalizes_completed_to_completed(self, mock_lookup_total_pages):
        response = self.client.post(
            "/books/import",
            json={"books": [{"title": "Completed Book", "author": "A", "status": "Completed"}]},
        )

        self.assertEqual(response.status_code, 200)
        book = self.client.get("/books").json()["results"][0]
        self.assertEqual(book["Read Status"], "read")
        self.assertEqual(book["Progress (%)"], 100)
        mock_lookup_total_pages.assert_called_once()

    @patch("backend.services.postgres_books.lookup_total_pages", return_value=None)
    def test_import_normalizes_finished_to_completed(self, mock_lookup_total_pages):
        response = self.client.post(
            "/books/import",
            json={"books": [{"title": "Finished Book", "author": "A", "read_status": "Finished"}]},
        )

        self.assertEqual(response.status_code, 200)
        book = self.client.get("/books").json()["results"][0]
        self.assertEqual(book["Read Status"], "read")
        self.assertEqual(book["Progress (%)"], 100)
        mock_lookup_total_pages.assert_called_once()

    @patch("backend.services.postgres_books.lookup_total_pages", return_value=300)
    def test_import_normalizes_reading_to_reading(self, mock_lookup_total_pages):
        response = self.client.post(
            "/books/import",
            json={
                "books": [
                    {
                        "title": "Reading Book",
                        "author": "A",
                        "read_status": "Reading",
                        "pages_read": 75,
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
        mock_lookup_total_pages.assert_called_once()

    @patch("backend.services.postgres_books.lookup_total_pages", return_value=None)
    def test_import_normalizes_to_read_to_not_started(self, mock_lookup_total_pages):
        response = self.client.post(
            "/books/import",
            json={"books": [{"title": "Unread Book", "author": "A", "Read Status": "To Read"}]},
        )

        self.assertEqual(response.status_code, 200)
        book = self.client.get("/books").json()["results"][0]
        self.assertEqual(book["Read Status"], "to-read")
        self.assertEqual(book["Pages Read"], 0)
        self.assertEqual(book["Progress (%)"], 0)
        mock_lookup_total_pages.assert_called_once()

    @patch("backend.services.postgres_books.lookup_total_pages", return_value=412)
    def test_import_missing_page_count_triggers_lookup(self, mock_lookup_total_pages):
        response = self.client.post(
            "/books/import",
            json={"books": [{"title": "Needs Pages", "author": "A"}]},
        )

        self.assertEqual(response.status_code, 200)
        book = self.client.get("/books").json()["results"][0]
        self.assertEqual(book["Total Pages"], 412)
        mock_lookup_total_pages.assert_called_once_with("Needs Pages", "A")

    @patch("backend.services.postgres_books.lookup_total_pages", return_value=None)
    def test_import_failed_page_count_lookup_does_not_crash(self, mock_lookup_total_pages):
        response = self.client.post(
            "/books/import",
            json={"books": [{"title": "No Pages Found", "author": "A"}]},
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"imported": 1, "skipped": 0})
        book = self.client.get("/books").json()["results"][0]
        self.assertIsNone(book["Total Pages"])
        mock_lookup_total_pages.assert_called_once_with("No Pages Found", "A")

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
                "book": {
                    "id": "1",
                    "title": "Snow Crash",
                    "author": "Neal Stephenson",
                },
                "score": 0.93,
                "explanation": "Recommended because you rated Neal Stephenson highly.",
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
        self.assertIn("explanation", payload[0])
        self.assertIn("similar_books", payload[0])

        self.assertEqual(mock_get_recommendation.call_count, 1)
        self.assertEqual(mock_get_recommendation.call_args.args[1], TEST_USER_ID)
        self.assertEqual(mock_get_recommendation.call_args.kwargs["style"], "balanced")

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


if __name__ == "__main__":
    unittest.main()
