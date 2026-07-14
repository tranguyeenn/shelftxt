import json
import math
from dataclasses import dataclass
from uuid import uuid4

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from backend.db.database import Base
from backend.db.models import Book, Profile
from backend.schemas.books import AddBook
from backend.services.postgres_books import add_book_service
from backend.services.recommendation import (
    get_recommendation,
    get_recommendation_sections,
    recommendation_facets,
)


@dataclass(frozen=True)
class _Outcome:
    source: str
    success: bool
    result_count: int = 0
    latency_ms: float = 1.0
    outcome: str = "success"
    http_status: int | None = None
    request_url: str | None = None
    response_body: str | None = None
    error_type: str | None = None


@dataclass(frozen=True)
class _Aggregation:
    results: list[dict]
    outcomes: tuple[_Outcome, ...]


def _session():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine)()


def _profile(db):
    user_id = uuid4()
    db.add(Profile(id=user_id, email=f"{user_id}@example.com", username=f"u{user_id.hex[:8]}"))
    db.commit()
    return user_id


def _book(
    user_id,
    title,
    isbn_uid,
    *,
    status="to-read",
    rating=None,
    author="Author",
    genres=None,
    subjects=None,
    work_key=None,
    edition_key=None,
    pages=250,
):
    completed = status in {"read", "completed"}
    return Book(
        user_id=user_id,
        title=title,
        authors=author,
        isbn_uid=isbn_uid,
        read_status=status,
        star_rating=rating,
        total_pages=pages,
        pages_read=pages if completed else 0,
        progress_percent=100 if completed else 0,
        genres=genres or ["science fiction"],
        subjects=subjects or ["space opera"],
        work_key=work_key,
        edition_key=edition_key,
    )


def _external(index, *, title=None, work_key=None, isbn=None, author="External Author"):
    return {
        "title": title or f"External Candidate {index}",
        "authors": [author],
        "isbn_uid": isbn or f"97800000000{index:03d}"[-13:],
        "description": "A discovered book with matching themes.",
        "cover_url": f"https://example.com/{index}.jpg",
        "total_pages": 300,
        "subjects": ["space opera"],
        "genres": ["science fiction"],
        "first_publish_year": 2020,
        "metadata_source": "open_library",
        "work_key": work_key or f"/works/OL-EXT-{index}W",
        "edition_key": f"OL-EXT-{index}M",
        "related_isbns": [],
        "confidence_score": 0.82,
    }


def _assert_json_safe(value):
    if isinstance(value, dict):
        for item in value.values():
            _assert_json_safe(item)
        return
    if isinstance(value, list):
        for item in value:
            _assert_json_safe(item)
        return
    if isinstance(value, float):
        assert math.isfinite(value)


def _success_aggregation(results):
    return _Aggregation(
        results=results,
        outcomes=(
            _Outcome(source="local", success=True, result_count=0),
            _Outcome(source="open_library", success=True, result_count=len(results)),
            _Outcome(source="librarything", success=False, outcome="not_configured", error_type="MissingConfiguration"),
        ),
    )


def _seed_anchor_and_library_candidates(db, user_id, *, library_count=7):
    db.add(
        _book(
            user_id,
            "Completed Anchor",
            "anchor",
            status="read",
            rating=5,
            author="Anchor Author",
            genres=["science fiction"],
            subjects=["space opera"],
            work_key="/works/OL-ANCHOR",
        )
    )
    for index in range(library_count):
        db.add(
            _book(
                user_id,
                f"Library Candidate {index}",
                f"library-{index}",
                author=f"Library Author {index}",
                genres=["science fiction"],
                subjects=["space opera"],
                work_key=f"/works/OL-LIB-{index}",
            )
        )
    db.commit()


def test_external_books_not_in_user_library_can_appear(monkeypatch):
    db = _session()
    user_id = _profile(db)
    _seed_anchor_and_library_candidates(db, user_id, library_count=1)
    monkeypatch.setattr(
        "backend.services.recommendation_discovery._run_aggregation",
        lambda _query, _local: _success_aggregation([_external(1)]),
    )

    result = get_recommendation(db, user_id, top_n=2, style="balanced")

    external = [item for item in result if not item["in_library"]]
    assert external
    assert external[0]["book_id"] is None
    assert external[0]["source_type"] == "external_discovery"
    assert external[0]["book"]["title"] == "External Candidate 1"


