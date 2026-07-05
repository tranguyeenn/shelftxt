from unittest.mock import Mock, patch

import httpx
import pandas as pd

from app.integrations.librarything import fetch_related_isbns, fetch_work_by_title
from backend.db.models import Book
from backend.scripts.backfill_book_metadata import _apply_metadata
from backend.services.page_lookup import BookMetadata, lookup_book_metadata
from backend.services.recommendation_builder import build_recommendations


THING_ISBN_XML = b"""<?xml version='1.0'?>
<idlist><isbn>0441172717</isbn><isbn>9780441172719</isbn></idlist>
"""


def _response(content: bytes) -> Mock:
    response = Mock(content=content)
    response.raise_for_status.return_value = None
    return response


def test_missing_token_skips_librarything(monkeypatch):
    monkeypatch.delenv("LIBRARYTHING_API_TOKEN", raising=False)
    with patch("app.integrations.librarything.httpx.get") as get:
        assert fetch_related_isbns("9780441172719") == []
        assert fetch_work_by_title("Dune") is None
    get.assert_not_called()


def test_thingisbn_xml_parsing(monkeypatch):
    monkeypatch.setenv("LIBRARYTHING_API_TOKEN", "test-token")
    with patch("app.integrations.librarything.httpx.get", return_value=_response(THING_ISBN_XML)):
        assert fetch_related_isbns("978-0-441-17271-9") == ["0441172717", "9780441172719"]


def test_timeout_does_not_crash_enrichment(monkeypatch):
    monkeypatch.setenv("LIBRARYTHING_API_TOKEN", "test-token")
    with patch(
        "app.integrations.librarything.httpx.get",
        side_effect=httpx.ReadTimeout("timed out"),
    ):
        assert fetch_related_isbns("9780441172719") == []


def test_librarything_data_is_stored_under_metadata():
    book = Book(title="Dune", authors="Frank Herbert", isbn_uid="9780441172719")
    librarything_data = {
        "related_isbns": ["0441172717"],
        "work_url": "https://www.librarything.com/work/4048",
        "enriched_at": "2026-07-05T00:00:00+00:00",
    }
    assert _apply_metadata(book, BookMetadata(librarything=librarything_data)) is True
    assert book.book_metadata == {"librarything": librarything_data}


def test_open_library_remains_primary_when_librarything_enriches(monkeypatch):
    monkeypatch.setenv("LIBRARYTHING_API_TOKEN", "test-token")
    open_library = _response(
        b'{"title":"Dune","authors":[{"name":"Frank Herbert"}],"number_of_pages":412}'
    )
    open_library.json.return_value = {
        "title": "Dune",
        "authors": [{"name": "Frank Herbert"}],
        "number_of_pages": 412,
    }
    with (
        patch("backend.services.page_lookup.httpx.get", return_value=open_library),
        patch("app.integrations.librarything.fetch_related_isbns", return_value=["0441172717"]),
        patch("app.integrations.librarything.fetch_work_by_title", return_value=None),
    ):
        metadata = lookup_book_metadata("Dune", "Frank Herbert", "9780441172719")

    assert metadata is not None
    assert metadata.metadata_source == "open_library"
    assert metadata.librarything["related_isbns"] == ["0441172717"]


def test_recommendations_skip_an_alternate_edition_already_owned():
    df = pd.DataFrame(
        [
            {
                "Title": "Dune",
                "Authors": "Frank Herbert",
                "ISBN/UID": "0441172717",
                "Read Status": "read",
                "Star Rating": 5,
                "Genres": ["science fiction"],
                "metadata": {"librarything": {"related_isbns": ["9780441172719"]}},
            },
            {
                "Title": "Dune: alternate edition",
                "Authors": "Frank Herbert",
                "ISBN/UID": "9780441172719",
                "Read Status": "to-read",
                "Genres": ["science fiction"],
                "metadata": {"librarything": {"related_isbns": ["0441172717"]}},
            },
            {
                "Title": "A Different Book",
                "Authors": "Another Author",
                "ISBN/UID": "9780316769488",
                "Read Status": "to-read",
                "Genres": ["science fiction"],
                "metadata": {},
            },
        ]
    )

    recommendations = build_recommendations(df, top_n=2)
    assert [item["book"]["title"] for item in recommendations] == ["A Different Book"]
