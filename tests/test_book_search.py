from uuid import uuid4
from unittest.mock import patch

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from backend.db.database import Base
from backend.db.models import Book, Profile
from backend.services.book_search import search_books


def _session():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine)()


def test_search_normalizes_and_merges_provider_results():
    db = _session()
    user_id = uuid4()
    db.add(Profile(id=user_id, email="reader@example.com", username="reader"))
    db.commit()

    open_library = {
        "title": "Kindred",
        "authors": ["Octavia E. Butler"],
        "isbn_uid": "9780807083697",
        "description": None,
        "cover_url": None,
        "total_pages": 264,
        "subjects": ["time travel"],
        "genres": ["science fiction"],
        "first_publish_year": 1979,
        "metadata_source": "open_library",
        "work_key": "/works/OL123W",
        "edition_key": "OL123M",
        "related_isbns": [],
        "already_in_library": False,
    }
    google = {**open_library, "description": "A modern classic.", "metadata_source": "google_books"}
    with (
        patch("backend.services.book_search._open_library_results", return_value=[open_library]),
        patch("backend.services.book_search._google_books_results", return_value=[google]),
        patch("backend.services.book_resolver.librarything.fetch_related_isbns", return_value=["0807083690"]),
    ):
        results = search_books(db, user_id, "Kindred")

    assert len(results) == 1
    assert results[0]["metadata_source"] == "google_books"
    assert results[0]["description"] == "A modern classic."
    assert results[0]["related_isbns"] == ["0807083690"]
    assert set(results[0]) == {
        "title", "authors", "isbn_uid", "description", "cover_url", "total_pages",
        "subjects", "genres", "first_publish_year", "metadata_source", "work_key",
        "edition_key", "publisher", "publish_date", "language", "related_isbns", "already_in_library",
    }


def test_search_marks_related_isbn_duplicate():
    db = _session()
    user_id = uuid4()
    db.add(Profile(id=user_id, email="reader@example.com", username="reader"))
    db.add(
        Book(
            user_id=user_id,
            title="Dune",
            authors="Frank Herbert",
            isbn_uid="0441172717",
            book_metadata={"librarything": {"related_isbns": ["9780441172719"]}},
        )
    )
    db.commit()
    candidate = {
        "title": "Dune",
        "authors": ["Frank Herbert"],
        "isbn_uid": "9780441172719",
        "description": None,
        "cover_url": None,
        "total_pages": 412,
        "subjects": [],
        "genres": [],
        "first_publish_year": 1965,
        "metadata_source": "open_library",
        "work_key": None,
        "edition_key": None,
        "related_isbns": [],
        "already_in_library": False,
    }
    with (
        patch("backend.services.book_search._open_library_results", return_value=[candidate]),
        patch("backend.services.book_search._google_books_results", return_value=[]),
        patch("backend.services.book_resolver.librarything.fetch_related_isbns", return_value=["0441172717"]),
    ):
        results = search_books(db, user_id, "Dune")

    assert results[0]["already_in_library"] is True