def test_balanced_style_returns_mixed_results_when_possible(monkeypatch):
    db = _session()
    user_id = _profile(db)
    _seed_anchor_and_library_candidates(db, user_id, library_count=8)
    monkeypatch.setattr(
        "backend.services.recommendation_discovery._run_aggregation",
        lambda _query, _local: _success_aggregation([_external(index) for index in range(8)]),
    )

    result = get_recommendation(db, user_id, top_n=10, style="balanced")

    assert sum(1 for item in result if item["in_library"]) == 6
    assert sum(1 for item in result if item["external_discovery"]) == 4


def test_discovery_style_returns_more_external_candidates(monkeypatch):
    db = _session()
    user_id = _profile(db)
    _seed_anchor_and_library_candidates(db, user_id, library_count=8)
    monkeypatch.setattr(
        "backend.services.recommendation_discovery._run_aggregation",
        lambda _query, _local: _success_aggregation([_external(index) for index in range(8)]),
    )

    balanced = get_recommendation(db, user_id, top_n=10, style="balanced")
    discovery = get_recommendation(db, user_id, top_n=10, style="discovery")

    assert sum(1 for item in discovery if item["external_discovery"]) > sum(
        1 for item in balanced if item["external_discovery"]
    )


def test_completed_books_are_excluded_from_recommendations(monkeypatch):
    db = _session()
    user_id = _profile(db)
    _seed_anchor_and_library_candidates(db, user_id, library_count=1)
    db.add(_book(user_id, "Completed Candidate", "done", status="read", rating=4, work_key="/works/DONE"))
    db.commit()
    monkeypatch.setattr(
        "backend.services.recommendation_discovery._run_aggregation",
        lambda _query, _local: _success_aggregation([]),
    )

    result = get_recommendation(db, user_id, top_n=10, style="balanced")

    assert "Completed Candidate" not in [item["title"] for item in result]


def test_external_duplicates_of_owned_works_are_excluded(monkeypatch):
    db = _session()
    user_id = _profile(db)
    _seed_anchor_and_library_candidates(db, user_id, library_count=1)
    monkeypatch.setattr(
        "backend.services.recommendation_discovery._run_aggregation",
        lambda _query, _local: _success_aggregation(
            [
                _external(1, title="Duplicate", work_key="/works/OL-LIB-0", isbn="9780000000001"),
                _external(2, title="Fresh External", work_key="/works/OL-FRESH", isbn="9780000000002"),
            ]
        ),
    )

    result = get_recommendation(db, user_id, top_n=10, style="balanced")

    assert "Duplicate" not in [item["title"] for item in result]
    assert "Fresh External" in [item["title"] for item in result]


def test_external_editions_of_same_work_are_deduplicated(monkeypatch):
    db = _session()
    user_id = _profile(db)
    _seed_anchor_and_library_candidates(db, user_id, library_count=1)
    monkeypatch.setattr(
        "backend.services.recommendation_discovery._run_aggregation",
        lambda _query, _local: _success_aggregation(
            [
                _external(1, title="Shared Work Edition A", work_key="/works/OL-SHARED", isbn="9780000000101"),
                _external(2, title="Shared Work Edition B", work_key="/works/OL-SHARED", isbn="9780000000102"),
            ]
        ),
    )

    result = get_recommendation(db, user_id, top_n=10, style="balanced")

    assert sum(1 for item in result if item.get("work_id") == "/works/OL-SHARED") == 1


def test_provider_failure_falls_back_to_library_recommendations(caplog, monkeypatch):
    caplog.set_level("INFO")
    db = _session()
    user_id = _profile(db)
    _seed_anchor_and_library_candidates(db, user_id, library_count=2)

    def failed_aggregation(_query, _local):
        return _Aggregation(
            results=[],
            outcomes=(
                _Outcome(source="local", success=True, result_count=0),
                _Outcome(source="open_library", success=False, outcome="timeout", error_type="ReadTimeout"),
                _Outcome(source="librarything", success=False, outcome="not_configured", error_type="MissingConfiguration"),
            ),
        )

    monkeypatch.setattr("backend.services.recommendation_discovery._run_aggregation", failed_aggregation)

    result = get_recommendation(db, user_id, top_n=10, style="balanced")

    assert result
    assert all(item["in_library"] for item in result)
    assert "provider_failures" in caplog.text


