from unittest.mock import patch

from backend.db.models import Book
from backend.scripts.backfill_book_metadata import backfill_book_metadata
from backend.services.page_lookup import BookMetadata
from tests.test_api import TEST_USER_ID, TestingSessionLocal, _seed_book, _seed_profile, engine
from backend.db.database import Base


def setup_function():
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    _seed_profile()


@patch("backend.scripts.backfill_book_metadata.time.sleep", return_value=None)
@patch("backend.scripts.backfill_book_metadata.get_session_local", return_value=TestingSessionLocal)
@patch("backend.scripts.backfill_book_metadata.lookup_book_metadata")
def test_backfill_skips_already_enriched_books(mock_lookup, _mock_session, _mock_sleep):
    _seed_book(
        title="Enriched",
        authors="A",
        isbn_uid="enriched",
        description="Existing description",
        subjects=["censorship"],
        genres=["dystopian"],
    )
    _seed_book(title="Missing", authors="B", isbn_uid="missing")
    mock_lookup.return_value = BookMetadata(
        description="New description",
        subjects=["magic"],
        genres=["fantasy"],
        metadata_source="open_library",
    )

    updated = backfill_book_metadata(limit=10, batch_size=1, sleep_seconds=0)

    assert updated == 1
    mock_lookup.assert_called_once_with("Missing", "B", "missing")

    db = TestingSessionLocal()
    try:
        missing = db.query(Book).filter(Book.isbn_uid == "missing").one()
        enriched = db.query(Book).filter(Book.isbn_uid == "enriched").one()
        assert missing.genres == ["fantasy"]
        assert missing.subjects == ["magic"]
        assert missing.description == "New description"
        assert enriched.description == "Existing description"
    finally:
        db.close()


@patch("backend.scripts.backfill_book_metadata.time.sleep", return_value=None)
@patch("backend.scripts.backfill_book_metadata.get_session_local", return_value=TestingSessionLocal)
@patch("backend.scripts.backfill_book_metadata.lookup_book_metadata")
def test_backfill_only_rated_prioritizes_rated_books(mock_lookup, _mock_session, _mock_sleep):
    _seed_book(title="Unrated Missing", authors="A", isbn_uid="unrated")
    _seed_book(title="Four Star Missing", authors="B", isbn_uid="four", star_rating=4.0)
    _seed_book(title="Five Star Missing", authors="C", isbn_uid="five", star_rating=5.0)
    mock_lookup.return_value = BookMetadata(
        subjects=["magic"],
        genres=["fantasy"],
        metadata_source="open_library",
    )

    updated = backfill_book_metadata(
        limit=2,
        batch_size=1,
        sleep_seconds=0,
        only_rated=True,
        missing_genres=True,
    )

    assert updated == 2
    assert mock_lookup.call_args_list[0].args == ("Five Star Missing", "C", "five")
    assert mock_lookup.call_args_list[1].args == ("Four Star Missing", "B", "four")

    db = TestingSessionLocal()
    try:
        unrated = db.query(Book).filter(Book.isbn_uid == "unrated").one()
        assert unrated.genres is None
    finally:
        db.close()


@patch("backend.scripts.backfill_book_metadata.time.sleep", return_value=None)
@patch("backend.scripts.backfill_book_metadata.get_session_local", return_value=TestingSessionLocal)
@patch("backend.scripts.backfill_book_metadata.lookup_book_metadata")
def test_backfill_manual_fallback_genres_apply_when_api_metadata_fails(
    mock_lookup,
    _mock_session,
    _mock_sleep,
):
    _seed_book(title="Animal Farm", authors="George Orwell", isbn_uid="animal-farm", star_rating=4.75)
    mock_lookup.return_value = BookMetadata(
        genres=["dystopian", "classic", "political fiction"],
        metadata_source="manual_override",
    )

    updated = backfill_book_metadata(
        limit=10,
        batch_size=1,
        sleep_seconds=0,
        only_rated=True,
        missing_genres=True,
    )

    assert updated == 1
    db = TestingSessionLocal()
    try:
        book = db.query(Book).filter(Book.isbn_uid == "animal-farm").one()
        assert book.genres == ["dystopian", "classic", "political fiction"]
        assert book.metadata_source == "manual_override"
    finally:
        db.close()


