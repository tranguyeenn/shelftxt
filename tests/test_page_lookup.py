import unittest
from unittest.mock import patch

import httpx

from backend.services.page_lookup import (
    BookMetadata,
    lookup_book_metadata,
    lookup_google_books_by_isbn,
    lookup_open_library_by_isbn,
)


class FakeResponse:
    def __init__(self, payload):
        self.payload = payload

    def raise_for_status(self):
        return None

    def json(self):
        return self.payload


class PageLookupTests(unittest.TestCase):
    @patch("backend.services.page_lookup.httpx.get")
    def test_google_books_isbn_page_count_success(self, mock_get):
        mock_get.return_value = FakeResponse(
            {
                "items": [
                    {
                        "volumeInfo": {
                            "title": "Dune",
                            "authors": ["Frank Herbert"],
                            "pageCount": 592,
                        }
                    }
                ]
            }
        )

        metadata = lookup_google_books_by_isbn("9780441172719")

        self.assertEqual(
            metadata,
            BookMetadata(title="Dune", authors="Frank Herbert", total_pages=592),
        )
        mock_get.assert_called_once()

    @patch("backend.services.page_lookup.httpx.get")
    def test_google_books_failure_falls_back_to_open_library(self, mock_get):
        mock_get.side_effect = [
            httpx.TimeoutException("timeout"),
            FakeResponse({"title": "Dune", "authors": [{"name": "Frank Herbert"}], "number_of_pages": 592}),
        ]

        metadata = lookup_book_metadata("Dune", "Frank Herbert", "9780441172719")

        self.assertEqual(
            metadata,
            BookMetadata(title="Dune", authors="Frank Herbert", total_pages=592),
        )
        self.assertEqual(mock_get.call_count, 2)

    @patch("backend.services.page_lookup.httpx.get")
    def test_open_library_isbn_success(self, mock_get):
        mock_get.return_value = FakeResponse(
            {
                "title": "Kindred",
                "authors": [{"name": "Octavia E. Butler"}],
                "number_of_pages": 288,
            }
        )

        metadata = lookup_open_library_by_isbn("9780807083697")

        self.assertEqual(
            metadata,
            BookMetadata(title="Kindred", authors="Octavia E. Butler", total_pages=288),
        )
        self.assertTrue(mock_get.call_args.kwargs["follow_redirects"])

    @patch("backend.services.page_lookup.httpx.get")
    def test_open_library_isbn_redirects_are_followed(self, mock_get):
        mock_get.return_value = FakeResponse(
            {
                "title": "Dune",
                "authors": [{"name": "Frank Herbert"}],
                "number_of_pages": 592,
            }
        )

        metadata = lookup_open_library_by_isbn("9780441172719")

        self.assertEqual(metadata.total_pages, 592)
        mock_get.assert_called_once_with(
            "https://openlibrary.org/isbn/9780441172719.json",
            timeout=2.0,
            follow_redirects=True,
        )

    @patch("backend.services.page_lookup.httpx.get")
    def test_title_only_fallback(self, mock_get):
        mock_get.return_value = FakeResponse(
            {
                "docs": [
                    {
                        "title": "Parable of the Sower",
                        "author_name": ["Octavia E. Butler"],
                        "number_of_pages_median": 345,
                    }
                ]
            }
        )

        metadata = lookup_book_metadata("Parable of the Sower")

        self.assertEqual(
            metadata,
            BookMetadata(
                title="Parable of the Sower",
                authors="Octavia E. Butler",
                total_pages=345,
            ),
        )
        mock_get.assert_called_once()


if __name__ == "__main__":
    unittest.main()
