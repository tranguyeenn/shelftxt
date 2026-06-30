import textwrap
from pathlib import Path
from unittest.mock import patch

import httpx

from backend.services.goodreads_metadata import (
    clean_description,
    colon_base_title,
    is_strong_base_title,
    lookup_goodreads_metadata,
    normalize_title_key,
    reset_goodreads_cache,
)
from backend.services.page_lookup import BookMetadata, lookup_book_metadata
from tests.test_page_lookup import FakeResponse


def _write_csv(path: Path, content: str) -> None:
    path.write_text(textwrap.dedent(content).lstrip(), encoding="utf-8")


def setup_function():
    reset_goodreads_cache()


def teardown_function():
    reset_goodreads_cache()


def test_missing_dataset_returns_none(tmp_path, monkeypatch):
    missing = tmp_path / "missing.csv"
    monkeypatch.setenv("GOODREADS_METADATA_CSV", str(missing))

    assert lookup_goodreads_metadata("To Kill a Mockingbird") is None


def test_exact_title_match_returns_description(tmp_path, monkeypatch):
    csv_path = tmp_path / "books.csv"
    _write_csv(
        csv_path,
        """
        title,url,description,genres
        To Kill a Mockingbird,https://www.goodreads.com/book/show/1,"A sleepy Southern town novel.","['Classics', 'Fiction']"
        """,
    )
    monkeypatch.setenv("GOODREADS_METADATA_CSV", str(csv_path))

    result = lookup_goodreads_metadata("To Kill a Mockingbird")

    assert result is not None
    assert result.description == "A sleepy Southern town novel."
    assert result.genres == ["Classics"]


def test_genre_fallback_parses_goodreads_tags(tmp_path, monkeypatch):
    csv_path = tmp_path / "books.csv"
    _write_csv(
        csv_path,
        """
        title,url,description,genres
        Dune,https://www.goodreads.com/book/show/2,,"['Science Fiction', 'Fantasy', 'Fiction']"
        """,
    )
    monkeypatch.setenv("GOODREADS_METADATA_CSV", str(csv_path))

    result = lookup_goodreads_metadata("Dune")

    assert result is not None
    assert result.description is None
    assert result.genres == ["Science Fiction", "Fantasy"]


def test_bad_rows_are_skipped(tmp_path, monkeypatch):
    csv_path = tmp_path / "books.csv"
    _write_csv(
        csv_path,
        """
        title,url,description,genres
        ,https://www.goodreads.com/book/show/0,,"['Fiction']"
        Broken Genres,https://www.goodreads.com/book/show/3,Still readable,not-a-list
        Empty Row,https://www.goodreads.com/book/show/4,,
        Valid Book,https://www.goodreads.com/book/show/5,"A valid description.","['Romance']"
        """,
    )
    monkeypatch.setenv("GOODREADS_METADATA_CSV", str(csv_path))

    assert lookup_goodreads_metadata("") is None
    broken = lookup_goodreads_metadata("Broken Genres")
    assert broken is not None
    assert broken.description == "Still readable"
    assert broken.genres is None
    assert lookup_goodreads_metadata("Empty Row") is None
    valid = lookup_goodreads_metadata("Valid Book")
    assert valid is not None
    assert valid.description == "A valid description."
    assert valid.genres == ["Romance"]


def test_html_in_descriptions_is_cleaned():
    assert clean_description("<p>Hello <b>world</b>.</p>") == "Hello world ."
    assert clean_description("  Plain text  ") == "Plain text"


def test_normalize_title_key_strips_case_punctuation_and_whitespace():
    assert normalize_title_key("  The Hobbit!!  ") == "the hobbit"
    assert normalize_title_key("Pride & Prejudice") == "pride prejudice"


def test_colon_subtitle_matches_base_title_in_dataset(tmp_path, monkeypatch):
    csv_path = tmp_path / "books.csv"
    _write_csv(
        csv_path,
        """
        title,url,description,genres
        "The Hobbit: Illustrated Edition",https://www.goodreads.com/book/show/9,"A hobbit adventure.","['Fantasy', 'Classics']"
        """,
    )
    monkeypatch.setenv("GOODREADS_METADATA_CSV", str(csv_path))

    result = lookup_goodreads_metadata("The Hobbit")

    assert result is not None
    assert result.description == "A hobbit adventure."


def test_colon_subtitle_matches_base_title_in_query(tmp_path, monkeypatch):
    csv_path = tmp_path / "books.csv"
    _write_csv(
        csv_path,
        """
        title,url,description,genres
        The Hobbit,https://www.goodreads.com/book/show/10,"A hobbit adventure.","['Fantasy']"
        """,
    )
    monkeypatch.setenv("GOODREADS_METADATA_CSV", str(csv_path))

    result = lookup_goodreads_metadata("The Hobbit: Illustrated Edition")

    assert result is not None
    assert result.description == "A hobbit adventure."


