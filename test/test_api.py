import unittest
from unittest.mock import patch

import numpy as np
import pandas as pd
from fastapi.testclient import TestClient

import api


class ApiTests(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(api.app)

    @patch("api.save_data")
    @patch("api.load_data")
    def test_add_book_appends_new_tbr_row(self, mock_load_data, mock_save_data):
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

        saved_df = mock_save_data.call_args.args[0]
        self.assertEqual(len(saved_df), 2)
        self.assertEqual(saved_df.iloc[-1]["Title"], "New Book")
        self.assertEqual(saved_df.iloc[-1]["Authors"], "New Author")
        self.assertEqual(saved_df.iloc[-1]["Read Status"], "to-read")

    @patch("api.get_recommendation")
    def test_recommend_returns_list_payload(self, mock_get_recommendation):
        mock_get_recommendation.return_value = [
            {
                "Title": "Snow Crash",
                "Authors": "Neal Stephenson",
                "score": 0.93,
            }
        ]

        response = self.client.get("/recommend")
        self.assertEqual(response.status_code, 200)

        payload = response.json()
        self.assertIsInstance(payload, list)
        self.assertEqual(payload[0]["Title"], "Snow Crash")
        self.assertEqual(payload[0]["Authors"], "Neal Stephenson")
        mock_get_recommendation.assert_called_once_with()

    @patch("api.get_recommendation")
    def test_recommend_returns_empty_when_no_pick(self, mock_get_recommendation):
        mock_get_recommendation.return_value = []

        response = self.client.get("/recommend")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), [])
        mock_get_recommendation.assert_called_once_with()

    @patch("api.save_data")
    @patch("api.load_data")
    def test_delete_book_removes_row(self, mock_load_data, mock_save_data):
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
        mock_load_data.return_value = base_df

        response = self.client.delete("/books?title=Remove")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"message": "Book deleted"})
        saved_df = mock_save_data.call_args.args[0]
        self.assertEqual(len(saved_df), 1)
        self.assertEqual(saved_df.iloc[0]["Title"], "Keep")

    @patch("api.save_data")
    @patch("api.load_data")
    def test_remove_via_post(self, mock_load_data, mock_save_data):
        base_df = pd.DataFrame(
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
        mock_load_data.return_value = base_df

        response = self.client.post("/books/remove", json={"title": "Gone"})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"message": "Book deleted"})
        saved_df = mock_save_data.call_args.args[0]
        self.assertEqual(len(saved_df), 0)

    @patch("api.save_data")
    @patch("api.load_data")
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

    @patch("api.save_data")
    @patch("api.load_data")
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


if __name__ == "__main__":
    unittest.main()
