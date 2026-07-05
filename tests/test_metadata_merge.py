from unittest.mock import patch

from backend.services.metadata_merge import merge_metadata_records
from backend.services.page_lookup import BookMetadata, lookup_book_metadata


def test_merge_preserves_priority_and_unions_subjects_and_genres():
    merged = merge_metadata_records(
        {
            "title": "Dune",
            "description": None,
            "subjects": ["desert"],
            "genres": ["science fiction"],
        },
        {
            "title": "",
            "description": "A story of politics and ecology.",
            "subjects": ["politics", "desert"],
            "genres": ["adventure"],
        },
        list_fields={"subjects", "genres"},
    )

    assert merged["title"] == "Dune"
    assert merged["description"] == "A story of politics and ecology."
    assert merged["subjects"] == ["desert", "politics"]
    assert merged["genres"] == ["science fiction", "adventure"]


def test_lookup_merges_google_description_and_page_count_after_open_library():
    open_library = BookMetadata(
        title="Kindred",
        authors="Octavia E. Butler",
        subjects=["time travel"],
        genres=["science fiction"],
        metadata_source="open_library",
        work_key="/works/OL123W",
    )
    google = BookMetadata(
        title="Kindred",
        authors="Octavia Butler",
        description="A modern classic.",
        total_pages=264,
        subjects=["historical fiction"],
        genres=["fiction"],
        metadata_source="google_books",
    )
    with (
        patch("backend.services.page_lookup.lookup_open_library_by_isbn", return_value=open_library),
        patch("backend.services.page_lookup.lookup_google_books_by_isbn", return_value=google),
        patch("backend.services.page_lookup._enrich_with_librarything", side_effect=lambda metadata, **_: metadata),
        patch("backend.services.page_lookup.lookup_goodreads_metadata", return_value=None),
    ):
        result = lookup_book_metadata("Kindred", "Octavia E. Butler", "9780807083697")

    assert result is not None
    assert result.title == "Kindred"
    assert result.authors == "Octavia E. Butler"
    assert result.description == "A modern classic."
    assert result.total_pages == 264
    assert result.subjects == ["time travel", "historical fiction"]
    assert result.genres == ["science fiction", "fiction"]
    assert result.metadata_source == "open_library"