@patch("backend.scripts.backfill_book_metadata.time.sleep", return_value=None)
@patch("backend.scripts.backfill_book_metadata.get_session_local", return_value=TestingSessionLocal)
@patch("backend.scripts.backfill_book_metadata.lookup_book_metadata")
def test_backfill_preserves_existing_end_date_when_total_pages_added(
    mock_lookup,
    _mock_session,
    _mock_sleep,
):
    _seed_book(
        title="Completed Missing Pages",
        authors="A",
        isbn_uid="completed-missing-pages",
        read_status="read",
        progress_percent=100,
        end_date="2025-02-03",
    )
    mock_lookup.return_value = BookMetadata(
        total_pages=320,
        genres=["fiction"],
        metadata_source="open_library",
    )

    updated = backfill_book_metadata(limit=10, batch_size=1, sleep_seconds=0)

    assert updated == 1
    db = TestingSessionLocal()
    try:
        book = db.query(Book).filter(Book.isbn_uid == "completed-missing-pages").one()
        assert book.total_pages == 320
        assert book.end_date.isoformat() == "2025-02-03"
    finally:
        db.close()


@patch("backend.scripts.backfill_book_metadata.time.sleep", return_value=None)
@patch("backend.scripts.backfill_book_metadata.get_session_local", return_value=TestingSessionLocal)
@patch("backend.scripts.backfill_book_metadata.lookup_book_cover")
def test_backfill_missing_covers_updates_existing_enriched_books(
    mock_lookup, _mock_session, _mock_sleep
):
    _seed_book(
        title="Already Enriched",
        authors="A",
        isbn_uid="9780441172719",
        description="Existing description",
        subjects=["science fiction"],
        genres=["science fiction"],
    )
    mock_lookup.return_value = BookMetadata(
        cover_url="https://covers.openlibrary.org/b/id/42-L.jpg?default=false",
        metadata_source="open_library",
    )

    updated = backfill_book_metadata(
        limit=10,
        batch_size=1,
        sleep_seconds=0,
        missing_covers=True,
    )

    assert updated == 1
    db = TestingSessionLocal()
    try:
        book = db.query(Book).filter(Book.isbn_uid == "9780441172719").one()
        assert book.cover_url == "https://covers.openlibrary.org/b/id/42-L.jpg?default=false"
    finally:
        db.close()


@patch("backend.scripts.backfill_book_metadata.time.sleep", return_value=None)
@patch("backend.scripts.backfill_book_metadata.get_session_local", return_value=TestingSessionLocal)
@patch("backend.scripts.backfill_book_metadata.lookup_book_metadata")
def test_backfill_replaces_overinflated_genres(mock_lookup, _mock_session, _mock_sleep):
    _seed_book(
        title="Night",
        authors="Elie Wiesel",
        isbn_uid="night",
        star_rating=5,
        genres=["historical fiction", "fantasy", "science fiction", "romance"],
        subjects=["noisy"],
        description="Existing",
    )
    mock_lookup.return_value = BookMetadata(
        genres=["memoir", "historical", "nonfiction"],
        metadata_source="manual_override",
    )

    updated = backfill_book_metadata(
        limit=10,
        batch_size=1,
        sleep_seconds=0,
        only_rated=True,
    )

    assert updated == 1
    db = TestingSessionLocal()
    try:
        book = db.query(Book).filter(Book.isbn_uid == "night").one()
        assert book.genres == ["memoir", "historical", "nonfiction"]
    finally:
        db.close()