def test_external_recommendation_can_be_added_and_then_becomes_library_candidate(monkeypatch):
    db = _session()
    user_id = _profile(db)
    _seed_anchor_and_library_candidates(db, user_id, library_count=0)
    external = _external(1, title="Addable External", work_key="/works/OL-ADDABLE", isbn="9780000000999")
    monkeypatch.setattr(
        "backend.services.recommendation_discovery._run_aggregation",
        lambda _query, _local: _success_aggregation([external]),
    )

    before = get_recommendation(db, user_id, top_n=10, style="balanced")
    assert before[0]["in_library"] is False

    add_book_service(
        db,
        AddBook(
            title=external["title"],
            author=external["authors"][0],
            isbn_uid=external["isbn_uid"],
            status="not_started",
            genres=external["genres"],
            subjects=external["subjects"],
            metadata_source=external["metadata_source"],
            work_key=external["work_key"],
            edition_key=external["edition_key"],
            cover_url=external["cover_url"],
        ),
        user_id,
    )

    after = get_recommendation(db, user_id, top_n=10, style="balanced")

    match = next(item for item in after if item["title"] == "Addable External")
    assert match["in_library"] is True
    assert match["source_type"] == "library"
    assert match["book_id"] is not None


def test_external_recommendation_with_missing_isbn_serializes_without_nan(monkeypatch):
    db = _session()
    user_id = _profile(db)
    _seed_anchor_and_library_candidates(db, user_id, library_count=1)
    external = _external(1, title="No ISBN External", isbn=None)
    external["isbn_uid"] = None
    monkeypatch.setattr(
        "backend.services.recommendation_discovery._run_aggregation",
        lambda _query, _local: _success_aggregation([external]),
    )

    result = get_recommendation(db, user_id, top_n=3, style="balanced")

    match = next(item for item in result if item["title"] == "No ISBN External")
    assert match["isbn"] is None
    _assert_json_safe(result)
    json.dumps(result, allow_nan=False)


def test_external_recommendation_with_missing_ids_uses_safe_external_id(monkeypatch):
    db = _session()
    user_id = _profile(db)
    _seed_anchor_and_library_candidates(db, user_id, library_count=1)
    external = _external(1, title="Missing IDs External", work_key=None, isbn=None)
    external["isbn_uid"] = None
    external["work_key"] = None
    external["edition_key"] = None
    monkeypatch.setattr(
        "backend.services.recommendation_discovery._run_aggregation",
        lambda _query, _local: _success_aggregation([external]),
    )

    result = get_recommendation(db, user_id, top_n=3, style="balanced")

    match = next(item for item in result if item["title"] == "Missing IDs External")
    assert match["book_id"] is None
    assert match["work_id"] is None
    assert match["edition_id"] is None
    assert match["external_id"].startswith("external:missing ids external:")
    _assert_json_safe(result)
    json.dumps(result, allow_nan=False)


def test_external_recommendation_with_nan_match_score_serializes_as_safe_score(monkeypatch):
    db = _session()
    user_id = _profile(db)
    _seed_anchor_and_library_candidates(db, user_id, library_count=1)
    external = _external(1, title="NaN Score External")
    external["confidence_score"] = float("nan")
    monkeypatch.setattr(
        "backend.services.recommendation_discovery._run_aggregation",
        lambda _query, _local: _success_aggregation([external]),
    )

    result = get_recommendation(db, user_id, top_n=3, style="balanced")

    match = next(item for item in result if item["title"] == "NaN Score External")
    assert math.isfinite(match["match_score"])
    _assert_json_safe(result)
    json.dumps(result, allow_nan=False)


def test_mixed_library_external_recommendations_serialize_without_nan(monkeypatch):
    db = _session()
    user_id = _profile(db)
    _seed_anchor_and_library_candidates(db, user_id, library_count=8)
    external = _external(1, title="Sparse External", isbn=None)
    external["isbn_uid"] = None
    external["work_key"] = None
    external["edition_key"] = None
    external["total_pages"] = float("nan")
    monkeypatch.setattr(
        "backend.services.recommendation_discovery._run_aggregation",
        lambda _query, _local: _success_aggregation([external, _external(2), _external(3), _external(4)]),
    )

    result = get_recommendation(db, user_id, top_n=10, style="balanced")

    assert any(item["in_library"] for item in result)
    assert any(item["external_discovery"] for item in result)
    _assert_json_safe(result)
    json.dumps(result, allow_nan=False)


