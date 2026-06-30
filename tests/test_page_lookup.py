import os
import unittest
from unittest.mock import patch

import httpx

from backend.services.goodreads_metadata import reset_goodreads_cache
from backend.services.page_lookup import (
    BookMetadata,
    lookup_book_metadata,
    lookup_book_cover,
    lookup_google_books_by_isbn,
    lookup_open_library_by_isbn,
    lookup_open_library_by_title,
    parse_open_library_description,
)


class FakeResponse:
    def __init__(self, payload):
        self.payload = payload

    def raise_for_status(self):
        return None

    def json(self):
        return self.payload


class PageLookupTests(unittest.TestCase):
    def setUp(self):
        reset_goodreads_cache()
        self._goodreads_csv = os.environ.get("GOODREADS_METADATA_CSV")
        os.environ["GOODREADS_METADATA_CSV"] = "/nonexistent/goodreads-metadata.csv"
        reset_goodreads_cache()

    def tearDown(self):
        reset_goodreads_cache()
        if self._goodreads_csv is None:
            os.environ.pop("GOODREADS_METADATA_CSV", None)
        else:
            os.environ["GOODREADS_METADATA_CSV"] = self._goodreads_csv
        reset_goodreads_cache()

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
                            "imageLinks": {"thumbnail": "http://books.google.com/dune.jpg"},
                        }
                    }
                ]
            }
        )

        metadata = lookup_google_books_by_isbn("9780441172719")

        self.assertEqual(
            metadata,
            BookMetadata(
                title="Dune",
                authors="Frank Herbert",
                total_pages=592,
                metadata_source="google_books",
                cover_url="https://books.google.com/dune.jpg",
            ),
        )
        mock_get.assert_called_once()

    @patch("backend.services.page_lookup.httpx.get")
    def test_open_library_failure_falls_back_to_google_books(self, mock_get):
        mock_get.side_effect = [
            httpx.TimeoutException("timeout"),
            FakeResponse(
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
            ),
        ]

        metadata = lookup_book_metadata("Dune", "Frank Herbert", "9780441172719")

        self.assertEqual(
            metadata,
            BookMetadata(title="Dune", authors="Frank Herbert", total_pages=592, metadata_source="google_books"),
        )
        self.assertEqual(mock_get.call_count, 2)

    @patch("backend.services.page_lookup.httpx.get")
    def test_open_library_isbn_success(self, mock_get):
        mock_get.return_value = FakeResponse(
            {
                "title": "Kindred",
                "authors": [{"name": "Octavia E. Butler"}],
                "number_of_pages": 288,
                "description": {"value": "A time travel novel."},
                "subjects": ["Science fiction", "Time travel"],
                "first_publish_year": 1979,
                "covers": [12345],
            }
        )

        metadata = lookup_open_library_by_isbn("9780807083697")

        self.assertEqual(
            metadata,
            BookMetadata(
                title="Kindred",
                authors="Octavia E. Butler",
                total_pages=288,
                description="A time travel novel.",
                subjects=["science fiction", "time travel"],
                genres=["science fiction"],
                first_publish_year=1979,
                metadata_source="open_library",
                cover_url="https://covers.openlibrary.org/b/id/12345-L.jpg?default=false",
            ),
        )
        self.assertTrue(mock_get.call_args.kwargs["follow_redirects"])

    @patch("backend.services.page_lookup.httpx.get")
    def test_open_library_cover_takes_priority_over_google_books(self, mock_get):
        mock_get.return_value = FakeResponse(
            {
                "title": "Dune",
                "authors": [{"name": "Frank Herbert"}],
                "number_of_pages": 592,
                "covers": [42],
            }
        )

        metadata = lookup_book_metadata("Dune", "Frank Herbert", "9780441172719")

        self.assertEqual(
            metadata.cover_url,
            "https://covers.openlibrary.org/b/id/42-L.jpg?default=false",
        )
        mock_get.assert_called_once()

    @patch("backend.services.page_lookup.httpx.get")
    def test_google_cover_fills_missing_open_library_cover(self, mock_get):
        mock_get.side_effect = [
            FakeResponse(
                {
                    "title": "Dune",
                    "authors": [{"name": "Frank Herbert"}],
                    "number_of_pages": 592,
                }
            ),
            FakeResponse(
                {
                    "items": [
                        {
                            "volumeInfo": {
                                "title": "Dune",
                                "imageLinks": {"thumbnail": "http://books.google.com/dune.jpg"},
                            }
                        }
                    ]
                }
            ),
        ]

        metadata = lookup_book_metadata("Dune", "Frank Herbert", "9780441172719")

        self.assertEqual(metadata.metadata_source, "open_library")
        self.assertEqual(metadata.cover_url, "https://books.google.com/dune.jpg")
        self.assertEqual(mock_get.call_count, 2)

    @patch("backend.services.page_lookup.httpx.get")
    def test_cover_only_lookup_uses_open_library_without_work_lookup(self, mock_get):
        mock_get.return_value = FakeResponse({"covers": [99]})

        metadata = lookup_book_cover("Dune", "Frank Herbert", "9780441172719")

        self.assertEqual(
            metadata,
            BookMetadata(
                cover_url="https://covers.openlibrary.org/b/id/99-L.jpg?default=false",
                metadata_source="open_library",
            ),
        )
        mock_get.assert_called_once()

    @patch("backend.services.page_lookup.httpx.get")
    def test_cover_only_lookup_uses_google_after_open_library_misses(self, mock_get):
        mock_get.side_effect = [
            FakeResponse({"title": "Dune"}),
            FakeResponse({"docs": []}),
            FakeResponse(
                {
                    "items": [
                        {
                            "volumeInfo": {
                                "imageLinks": {"thumbnail": "http://books.google.com/dune.jpg"}
                            }
                        }
                    ]
                }
            ),
        ]

        metadata = lookup_book_cover("Dune", "Frank Herbert", "9780441172719")

        self.assertEqual(metadata.cover_url, "https://books.google.com/dune.jpg")
        self.assertEqual(metadata.metadata_source, "google_books")
        self.assertEqual(mock_get.call_count, 3)

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
                metadata_source="open_library",
            ),
        )
        mock_get.assert_called_once()

    @patch("backend.services.page_lookup.httpx.get")
    def test_search_subjects_generate_genres_when_work_lookup_times_out(self, mock_get):
        mock_get.side_effect = [
            FakeResponse(
                {
                    "docs": [
                        {
                            "title": "Fahrenheit 451",
                            "author_name": ["Ray Bradbury"],
                            "subject": ["Dystopian fiction", "Science fiction"],
                            "key": "/works/OL103123W",
                        }
                    ]
                }
            ),
            httpx.TimeoutException("work timeout"),
        ]

        metadata = lookup_open_library_by_title("Fahrenheit 451", "Ray Bradbury")

        self.assertEqual(metadata.genres, ["dystopian", "science fiction"])
        self.assertEqual(metadata.subjects, ["dystopian fiction", "science fiction"])
        self.assertEqual(mock_get.call_count, 2)

    @patch("backend.services.page_lookup.httpx.get")
    def test_edition_metadata_is_returned_when_work_lookup_times_out(self, mock_get):
        mock_get.side_effect = [
            FakeResponse(
                {
                    "title": "Frankenstein",
                    "number_of_pages": 280,
                    "subjects": ["Gothic fiction", "Science fiction"],
                    "description": "A gothic novel.",
                    "first_publish_year": 1818,
                    "works": [{"key": "/works/OL45026W"}],
                }
            ),
            httpx.TimeoutException("work timeout"),
        ]

        metadata = lookup_open_library_by_isbn("9780000000000")

        self.assertEqual(metadata.title, "Frankenstein")
        self.assertEqual(metadata.total_pages, 280)
        self.assertEqual(metadata.description, "A gothic novel.")
        self.assertEqual(metadata.first_publish_year, 1818)
        self.assertEqual(metadata.genres, ["gothic fiction", "science fiction"])
        self.assertEqual(metadata.metadata_source, "open_library")

    @patch("backend.services.page_lookup.httpx.get")
    def test_manual_fallback_genres_apply_when_api_metadata_fails(self, mock_get):
        mock_get.side_effect = httpx.TimeoutException("search timeout")

        metadata = lookup_book_metadata("A Court of Wings and Ruin", "Sarah J. Maas")

        self.assertEqual(metadata.genres, ["fantasy", "romance"])
        self.assertEqual(metadata.metadata_source, "manual_override")

    @patch("backend.services.page_lookup.httpx.get")
    def test_manual_fallback_validation_examples_are_precise(self, mock_get):
        mock_get.side_effect = httpx.TimeoutException("search timeout")

        examples = {
            "Night": ["memoir", "historical", "nonfiction"],
            "The Death of Ivan Ilych": ["classic", "literary fiction", "philosophy"],
            "Frankenstein": ["gothic fiction", "science fiction", "classic"],
            "Nineteen Eighty-Four": ["dystopian", "political fiction", "science fiction"],
            "Book Lovers": ["romance", "contemporary romance"],
        }

        for title, genres in examples.items():
            with self.subTest(title=title):
                metadata = lookup_book_metadata(title)
                self.assertEqual(metadata.genres, genres)
                self.assertLessEqual(len(metadata.genres), 3)

    def test_open_library_description_parses_string_and_object(self):
        self.assertEqual(parse_open_library_description(" Plain description "), "Plain description")
        self.assertEqual(
            parse_open_library_description({"type": "/type/text", "value": "Object description"}),
            "Object description",
        )


if __name__ == "__main__":
    unittest.main()
