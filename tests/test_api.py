import unittest
from unittest.mock import patch

import numpy as np
import pandas as pd
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from backend import api
from backend.book_data import BOOKS_COLUMNS
from backend.db.database import Base, get_db
from backend.db.models import Book


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


api.app.dependency_overrides[get_db] = override_get_db


def _seed_book(
    *,
    title="Book",
    authors="Author",
    isbn_uid="book-1",
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
            json={"status": "reading", "pages_read": 500, "rating": 5},
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
        mock_get_recommendation.assert_called_once_with(style="balanced")

    @patch("backend.routes.recommendation.get_recommendation")
    def test_recommend_returns_empty_when_no_pick(self, mock_get_recommendation):
        mock_get_recommendation.return_value = []

        response = self.client.get("/recommend")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), [])
        mock_get_recommendation.assert_called_once_with(style="balanced")

    @patch("backend.services.books.invalidate_recommendation_cache")
    @patch("backend.services.books.save_books")
    @patch("backend.services.books.get_all_books")
    def test_export_library_csv(self, mock_get_all, mock_save, mock_invalidate):
        mock_get_all.return_value = pd.DataFrame(
            [
                {
                    "Title": "Export Me",
                    "Authors": "Author",
                    "ISBN/UID": "1",
                    "Read Status": "to-read",
                    "Star Rating": np.nan,
                    "Last Date Read": None,
                    "Progress (%)": 0,
                    "Pages Read": 0,
                    "Total Pages": 100,
                }
            ],
            columns=BOOKS_COLUMNS,
        )

        response = self.client.get("/books/export")

        self.assertEqual(response.status_code, 200)
        self.assertIn("text/csv", response.headers.get("content-type", ""))
        self.assertIn("Export Me", response.text)

    @patch("backend.services.books.save_books")
    @patch("backend.services.books.get_all_books")
    def test_import_skips_duplicate_title(self, mock_load_data, mock_save_data):
        base_df = pd.DataFrame(
            [
                {
                    "Title": "Existing",
                    "Authors": "A",
                    "ISBN/UID": "1",
                    "Read Status": "to-read",
                    "Star Rating": np.nan,
                    "Last Date Read": None,
                    "Progress (%)": 0,
                    "Pages Read": 0,
                    "Total Pages": None,
                }
            ],
            columns=BOOKS_COLUMNS,
        )
        mock_load_data.return_value = base_df

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
        saved = mock_save_data.call_args.args[0]
        self.assertEqual(len(saved), 2)

    @patch("backend.services.books.invalidate_recommendation_cache")
    @patch("backend.services.books.save_books")
    @patch("backend.services.books.get_all_books")
    def test_import_skips_invalidation_if_no_books_added(
        self,
        mock_get_all,
        mock_save,
        mock_invalidate,
    ):
        mock_get_all.return_value = pd.DataFrame([{"Title": "Existing Book"}])

        response = self.client.post(
            "/books/import",
            json={"books": [{"title": "Existing Book", "author": "X"}]},
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["imported"], 0)

        mock_save.assert_not_called()
        mock_invalidate.assert_not_called()


if __name__ == "__main__":
    unittest.main()