def test_genre_facet_count_matches_eligible_result_pool(monkeypatch):
    db = _session()
    user_id = _profile(db)
    db.add(
        _book(
            user_id,
            "Completed Bestseller Anchor",
            "anchor-bestseller",
            status="read",
            rating=5,
            subjects=["New York Times Bestseller"],
            genres=["fiction"],
        )
    )
    db.add(
        _book(
            user_id,
            "Eligible Bestseller Candidate",
            "eligible-bestseller",
            subjects=["New York Times Bestsellers"],
            genres=[],
        )
    )
    db.add(
        _book(
            user_id,
            "Completed Bestseller Candidate",
            "completed-bestseller",
            status="read",
            rating=4,
            subjects=["new-york-times bestseller"],
            genres=[],
        )
    )
    db.add(
        _book(
            user_id,
            "Reading Bestseller Candidate",
            "reading-bestseller",
            subjects=["New York Times Bestseller"],
            genres=[],
        )
    )
    db.flush()
    reading = db.query(Book).filter(Book.isbn_uid == "reading-bestseller").one()
    reading.pages_read = 25
    reading.progress_percent = 10
    db.commit()
    monkeypatch.setattr(
        "backend.services.recommendation_discovery._run_aggregation",
        lambda _query, _local: _success_aggregation([]),
    )

    facets = recommendation_facets(db, user_id, kind="genres", limit=10)

    bestseller = next(item for item in facets["items"] if item["label"] == "new york times bestseller")
    assert bestseller["candidate_count"] == 1
    assert bestseller["external_candidate_count"] == 0


def test_selecting_counted_genre_returns_result_with_normalized_subject_match(monkeypatch):
    db = _session()
    user_id = _profile(db)
    db.add(
        _book(
            user_id,
            "Completed Bestseller Anchor",
            "anchor-bestseller",
            status="read",
            rating=5,
            subjects=["New York Times Bestseller"],
            genres=["fiction"],
        )
    )
    db.add(
        _book(
            user_id,
            "Eligible Bestseller Candidate",
            "eligible-bestseller",
            subjects=["New York Times Bestsellers"],
            genres=[],
        )
    )
    db.commit()
    monkeypatch.setattr(
        "backend.services.recommendation_discovery._run_aggregation",
        lambda _query, _local: _success_aggregation([]),
    )

    result = get_recommendation(
        db,
        user_id,
        top_n=10,
        style="balanced",
        genre="New York Times Bestseller",
    )

    assert any(item["title"] == "Eligible Bestseller Candidate" for item in result)


def test_genre_facets_include_external_eligible_candidates(monkeypatch):
    db = _session()
    user_id = _profile(db)
    _seed_anchor_and_library_candidates(db, user_id, library_count=0)
    external = _external(
        1,
        title="External Bestseller Candidate",
        work_key="/works/OL-BESTSELLER",
        isbn="9780000001111",
    )
    external["subjects"] = ["New York Times Bestseller"]
    external["genres"] = []
    monkeypatch.setattr(
        "backend.services.recommendation_discovery._run_aggregation",
        lambda _query, _local: _success_aggregation([external]),
    )

    facets = recommendation_facets(db, user_id, kind="genres", limit=10)

    bestseller = next(item for item in facets["items"] if item["label"] == "new york times bestseller")
    assert bestseller["candidate_count"] == 1
    assert bestseller["external_candidate_count"] == 1


def test_external_genre_recommendation_renders_in_sections_with_null_book_id(monkeypatch):
    db = _session()
    user_id = _profile(db)
    _seed_anchor_and_library_candidates(db, user_id, library_count=0)
    external = _external(
        1,
        title="External Bestseller Candidate",
        work_key="/works/OL-BESTSELLER",
        isbn="9780000001111",
    )
    external["subjects"] = ["New York Times Bestseller"]
    external["genres"] = []
    monkeypatch.setattr(
        "backend.services.recommendation_discovery._run_aggregation",
        lambda _query, _local: _success_aggregation([external]),
    )

    sections = get_recommendation_sections(
        db,
        user_id,
        top_n=10,
        style="balanced",
        genre="new york times bestseller",
    )

    items = sections["sections"][0]["items"]
    assert len(items) == 1
    assert items[0]["canonical_title"] == "External Bestseller Candidate"
    assert items[0]["library_state"]["in_library"] is False
