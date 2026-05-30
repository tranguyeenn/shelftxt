import unittest
from unittest.mock import patch

import numpy as np
import pandas as pd
from fastapi.testclient import TestClient

from backend import api
from backend.book_data import BOOKS_COLUMNS


def _sample_library_df(count: int) -> pd.DataFrame:
    rows = []
    for i in range(count):
        rows.append(
            {
                "Title": f"Book {i}",
                "Authors": f"Author {i}",
                "ISBN/UID": f"id-{i}",
                "Read Status": "to-read",
                "Star Rating": np.nan,
                "Last Date Read": None,
                "Progress (%)": 0,
                "Pages Read": 0,
                "Total Pages": None,
            }
        )
    return pd.DataFrame(rows, columns=BOOKS_COLUMNS)


class ApiTests(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(api.app)

    @patch("backend.routes.books.load_data")
    def test_get_books_default_pagination(self, mock_load_data):
        mock_load_data.return_value = _sample_library_df(25)

        response = self.client.get("/books")

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["page"], 1)
        self.assertEqual(payload["limit"], 20)
        self.assertEqual(payload["total"], 25)
        self.assertEqual(len(payload["results"]), 20)
        self.assertEqual(payload["results"][0]["Title"], "Book 0")
        self.assertEqual(payload["results"][-1]["Title"], "Book 19")

    @patch("backend.routes.books.load_data")
    def test_get_books_explicit_page_and_limit(self, mock_load_data):
        mock_load_data.return_value = _sample_library_df(12)

        response = self.client.get("/books?page=2&limit=5")

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["page"], 2)
        self.assertEqual(payload["limit"], 5)
        self.assertEqual(payload["total"], 12)
        self.assertEqual(len(payload["results"]), 5)
        self.assertEqual([row["Title"] for row in payload["results"]], [
            "Book 5",
            "Book 6",
            "Book 7",
            "Book 8",
            "Book 9",
        ])

    @patch("backend.routes.books.load_data")
    def test_get_books_page_past_end_returns_empty_results(self, mock_load_data):
        mock_load_data.return_value = _sample_library_df(3)

        response = self.client.get("/books?page=10&limit=5")

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["total"], 3)
        self.assertEqual(payload["results"], [])

    @patch("backend.routes.books.load_data")
    def test_get_books_rejects_invalid_query_params(self, mock_load_data):
        mock_load_data.return_value = _sample_library_df(1)

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

    @patch("backend.services.books.save_books")
    @patch("backend.services.books.get_all_books")
    @patch("backend.services.books.invalidate_recommendation_cache")
    def test_add_book_appends_new_tbr_row(self, mock_invalidate_recommendation_cache, mock_load_data, mock_save_data):
        base_df = pd.DataFrame(
            [
                {
                    "Title": "Existing",
                    "Authors": "Author A",
                    "ISBN/UID": "1",
                    "Read Status": "to-read",
                    "Star Rating": np.nan,
                    "Last Date Read": None,
                    "Progress (%)": 0,
                    "Pages Read": 0,
                    "Total Pages": None,
                }
            ]
        )
        mock_load_data.return_value = base_df

        response = self.client.post(
            "/books",
            json={"title": "New Book", "author": "New Author"},
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"message": "Book added"})
        self.assertTrue(mock_save_data.called)
        mock_invalidate_recommendation_cache.assert_called_once()
        saved_df = mock_save_data.call_args.args[0]
        self.assertEqual(len(saved_df), 2)
        self.assertEqual(saved_df.iloc[-1]["Title"], "New Book")
        self.assertEqual(saved_df.iloc[-1]["Authors"], "New Author")
        self.assertEqual(saved_df.iloc[-1]["Read Status"], "to-read")

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

    @patch("backend.services.books.save_books")
    @patch("backend.services.books.get_all_books")
    def test_delete_book_removes_row(self, mock_get_all_books, mock_save_books):
        base_df = pd.DataFrame(
            [
                {
                    "Title": "Keep",
                    "Authors": "Author A",
                    "ISBN/UID": "1",
                    "Read Status": "to-read",
                    "Star Rating": np.nan,
                    "Last Date Read": None,
                    "Progress (%)": 0,
                    "Pages Read": 0,
                    "Total Pages": None,
                },
                {
                    "Title": "Remove",
                    "Authors": "Author B",
                    "ISBN/UID": "2",
                    "Read Status": "to-read",
                    "Star Rating": np.nan,
                    "Last Date Read": None,
                    "Progress (%)": 0,
                    "Pages Read": 0,
                    "Total Pages": None,
                },
            ]
        )
        mock_get_all_books.return_value = base_df

        response = self.client.delete("/books?title=Remove")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"message": "Book deleted"})
        saved_df = mock_save_books.call_args.args[0]
        self.assertEqual(len(saved_df), 1)
        self.assertEqual(saved_df.iloc[0]["Title"], "Keep")

    @patch("backend.services.books.invalidate_recommendation_cache")
    @patch("backend.services.books.save_books")
    @patch("backend.services.books.get_all_books")
    def test_update_book_progress_by_id(
        self, mock_get_all_books, mock_save_books, mock_invalidate
    ):
        base_df = pd.DataFrame(
            [
                {
                    "Title": "In Progress",
                    "Authors": "A",
                    "ISBN/UID": "book-1",
                    "Read Status": "to-read",
                    "Star Rating": np.nan,
                    "Last Date Read": None,
                    "Progress (%)": 10,
                    "Pages Read": 50,
                    "Total Pages": 500,
                }
            ]
        )
        mock_get_all_books.return_value = base_df

        response = self.client.patch(
            "/books/book-1/progress",
            json={"status": "reading", "pages_read": 120},
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["book"]["pages_read"], 120)
        self.assertEqual(payload["book"]["status"], "reading")
        saved = mock_save_books.call_args.args[0]
        self.assertEqual(saved.iloc[0]["Pages Read"], 120)
        mock_invalidate.assert_called_once()

    @patch("backend.services.books.get_all_books")
    def test_update_book_progress_auto_completes(self, mock_get_all_books):
        base_df = pd.DataFrame(
            [
                {
                    "Title": "Almost Done",
                    "Authors": "A",
                    "ISBN/UID": "book-2",
                    "Read Status": "to-read",
                    "Star Rating": np.nan,
                    "Last Date Read": None,
                    "Progress (%)": 90,
                    "Pages Read": 450,
                    "Total Pages": 500,
                }
            ]
        )
        mock_get_all_books.return_value = base_df

        with patch("backend.services.books.save_books") as mock_save:
            response = self.client.patch(
                "/books/book-2/progress",
                json={"status": "reading", "pages_read": 500},
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["book"]["status"], "completed")
        saved = mock_save.call_args.args[0]
        self.assertEqual(saved.iloc[0]["Read Status"], "read")

    @patch("backend.services.books.get_all_books")
    def test_update_book_progress_rejects_pages_over_total(self, mock_get_all_books):
        base_df = pd.DataFrame(
            [
                {
                    "Title": "TBR",
                    "Authors": "A",
                    "ISBN/UID": "book-3",
                    "Read Status": "to-read",
                    "Star Rating": np.nan,
                    "Last Date Read": None,
                    "Progress (%)": 0,
                    "Pages Read": 0,
                    "Total Pages": 500,
                }
            ]
        )
        mock_get_all_books.return_value = base_df

        response = self.client.patch(
            "/books/book-3/progress",
            json={"status": "reading", "pages_read": 600},
        )

        self.assertEqual(response.status_code, 400)

    @patch("backend.services.books.invalidate_recommendation_cache")
    @patch("backend.services.books.save_books")
    @patch("backend.services.books.get_all_books")
    def test_delete_book_by_id(self, mock_get_all, mock_save, mock_invalidate):
        base_df = pd.DataFrame(
            [
                {
                    "Title": "Keep",
                    "Authors": "A",
                    "ISBN/UID": "keep-id",
                    "Read Status": "to-read",
                    "Star Rating": np.nan,
                    "Last Date Read": None,
                    "Progress (%)": 0,
                    "Pages Read": 0,
                    "Total Pages": None,
                },
                {
                    "Title": "Remove",
                    "Authors": "B",
                    "ISBN/UID": "remove-id",
                    "Read Status": "to-read",
                    "Star Rating": np.nan,
                    "Last Date Read": None,
                    "Progress (%)": 0,
                    "Pages Read": 0,
                    "Total Pages": None,
                },
            ]
        )
        mock_get_all.return_value = base_df

        response = self.client.delete("/books/remove-id")
        self.assertEqual(response.status_code, 200)
        saved = mock_save.call_args.args[0]
        self.assertEqual(len(saved), 1)
        self.assertEqual(saved.iloc[0]["ISBN/UID"], "keep-id")
        mock_invalidate.assert_called_once()

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
            ]
        )

        response = self.client.get("/books/export")
        self.assertEqual(response.status_code, 200)
        self.assertIn("text/csv", response.headers.get("content-type", ""))
        self.assertIn("Export Me", response.text)

    @patch("backend.services.books.invalidate_recommendation_cache")
    @patch("backend.services.books.save_books")
    @patch("backend.services.books.get_all_books")
    def test_clear_library(self, mock_get_all, mock_save, mock_invalidate):
        mock_get_all.return_value = pd.DataFrame(
            [
                {
                    "Title": "Gone",
                    "Authors": "A",
                    "ISBN/UID": "1",
                    "Read Status": "to-read",
                    "Star Rating": np.nan,
                    "Last Date Read": None,
                    "Progress (%)": 0,
                    "Pages Read": 0,
                    "Total Pages": None,
                }
            ]
        )

        response = self.client.post("/books/clear", json={"confirm": True})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["deleted"], 1)
        saved = mock_save.call_args.args[0]
        self.assertEqual(len(saved), 0)
        mock_invalidate.assert_called_once()

    @patch("backend.services.books.get_all_books")
    def test_clear_library_requires_confirm(self, mock_get_all):
        mock_get_all.return_value = pd.DataFrame()
        response = self.client.post("/books/clear", json={"confirm": False})
        self.assertEqual(response.status_code, 400)

    @patch("backend.services.books.save_books")
    @patch("backend.services.books.get_all_books")
    def test_patch_move_to_dnf(self, mock_load_data, mock_save_data):
        base_df = pd.DataFrame(
            [
                {
                    "Title": "T",
                    "Authors": "A",
                    "ISBN/UID": "1",
                    "Read Status": "to-read",
                    "Star Rating": np.nan,
                    "Last Date Read": None,
                    "Progress (%)": 0,
                    "Pages Read": 0,
                    "Total Pages": 100,
                }
            ]
        )
        mock_load_data.return_value = base_df

        response = self.client.patch("/books", json={"title": "T", "move_to": "dnf"})
        self.assertEqual(response.status_code, 200)
        saved = mock_save_data.call_args.args[0]
        self.assertEqual(saved.iloc[0]["Read Status"], "dnf")

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
            ]
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
    def test_import_skips_invalidation_if_no_books_added(self, mock_get_all, mock_save, mock_invalidate):
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