def test_ambiguous_colon_base_titles_do_not_match(tmp_path, monkeypatch):
    csv_path = tmp_path / "books.csv"
    _write_csv(
        csv_path,
        """
        title,url,description,genres
        "The Hobbit: Illustrated Edition",https://www.goodreads.com/book/show/11,"Illustrated text.","['Fantasy']"
        "The Hobbit: Movie Tie-In",https://www.goodreads.com/book/show/12,"Movie tie-in text.","['Fantasy']"
        """,
    )
    monkeypatch.setenv("GOODREADS_METADATA_CSV", str(csv_path))

    assert lookup_goodreads_metadata("The Hobbit") is None


def test_weak_base_titles_are_rejected():
    assert colon_base_title("The: A Story") == "The"
    assert not is_strong_base_title("The")
    assert not is_strong_base_title("A")


def test_near_miss_titles_do_not_fuzzy_match(tmp_path, monkeypatch):
    csv_path = tmp_path / "books.csv"
    _write_csv(
        csv_path,
        """
        title,url,description,genres
        The Hobbit,https://www.goodreads.com/book/show/13,"A hobbit adventure.","['Fantasy']"
        """,
    )
    monkeypatch.setenv("GOODREADS_METADATA_CSV", str(csv_path))

    assert lookup_goodreads_metadata("The Hobbits") is None
    assert lookup_goodreads_metadata("Hobbit") is None


@patch("backend.services.page_lookup.httpx.get")
def test_lookup_book_metadata_does_not_overwrite_open_library_description(mock_get, tmp_path, monkeypatch):
    csv_path = tmp_path / "books.csv"
    _write_csv(
        csv_path,
        """
        title,url,description,genres
        Kindred,https://www.goodreads.com/book/show/6,"Goodreads description.","['Science Fiction']"
        """,
    )
    monkeypatch.setenv("GOODREADS_METADATA_CSV", str(csv_path))

    mock_get.return_value = FakeResponse(
        {
            "title": "Kindred",
            "authors": [{"name": "Octavia E. Butler"}],
            "description": {"value": "Open Library description."},
            "subjects": ["Science fiction"],
        }
    )

    metadata = lookup_book_metadata("Kindred", "Octavia E. Butler", "9780807083697")

    assert metadata is not None
    assert metadata.description == "Open Library description."
    assert metadata.metadata_source == "open_library"


@patch("backend.services.page_lookup.httpx.get")
def test_lookup_book_metadata_fills_missing_description_from_goodreads(mock_get, tmp_path, monkeypatch):
    csv_path = tmp_path / "books.csv"
    _write_csv(
        csv_path,
        """
        title,url,description,genres
        Parable of the Sower,https://www.goodreads.com/book/show/7,"A dystopian future novel.","['Science Fiction', 'Dystopian']"
        """,
    )
    monkeypatch.setenv("GOODREADS_METADATA_CSV", str(csv_path))
    mock_get.side_effect = httpx.TimeoutException("timeout")

    metadata = lookup_book_metadata("Parable of the Sower", "Octavia E. Butler")

    assert metadata is not None
    assert metadata.description == "A dystopian future novel."
    assert metadata.genres == ["Science Fiction", "Dystopian"]
    assert metadata.metadata_source == "goodreads_kaggle"


@patch("backend.services.page_lookup.httpx.get")
def test_lookup_book_metadata_replaces_generic_genres_from_goodreads(mock_get, tmp_path, monkeypatch):
    csv_path = tmp_path / "books.csv"
    _write_csv(
        csv_path,
        """
        title,url,description,genres
        The Left Hand of Darkness,https://www.goodreads.com/book/show/8,,"['Science Fiction', 'Fantasy', 'Classics']"
        """,
    )
    monkeypatch.setenv("GOODREADS_METADATA_CSV", str(csv_path))
    mock_get.return_value = FakeResponse(
        {
            "docs": [
                {
                    "title": "The Left Hand of Darkness",
                    "author_name": ["Ursula K. Le Guin"],
                    "subject": ["Fiction", "Literature"],
                }
            ]
        }
    )

    metadata = lookup_book_metadata("The Left Hand of Darkness", "Ursula K. Le Guin")

    assert metadata is not None
    assert metadata.genres == ["Science Fiction", "Fantasy", "Classics"]
    assert metadata.metadata_source == "open_library"


def test_merge_goodreads_does_not_replace_specific_api_genres(tmp_path, monkeypatch):
    from backend.services.page_lookup import _merge_goodreads_fallback

    goodreads = BookMetadata(
        genres=["Romance", "Young Adult"],
        metadata_source="goodreads_kaggle",
    )
    base = BookMetadata(
        genres=["dystopian", "science fiction"],
        metadata_source="open_library",
    )

    merged = _merge_goodreads_fallback(base, goodreads)

    assert merged.genres == ["dystopian", "science fiction"]
    assert merged.metadata_source == "open_library"
