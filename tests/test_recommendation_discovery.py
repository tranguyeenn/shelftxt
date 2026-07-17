import json
import math
from dataclasses import dataclass
from uuid import uuid4

import pandas as pd
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from backend.db.database import Base
from backend.db.models import Book, Profile
from backend.schemas.books import AddBook
from backend.services.candidate_integrity import evaluate_candidate_integrity
from backend.services.postgres_books import add_book_service
from backend.services.recommendation import (
    get_recommendation,
    get_recommendation_sections,
    recommendation_facets,
)
from backend.services.recommendation_builder import build_recommendations
from backend.services.recommendation_discovery import DiscoveryQuery, discovery_candidate_rows


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
    metadata=None,
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
        book_metadata=metadata,
    )


def _external(index, *, title=None, work_key=None, isbn=None, author="External Author", series=None):
    result = {
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
    if series:
        result["series"] = series
        result.update(series)
    return result


def test_candidate_integrity_classifies_collections_conservatively():
    boxed = evaluate_candidate_integrity({"title": "A Court of Thorns and Roses Box Set"})
    ranged = evaluate_candidate_integrity({"title": "Fantasy Saga Books 1-3"})
    collection_set = evaluate_candidate_integrity({"title": "Ali Hazelwood Collection 2 Books Set"})
    complete = evaluate_candidate_integrity({"title": "The Complete Lunar Chronicles"})
    standalone = evaluate_candidate_integrity({"title": "Set in Stone"})
    anthology = evaluate_candidate_integrity({"title": "Best American Short Stories", "subjects": ["anthology"]})

    assert boxed.classification == "boxed_set"
    assert not boxed.recommendation_eligible
    assert ranged.classification == "bundle"
    assert not ranged.recommendation_eligible
    assert collection_set.classification == "bundle"
    assert not collection_set.recommendation_eligible
    assert complete.classification == "omnibus"
    assert not complete.recommendation_eligible
    assert standalone.classification == "individual_book"
    assert standalone.recommendation_eligible
    assert anthology.classification == "anthology"
    assert anthology.recommendation_eligible


def _naturals_series(position=None):
    books = [
        {"title": "The Naturals", "author": "Jennifer Lynn Barnes", "position": 1, "work_id": "/works/NATURALS-1"},
        {"title": "Killer Instinct", "author": "Jennifer Lynn Barnes", "position": 2, "work_id": "/works/NATURALS-2"},
        {"title": "All In", "author": "Jennifer Lynn Barnes", "position": 3, "work_id": "/works/NATURALS-3"},
        {"title": "Bad Blood", "author": "Jennifer Lynn Barnes", "position": 4, "work_id": "/works/NATURALS-4"},
    ]
    return {
        "series_name": "The Naturals",
        "series_position": position,
        "series_type": "main_series",
        "series_books": books,
        "series_source": "test_fixture",
        "series_confidence": 0.95,
    }


def _hunger_games_series(position=None):
    books = [
        {"title": "The Hunger Games", "author": "Suzanne Collins", "position": 1, "work_id": "/works/HUNGER-GAMES-1"},
        {"title": "Catching Fire", "author": "Suzanne Collins", "position": 2, "work_id": "/works/HUNGER-GAMES-2"},
        {"title": "Mockingjay", "author": "Suzanne Collins", "position": 3, "work_id": "/works/HUNGER-GAMES-3"},
    ]
    return {
        "series_name": "The Hunger Games",
        "series_position": position,
        "series_type": "main_series",
        "series_books": books,
        "series_source": "test_fixture",
        "series_confidence": 0.95,
    }


def _throne_of_glass_series(position=None):
    books = [
        {"title": "Throne of Glass", "author": "Sarah J. Maas", "position": 1, "work_id": "/works/OL16607146W"},
        {"title": "Crown of Midnight", "author": "Sarah J. Maas", "position": 2, "work_id": "/works/OL16809980W"},
        {"title": "Heir of Fire", "author": "Sarah J. Maas", "position": 3, "work_id": "/works/OL17367560W"},
        {"title": "Queen of Shadows", "author": "Sarah J. Maas", "position": 4, "work_id": "/works/OL17718538W"},
    ]
    return {
        "series_name": "Throne of Glass",
        "series_position": position,
        "series_type": "main_series",
        "series_books": books,
        "series_source": "test_fixture",
        "series_confidence": 0.95,
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


def _provider_aggregation(results, *, source):
    return _Aggregation(
        results=results,
        outcomes=(
            _Outcome(source="local", success=True, result_count=0),
            _Outcome(source=source, success=True, result_count=len(results)),
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


def test_discovery_rows_preserve_provider_rank(monkeypatch):
    db = _session()
    user_id = _profile(db)
    anchor = _book(
        user_id,
        "The Hunger Games",
        "hunger-games",
        status="read",
        rating=5,
        author="Suzanne Collins",
        genres=["dystopian"],
        subjects=["survival", "rebellion"],
    )
    db.add(anchor)
    db.commit()
    monkeypatch.setattr(
        "backend.services.recommendation_discovery._run_aggregation",
        lambda _query, _local, **_kwargs: _provider_aggregation(
            [
                _external(1, title="First Result", author="A", work_key="/works/FIRST"),
                _external(2, title="Second Result", author="B", work_key="/works/SECOND"),
            ],
            source="hardcover",
        ),
    )

    rows, _diagnostics = discovery_candidate_rows(db, user_id, [anchor], include_broad_exploration=False)

    ranks = {row["Title"]: row["Provider Rank"] for row in rows}
    assert ranks["First Result"] == 1
    assert ranks["Second Result"] == 2


def test_preferred_cluster_queries_run_before_supplemental_fallbacks(monkeypatch):
    db = _session()
    user_id = _profile(db)
    anchor = _book(
        user_id,
        "Book Lovers",
        "book-lovers",
        status="read",
        rating=5,
        author="Emily Henry",
        genres=["romance"],
        subjects=["contemporary romance"],
    )
    db.add(anchor)
    db.commit()
    monkeypatch.setenv("DISCOVERY_MAX_QUERIES", "2")
    monkeypatch.setattr(
        "backend.services.recommendation_discovery._run_aggregation",
        lambda _query, _local, **_kwargs: _provider_aggregation([], source="hardcover"),
    )

    _rows, diagnostics = discovery_candidate_rows(
        db,
        user_id,
        [anchor],
        preferred_cluster_ids={"contemporary-romance-new-adult"},
        supplemental_query_specs=[
            DiscoveryQuery(
                query="middle-grade bullying redemption friendship",
                cluster_id="topic-middle-grade-friendship-and-moral-choices",
                specific_genres=("middle grade",),
                specific_themes=("bullying", "friendship"),
            )
        ],
    )

    assert diagnostics.structured_queries[0]["cluster_id"] == "contemporary-romance-new-adult"


def test_strong_seeded_external_catching_fire_competes_end_to_end(monkeypatch):
    db = _session()
    user_id = _profile(db)
    db.add(
        _book(
            user_id,
            "The Hunger Games",
            "hunger-games",
            status="read",
            rating=5,
            author="Suzanne Collins",
            genres=["dystopian"],
            subjects=["rebellion", "survival"],
            work_key="/works/HUNGER-GAMES-1",
            metadata={
                "series": {
                    "series_name": "The Hunger Games",
                    "series_position": 1,
                    "series_type": "main_series",
                    "series_confidence": 0.95,
                }
            },
        )
    )
    db.add(
        _book(
            user_id,
            "Weak Library Match",
            "weak-library",
            status="to-read",
            author="Unrelated Author",
            genres=["general fiction"],
            subjects=["life"],
            work_key="/works/WEAK-LIBRARY",
        )
    )
    db.commit()
    catching_fire = _external(
        2,
        title="Catching Fire",
        work_key="/works/HUNGER-GAMES-2",
        author="Suzanne Collins",
        series={
            "series_name": "The Hunger Games",
            "series_position": 2,
            "series_type": "main_series",
            "series_confidence": 0.95,
            "series_books": [
                {"title": "The Hunger Games", "author": "Suzanne Collins", "position": 1, "work_id": "/works/HUNGER-GAMES-1"},
                {"title": "Catching Fire", "author": "Suzanne Collins", "position": 2, "work_id": "/works/HUNGER-GAMES-2"},
            ],
        },
    )
    catching_fire["genres"] = ["dystopian"]
    catching_fire["subjects"] = ["rebellion", "survival"]
    catching_fire["description"] = "A dystopian rebellion survival sequel."
    weak_external = _external(3, title="Weak External", author="Other Author")
    weak_external["genres"] = ["cookbooks"]
    weak_external["subjects"] = ["recipes"]
    weak_external["description"] = "Unrelated recipes."
    monkeypatch.setattr(
        "backend.services.recommendation_discovery._run_aggregation",
        lambda _query, _local, allow_external=True: _provider_aggregation([catching_fire, weak_external] if allow_external else [], source="open_library"),
    )

    result = get_recommendation(db, user_id, top_n=10, style="balanced")
    titles = [item["title"] for item in result]

    assert titles[0] == "Catching Fire"
    assert result[0]["external_discovery"] is True
    assert "Weak External" not in titles
    assert "Weak Library Match" not in titles


def test_translated_edition_is_excluded_when_underlying_work_is_owned(monkeypatch):
    db = _session()
    user_id = _profile(db)
    db.add(
        _book(
            user_id,
            "A Court of Mist and Fury",
            "acomaf",
            status="to-read",
            author="Sarah J. Maas",
            genres=["fantasy"],
            subjects=["fae"],
        )
    )
    db.add(_book(user_id, "A Court of Thorns and Roses", "acotar", status="read", rating=5, author="Sarah J. Maas", genres=["fantasy"], subjects=["magic"]))
    db.commit()
    translated = _external(
        1,
        title="Una corte de niebla y furia",
        author="Sarah J. Maas",
        work_key="/works/TRANSLATED-ACOMAF",
    )
    translated["language"] = "spa"
    replacement = _external(2, title="Throne of Glass", author="Sarah J. Maas", work_key="/works/THRONE-OF-GLASS")
    replacement["genres"] = ["fantasy"]
    replacement["subjects"] = ["magic"]
    monkeypatch.setattr(
        "backend.services.recommendation_discovery._run_aggregation",
        lambda _query, _local, allow_external=True, result_limit=None: _provider_aggregation([translated, replacement] if allow_external else [], source="open_library"),
    )

    result = get_recommendation(db, user_id, top_n=10, style="balanced")
    titles = [item["title"] for item in result]

    assert "Una corte de niebla y furia" not in titles
    assert "Throne of Glass" in titles


def test_translation_remains_eligible_when_underlying_work_is_not_owned(monkeypatch):
    db = _session()
    user_id = _profile(db)
    db.add(_book(user_id, "A Court of Thorns and Roses", "acotar", status="read", rating=5, author="Sarah J. Maas", genres=["fantasy"], subjects=["magic"]))
    db.commit()
    translated = _external(
        1,
        title="Una corte de niebla y furia",
        author="Sarah J. Maas",
        work_key="/works/TRANSLATED-ACOMAF",
    )
    translated["language"] = "spa"
    translated["genres"] = ["fantasy"]
    translated["subjects"] = ["magic"]
    monkeypatch.setattr(
        "backend.services.recommendation_discovery._run_aggregation",
        lambda _query, _local, allow_external=True, result_limit=None: _provider_aggregation([translated] if allow_external else [], source="open_library"),
    )

    result = get_recommendation(db, user_id, top_n=10, style="balanced")
    match = next(item for item in result if item["title"] == "Una corte de niebla y furia")

    assert match["canonical_work_identity"] == "title_author:a-court-of-mist-and-fury:sarah-j-maas"
    assert match["original_title"] == "A Court of Mist and Fury"
    assert match["language"] == "spa"


def test_different_works_by_same_author_remain_separate(monkeypatch):
    db = _session()
    user_id = _profile(db)
    db.add(_book(user_id, "A Court of Mist and Fury", "acomaf", status="read", rating=5, author="Sarah J. Maas", genres=["fantasy"], subjects=["magic"]))
    db.commit()
    candidate = _external(1, title="Throne of Glass", author="Sarah J. Maas", work_key="/works/THRONE-OF-GLASS")
    candidate["genres"] = ["fantasy"]
    candidate["subjects"] = ["magic"]
    monkeypatch.setattr(
        "backend.services.recommendation_discovery._run_aggregation",
        lambda _query, _local, allow_external=True, result_limit=None: _provider_aggregation([candidate] if allow_external else [], source="open_library"),
    )

    result = get_recommendation(db, user_id, top_n=10, style="balanced")

    assert any(item["title"] == "Throne of Glass" for item in result)


def test_hunger_games_omnibus_suppressed_and_catching_fire_is_next(monkeypatch):
    db = _session()
    user_id = _profile(db)
    db.add(
        _book(
            user_id,
            "The Hunger Games",
            "hunger-games",
            status="read",
            rating=5,
            author="Suzanne Collins",
            genres=["dystopian"],
            subjects=["rebellion", "survival"],
            metadata=_hunger_games_series(1),
        )
    )
    db.commit()
    trilogy = _external(1, title="The Hunger Games Trilogy", author="Suzanne Collins", work_key="/works/HG-TRILOGY")
    trilogy["genres"] = ["dystopian"]
    trilogy["subjects"] = ["rebellion", "survival"]
    catching_fire = _external(2, title="Catching Fire", author="Suzanne Collins", work_key="/works/HUNGER-GAMES-2", series=_hunger_games_series(2))
    catching_fire["genres"] = ["dystopian"]
    catching_fire["subjects"] = ["rebellion", "survival"]
    mockingjay = _external(3, title="Mockingjay", author="Suzanne Collins", work_key="/works/HUNGER-GAMES-3", series=_hunger_games_series(3))
    mockingjay["genres"] = ["dystopian"]
    mockingjay["subjects"] = ["rebellion", "survival"]
    monkeypatch.setattr(
        "backend.services.recommendation_discovery._run_aggregation",
        lambda _query, _local, allow_external=True, result_limit=None: _provider_aggregation([trilogy, catching_fire, mockingjay] if allow_external else [], source="open_library"),
    )

    result = get_recommendation(db, user_id, top_n=10, style="balanced")
    titles = [item["title"] for item in result]

    assert "Catching Fire" in titles
    assert "The Hunger Games Trilogy" not in titles
    assert "Mockingjay" not in titles


def test_omnibus_rejected_even_when_user_owns_no_components(monkeypatch):
    db = _session()
    user_id = _profile(db)
    db.add(_book(user_id, "Scythe", "scythe", status="read", rating=5, author="Neal Shusterman", genres=["dystopian"], subjects=["rebellion"]))
    db.commit()
    trilogy = _external(1, title="The Hunger Games Trilogy", author="Suzanne Collins", work_key="/works/HG-TRILOGY")
    trilogy["genres"] = ["dystopian"]
    trilogy["subjects"] = ["rebellion", "survival"]
    monkeypatch.setattr(
        "backend.services.recommendation_discovery._run_aggregation",
        lambda _query, _local, allow_external=True, result_limit=None: _provider_aggregation([trilogy] if allow_external else [], source="open_library"),
    )

    result = get_recommendation(db, user_id, top_n=10, style="balanced")

    assert all(item["title"] != "The Hunger Games Trilogy" for item in result)


def test_books_range_bundle_does_not_outrank_individual_volume(monkeypatch):
    db = _session()
    user_id = _profile(db)
    db.add(_book(user_id, "A Court of Thorns and Roses", "acotar", status="read", rating=5, author="Sarah J. Maas", genres=["fantasy"], subjects=["magic"]))
    db.commit()
    bundle = _external(1, title="A Court of Thorns and Roses Books 1-3", author="Sarah J. Maas", work_key="/works/ACOTAR-BUNDLE")
    individual = _external(2, title="A Court of Mist and Fury", author="Sarah J. Maas", work_key="/works/ACOMAF")
    for item in (bundle, individual):
        item["genres"] = ["fantasy"]
        item["subjects"] = ["magic", "fae"]
    monkeypatch.setattr(
        "backend.services.recommendation_discovery._run_aggregation",
        lambda _query, _local, allow_external=True, result_limit=None: _provider_aggregation([bundle, individual] if allow_external else [], source="hardcover"),
    )

    result = get_recommendation(db, user_id, top_n=10, style="balanced")
    titles = [item["title"] for item in result]

    assert "A Court of Thorns and Roses Books 1-3" not in titles
    assert "A Court of Mist and Fury" in titles


def test_no_throne_of_glass_books_receives_only_first_installment(monkeypatch):
    db = _session()
    user_id = _profile(db)
    db.add(_book(user_id, "A Court of Thorns and Roses", "acotar", status="read", rating=5, author="Sarah J. Maas", genres=["fantasy"], subjects=["magic"]))
    db.commit()
    throne = _external(1, title="Throne of Glass", author="Sarah J. Maas", work_key="/works/OL16607146W")
    queen = _external(2, title="Queen of Shadows", author="Sarah J. Maas", work_key="/works/OL17718538W")
    for item in (throne, queen):
        item["genres"] = ["fantasy"]
        item["subjects"] = ["magic"]
    monkeypatch.setattr(
        "backend.services.recommendation_discovery._run_aggregation",
        lambda _query, _local, allow_external=True, result_limit=None: _provider_aggregation([throne, queen] if allow_external else [], source="open_library"),
    )

    result = get_recommendation(db, user_id, top_n=10, style="balanced")
    titles = [item["title"] for item in result]
    match = next(item for item in result if item["title"] == "Throne of Glass")

    assert "Throne of Glass" in titles
    assert "Queen of Shadows" not in titles
    assert match["canonical_series_identity"] == "series:throne-of-glass"
    assert match["series_position"] == 1.0
    assert match["required_next_position"] == 1.0
    assert match["series_order_decision"] == "allowed"


def test_after_throne_of_glass_completed_next_installment_is_eligible(monkeypatch):
    db = _session()
    user_id = _profile(db)
    db.add(_book(user_id, "Throne of Glass", "tog-1", status="read", rating=5, author="Sarah J. Maas", genres=["fantasy"], subjects=["magic"], metadata=_throne_of_glass_series(1)))
    db.commit()
    crown = _external(1, title="Crown of Midnight", author="Sarah J. Maas", work_key="/works/OL16809980W")
    queen = _external(2, title="Queen of Shadows", author="Sarah J. Maas", work_key="/works/OL17718538W")
    for item in (crown, queen):
        item["genres"] = ["fantasy"]
        item["subjects"] = ["magic"]
    monkeypatch.setattr(
        "backend.services.recommendation_discovery._run_aggregation",
        lambda _query, _local, allow_external=True, result_limit=None: _provider_aggregation([crown, queen] if allow_external else [], source="open_library"),
    )

    result = get_recommendation(db, user_id, top_n=10, style="balanced")
    titles = [item["title"] for item in result]

    assert "Crown of Midnight" in titles
    assert "Queen of Shadows" not in titles


def test_owned_unread_earlier_throne_of_glass_blocks_later_installments(monkeypatch):
    db = _session()
    user_id = _profile(db)
    db.add(_book(user_id, "Throne of Glass", "tog-1", status="to-read", author="Sarah J. Maas", genres=["fantasy"], subjects=["magic"], metadata=_throne_of_glass_series(1)))
    db.add(_book(user_id, "A Court of Thorns and Roses", "acotar", status="read", rating=5, author="Sarah J. Maas", genres=["fantasy"], subjects=["magic"]))
    db.commit()
    queen = _external(1, title="Queen of Shadows", author="Sarah J. Maas", work_key="/works/OL17718538W")
    queen["genres"] = ["fantasy"]
    queen["subjects"] = ["magic"]
    monkeypatch.setattr(
        "backend.services.recommendation_discovery._run_aggregation",
        lambda _query, _local, allow_external=True, result_limit=None: _provider_aggregation([queen] if allow_external else [], source="open_library"),
    )

    result = get_recommendation(db, user_id, top_n=10, style="balanced")

    assert all(item["title"] != "Queen of Shadows" for item in result)


def test_alternate_language_throne_of_glass_shares_series_position(monkeypatch):
    db = _session()
    user_id = _profile(db)
    db.add(_book(user_id, "A Court of Thorns and Roses", "acotar", status="read", rating=5, author="Sarah J. Maas", genres=["fantasy"], subjects=["magic"]))
    db.commit()
    translated = _external(1, title="Trono de cristal", author="Sarah J. Maas", work_key="/works/TOG-SPANISH")
    translated["language"] = "spa"
    translated["genres"] = ["fantasy"]
    translated["subjects"] = ["magic"]
    monkeypatch.setattr(
        "backend.services.recommendation_discovery._run_aggregation",
        lambda _query, _local, allow_external=True, result_limit=None: _provider_aggregation([translated] if allow_external else [], source="open_library"),
    )

    result = get_recommendation(db, user_id, top_n=10, style="balanced")
    match = next(item for item in result if item["title"] == "Trono de cristal")

    assert match["canonical_series_identity"] == "series:throne-of-glass"
    assert match["series_position"] == 1.0


def test_final_recommendations_limit_same_canonical_series_to_one():
    rows = [
        {
            "Title": "Anchor Fantasy",
            "Authors": "Sarah J. Maas",
            "ISBN/UID": "anchor",
            "Read Status": "read",
            "Star Rating": 5,
            "Genres": ["fantasy"],
            "Subjects": ["magic"],
            "In Library": True,
        },
        {
            "Title": "Throne of Glass",
            "Authors": "Sarah J. Maas",
            "ISBN/UID": "tog-1",
            "Read Status": "to-read",
            "Genres": ["fantasy"],
            "Subjects": ["magic"],
            "In Library": False,
            "Source Type": "external_discovery",
            "Canonical Series Identity": "series:throne-of-glass",
            "Series Name": "Throne of Glass",
            "Series Position": 1,
            "Discovery Query": "Sarah J. Maas fantasy",
            "Discovery Cluster ID": "fantasy",
            "Discovery Query Confidence": 0.9,
            "Discovery Specific Genres": ["fantasy"],
            "Discovery Specific Themes": ["magic"],
        },
        {
            "Title": "Crown of Midnight",
            "Authors": "Sarah J. Maas",
            "ISBN/UID": "tog-2",
            "Read Status": "to-read",
            "Genres": ["fantasy"],
            "Subjects": ["magic"],
            "In Library": False,
            "Source Type": "external_discovery",
            "Canonical Series Identity": "series:throne-of-glass",
            "Series Name": "Throne of Glass",
            "Series Position": 2,
            "Discovery Query": "Sarah J. Maas fantasy",
            "Discovery Cluster ID": "fantasy",
            "Discovery Query Confidence": 0.9,
            "Discovery Specific Genres": ["fantasy"],
            "Discovery Specific Themes": ["magic"],
        },
    ]

    result = build_recommendations(pd.DataFrame(rows), top_n=10, style="balanced")
    series_items = [item for item in result if item.get("canonical_series_identity") == "series:throne-of-glass"]

    assert len(series_items) == 1


def test_open_library_candidates_can_appear(monkeypatch):
    db = _session()
    user_id = _profile(db)
    _seed_anchor_and_library_candidates(db, user_id, library_count=0)
    candidate = _external(1, title="Open Library Discovery", work_key="/works/OL-OPEN")
    candidate["metadata_source"] = "open_library"
    monkeypatch.setattr(
        "backend.services.recommendation_discovery._run_aggregation",
        lambda _query, _local, allow_external=True: _provider_aggregation([candidate] if allow_external else [], source="open_library"),
    )

    result = get_recommendation(db, user_id, top_n=10, style="balanced")

    match = next(item for item in result if item["title"] == "Open Library Discovery")
    assert match["external_discovery"] is True
    assert match["discovery_source"] == "open_library"


def test_librarything_candidates_can_appear(monkeypatch):
    db = _session()
    user_id = _profile(db)
    _seed_anchor_and_library_candidates(db, user_id, library_count=0)
    candidate = _external(2, title="LibraryThing Discovery", work_key="/works/LT-DISCOVERY")
    candidate["metadata_source"] = "librarything"
    monkeypatch.setattr(
        "backend.services.recommendation_discovery._run_aggregation",
        lambda _query, _local, allow_external=True: _provider_aggregation([candidate] if allow_external else [], source="librarything"),
    )

    result = get_recommendation(db, user_id, top_n=10, style="balanced")

    match = next(item for item in result if item["title"] == "LibraryThing Discovery")
    assert match["external_discovery"] is True
    assert match["discovery_source"] == "librarything"


def test_external_discovery_runs_when_local_pool_is_insufficient(monkeypatch):
    db = _session()
    user_id = _profile(db)
    _seed_anchor_and_library_candidates(db, user_id, library_count=1)
    calls: list[bool] = []

    def aggregation(_query, _local, allow_external=True):
        calls.append(allow_external)
        return _provider_aggregation([_external(3)] if allow_external else [], source="open_library")

    monkeypatch.setattr("backend.services.recommendation_discovery._run_aggregation", aggregation)

    result = get_recommendation(db, user_id, top_n=10, style="balanced")

    assert False in calls
    assert True in calls
    assert any(item["external_discovery"] for item in result)


def test_returns_ten_when_external_providers_have_enough_candidates(monkeypatch):
    db = _session()
    user_id = _profile(db)
    _seed_anchor_and_library_candidates(db, user_id, library_count=0)
    external = [
        _external(index, title=f"Provider Candidate {index}", work_key=f"/works/OL-PROVIDER-{index}", author=f"External Author {index}")
        for index in range(12)
    ]
    monkeypatch.setattr(
        "backend.services.recommendation_discovery._run_aggregation",
        lambda _query, _local, allow_external=True: _provider_aggregation(external if allow_external else [], source="open_library"),
    )

    result = get_recommendation(db, user_id, top_n=10, style="balanced")

    assert len(result) == 10
    assert all(item["external_discovery"] for item in result)


def test_external_provider_receives_configured_discovery_result_limit(monkeypatch):
    db = _session()
    user_id = _profile(db)
    _seed_anchor_and_library_candidates(db, user_id, library_count=0)
    external = [
        _external(index, title=f"Provider Candidate {index}", work_key=f"/works/OL-LIMIT-{index}", author=f"External Author {index}")
        for index in range(20)
    ]
    observed_limits: list[int | None] = []

    def aggregation(_query, _local, allow_external=True, result_limit=None):
        observed_limits.append(result_limit)
        return _provider_aggregation(external if allow_external else [], source="open_library")

    monkeypatch.setattr("backend.services.recommendation_discovery._run_aggregation", aggregation)

    result = get_recommendation(db, user_id, top_n=10, style="balanced")

    assert observed_limits
    assert 20 in observed_limits
    assert len(result) == 10


def test_cached_series_metadata_recommends_next_external_installment(monkeypatch):
    db = _session()
    user_id = _profile(db)
    db.add(
        _book(
            user_id,
            "Series Book One",
            "series-1",
            status="read",
            rating=5,
            author="Series Author",
            genres=["fantasy"],
            subjects=["magic"],
            metadata={
                "series": {
                    "series_name": "Example Saga",
                    "series_position": 1,
                    "series_confidence": 0.9,
                    "series_source": "trusted_fixture",
                    "series_books": [
                        {"title": "Series Book One", "author": "Series Author", "position": 1},
                        {"title": "Series Book Two", "author": "Series Author", "position": 2, "work_id": "/works/SERIES-2"},
                    ],
                }
            },
        )
    )
    db.commit()
    monkeypatch.setattr(
        "backend.services.recommendation_discovery._run_aggregation",
        lambda _query, _local, allow_external=True: _provider_aggregation([], source="open_library"),
    )

    result = get_recommendation(db, user_id, top_n=10, style="balanced")

    match = next(item for item in result if item["title"] == "Series Book Two")
    assert match["external_discovery"] is True
    assert match["discovery_source"] == "series_metadata"
    assert match["series_name"] == "Example Saga"
    assert match["score_breakdown"]["series_continuity_boost"] > 0


def test_completed_naturals_only_recommends_killer_instinct(monkeypatch, caplog):
    caplog.set_level("INFO")
    db = _session()
    user_id = _profile(db)
    db.add(
        _book(
            user_id,
            "The Naturals",
            "naturals-1",
            status="read",
            rating=5,
            author="Jennifer Lynn Barnes",
            genres=["mystery"],
            subjects=["serial killers"],
            metadata={"series": _naturals_series(1)},
        )
    )
    db.commit()
    provider = [
        _external(1, title="Killer Instinct", work_key="/works/NATURALS-2", author="Jennifer Lynn Barnes", series=_naturals_series(2)),
        _external(2, title="All In", work_key="/works/NATURALS-3", author="Jennifer Lynn Barnes", series=_naturals_series(3)),
        _external(3, title="Bad Blood", work_key="/works/NATURALS-4", author="Jennifer Lynn Barnes", series=_naturals_series(4)),
    ]
    monkeypatch.setattr(
        "backend.services.recommendation_discovery._run_aggregation",
        lambda _query, _local, allow_external=True: _provider_aggregation(provider if allow_external else [], source="open_library"),
    )

    result = get_recommendation(db, user_id, top_n=10, style="balanced")
    titles = [item["title"] for item in result]

    assert "Killer Instinct" in titles
    assert "All In" not in titles
    assert "Bad Blood" not in titles
    assert "reason=series_order_skip" in caplog.text
    assert "title=All In" in caplog.text
    assert "title=Bad Blood" in caplog.text


def test_naturals_sections_payload_only_shows_earliest_unread_installment(monkeypatch):
    db = _session()
    user_id = _profile(db)
    db.add(
        _book(
            user_id,
            "The Naturals",
            "naturals-1",
            status="read",
            rating=5,
            author="Jennifer Lynn Barnes",
            genres=["mystery"],
            subjects=["serial killers"],
            work_key="/works/NATURALS-1",
            metadata={"series": _naturals_series(1)},
        )
    )
    db.commit()
    provider = [
        _external(1, title="Killer Instinct", work_key="/works/NATURALS-2", author="Jennifer Lynn Barnes", series=_naturals_series(2)),
        _external(2, title="All In", work_key="/works/NATURALS-3", author="Jennifer Lynn Barnes", series=_naturals_series(3)),
        _external(3, title="Bad Blood", work_key="/works/NATURALS-4", author="Jennifer Lynn Barnes", series=_naturals_series(4)),
    ]
    monkeypatch.setattr(
        "backend.services.recommendation_discovery._run_aggregation",
        lambda _query, _local, allow_external=True: _provider_aggregation(provider if allow_external else [], source="open_library"),
    )

    payload = get_recommendation_sections(db, user_id, top_n=10, style="balanced")
    all_items = [item for section in payload["sections"] for item in section["items"]]
    titles = [item["canonical_title"] for item in all_items]
    naturals_items = [item for item in all_items if item.get("provider") in {"open_library", "series_metadata"}]

    assert titles.count("Killer Instinct") == 1
    assert "All In" not in titles
    assert "Bad Blood" not in titles
    assert len(naturals_items) == 1
    assert naturals_items[0]["canonical_title"] == "Killer Instinct"
    assert naturals_items[0]["canonical_identity"] in {"work:/works/naturals-2", "work:/works/ol19987695w"}
    assert naturals_items[0]["source"] == "external"
    assert naturals_items[0]["library_state"]["in_library"] is False


def test_metadata_less_naturals_library_rows_use_trusted_order_in_sections(monkeypatch):
    db = _session()
    user_id = _profile(db)
    db.add_all(
        [
            _book(
                user_id,
                "The Naturals",
                "9781423168232",
                status="read",
                rating=4.75,
                author="Jennifer Lynn Barnes",
                genres=["mystery"],
                subjects=["serial killers"],
                work_key="/works/OL19987694W",
                metadata=None,
            ),
            _book(
                user_id,
                "All In",
                "9781484716434",
                status="to-read",
                author="Jennifer Lynn Barnes",
                genres=["mystery"],
                subjects=["criminal profilers"],
                work_key="/works/OL20011828W",
                metadata=None,
            ),
            _book(
                user_id,
                "Bad Blood",
                "9781484757321",
                status="to-read",
                author="Jennifer Lynn Barnes",
                genres=["mystery"],
                subjects=["mystery and detective stories"],
                work_key="/works/OL17639867W",
                metadata=None,
            ),
        ]
    )
    db.commit()
    monkeypatch.setattr(
        "backend.services.recommendation_discovery._run_aggregation",
        lambda _query, _local, allow_external=True: _provider_aggregation([], source="open_library"),
    )

    payload = get_recommendation_sections(db, user_id, top_n=10, style="balanced")
    all_items = [item for section in payload["sections"] for item in section["items"]]
    titles = [item["canonical_title"] for item in all_items]
    killer = next(item for item in all_items if item["canonical_title"] == "Killer Instinct")

    assert titles.count("Killer Instinct") == 1
    assert "All In" not in titles
    assert "Bad Blood" not in titles
    assert killer["source"] == "external"
    assert killer["series_name"] == "The Naturals"
    assert killer["series_position"] == 2.0
    assert killer["provider"] == "series_metadata"


def test_completed_naturals_and_killer_instinct_recommends_all_in_only(monkeypatch):
    db = _session()
    user_id = _profile(db)
    db.add_all(
        [
            _book(user_id, "The Naturals", "naturals-1", status="read", rating=5, author="Jennifer Lynn Barnes", metadata={"series": _naturals_series(1)}),
            _book(user_id, "Killer Instinct", "naturals-2", status="read", rating=5, author="Jennifer Lynn Barnes", metadata={"series": _naturals_series(2)}),
        ]
    )
    db.commit()
    provider = [
        _external(2, title="All In", work_key="/works/NATURALS-3", author="Jennifer Lynn Barnes", series=_naturals_series(3)),
        _external(3, title="Bad Blood", work_key="/works/NATURALS-4", author="Jennifer Lynn Barnes", series=_naturals_series(4)),
    ]
    monkeypatch.setattr(
        "backend.services.recommendation_discovery._run_aggregation",
        lambda _query, _local, allow_external=True: _provider_aggregation(provider if allow_external else [], source="open_library"),
    )

    result = get_recommendation(db, user_id, top_n=10, style="balanced")
    titles = [item["title"] for item in result]

    assert "All In" in titles
    assert "Bad Blood" not in titles


def test_noncontiguous_completed_naturals_still_requires_killer_instinct(monkeypatch):
    db = _session()
    user_id = _profile(db)
    db.add_all(
        [
            _book(user_id, "The Naturals", "naturals-1", status="read", rating=5, author="Jennifer Lynn Barnes", metadata={"series": _naturals_series(1)}),
            _book(user_id, "All In", "naturals-3", status="read", rating=5, author="Jennifer Lynn Barnes", metadata={"series": _naturals_series(3)}),
        ]
    )
    db.commit()
    provider = [
        _external(1, title="Killer Instinct", work_key="/works/NATURALS-2", author="Jennifer Lynn Barnes", series=_naturals_series(2)),
        _external(3, title="Bad Blood", work_key="/works/NATURALS-4", author="Jennifer Lynn Barnes", series=_naturals_series(4)),
    ]
    monkeypatch.setattr(
        "backend.services.recommendation_discovery._run_aggregation",
        lambda _query, _local, allow_external=True: _provider_aggregation(provider if allow_external else [], source="open_library"),
    )

    result = get_recommendation(db, user_id, top_n=10, style="balanced")
    titles = [item["title"] for item in result]

    assert "Killer Instinct" in titles
    assert "Bad Blood" not in titles


def test_unstarted_naturals_series_recommends_first_book_only(monkeypatch):
    db = _session()
    user_id = _profile(db)
    db.add(
        _book(
            user_id,
            "The Naturals",
            "naturals-1",
            status="to-read",
            author="Jennifer Lynn Barnes",
            metadata={"series": _naturals_series(1)},
        )
    )
    db.commit()
    provider = [
        _external(1, title="Killer Instinct", work_key="/works/NATURALS-2", author="Jennifer Lynn Barnes", series=_naturals_series(2)),
        _external(2, title="All In", work_key="/works/NATURALS-3", author="Jennifer Lynn Barnes", series=_naturals_series(3)),
        _external(3, title="Bad Blood", work_key="/works/NATURALS-4", author="Jennifer Lynn Barnes", series=_naturals_series(4)),
    ]
    monkeypatch.setattr(
        "backend.services.recommendation_discovery._run_aggregation",
        lambda _query, _local, allow_external=True: _provider_aggregation(provider if allow_external else [], source="open_library"),
    )

    result = get_recommendation(db, user_id, top_n=10, style="balanced")
    titles = [item["title"] for item in result]

    assert "The Naturals" in titles
    assert "Killer Instinct" not in titles
    assert "All In" not in titles
    assert "Bad Blood" not in titles


def test_external_candidates_survive_when_ten_local_candidates_exist(monkeypatch):
    db = _session()
    user_id = _profile(db)
    _seed_anchor_and_library_candidates(db, user_id, library_count=10)
    external = [
        _external(index, title=f"Outside Candidate {index}", work_key=f"/works/OUT-{index}", author=f"Outside Author {index}")
        for index in range(6)
    ]
    monkeypatch.setattr(
        "backend.services.recommendation_discovery._run_aggregation",
        lambda _query, _local, allow_external=True: _provider_aggregation(external if allow_external else [], source="open_library"),
    )

    result = get_recommendation(db, user_id, top_n=10, style="balanced")

    assert any(item["outside_library"] for item in result)
    assert sum(1 for item in result if item["outside_library"]) >= 3
    external = next(item for item in result if item["outside_library"])
    assert external["genres"]
    assert external["subjects"]
    assert external["description"]


def test_ownership_matching_does_not_use_title_only(monkeypatch):
    db = _session()
    user_id = _profile(db)
    _seed_anchor_and_library_candidates(db, user_id, library_count=0)
    db.add(_book(user_id, "Shared Title", "owned-shared", author="Owned Author", status="to-read", work_key="/works/OWNED-SHARED"))
    db.commit()
    external = _external(
        1,
        title="Shared Title",
        author="Different Author",
        work_key="/works/EXTERNAL-SHARED",
        isbn="9780000002222",
    )
    monkeypatch.setattr(
        "backend.services.recommendation_discovery._run_aggregation",
        lambda _query, _local, allow_external=True: _provider_aggregation([external] if allow_external else [], source="open_library"),
    )

    result = get_recommendation(db, user_id, top_n=10, style="balanced")

    match = next(item for item in result if item["title"] == "Shared Title" and item["author"] == "Different Author")
    assert match["outside_library"] is True


def test_generic_fallback_discovery_runs_without_library_anchors(monkeypatch):
    db = _session()
    user_id = _profile(db)
    queries: list[str] = []

    def aggregation(query, _local, allow_external=True):
        queries.append(query)
        return _provider_aggregation([_external(7, title="Generic External")] if allow_external else [], source="open_library")

    monkeypatch.setattr("backend.services.recommendation_discovery._run_aggregation", aggregation)

    result = get_recommendation(db, user_id, top_n=10, style="balanced")

    assert queries
    assert "recent acclaimed mystery romance dystopian" in queries
    assert "award winning fiction" not in queries
    assert any(item["title"] == "Generic External" for item in result)


def test_balanced_style_returns_mixed_results_when_possible(monkeypatch):
    db = _session()
    user_id = _profile(db)
    _seed_anchor_and_library_candidates(db, user_id, library_count=8)
    monkeypatch.setattr(
        "backend.services.recommendation_discovery._run_aggregation",
        lambda _query, _local: _success_aggregation([_external(index, author=f"External Author {index}") for index in range(8)]),
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
        lambda _query, _local: _success_aggregation([_external(index, author=f"External Author {index}") for index in range(8)]),
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


def test_seeded_external_fixture_is_rejected_when_already_in_user_library(monkeypatch):
    db = _session()
    user_id = _profile(db)
    _seed_anchor_and_library_candidates(db, user_id, library_count=1)
    db.add(
        _book(
            user_id,
            "Happy Place",
            "9780593441275",
            author="Emily Henry",
            work_key="/works/OL-HAPPY-PLACE",
            edition_key="OL-HAPPY-PLACE-M",
            metadata={"librarything": {"related_isbns": ["0593441273"]}},
        )
    )
    db.commit()
    duplicate_by_title_author = _external(
        1,
        title="Happy Place",
        author="Emily Henry",
        work_key="/works/OL-DIFFERENT-HAPPY",
        isbn="9780000000001",
    )
    duplicate_by_work = _external(
        2,
        title="Alternate Happy Place",
        author="Emily Henry",
        work_key="/works/OL-HAPPY-PLACE",
        isbn="9780000000002",
    )
    duplicate_by_isbn = _external(
        3,
        title="Happy Place Other ISBN",
        author="Emily Henry",
        work_key="/works/OL-HAPPY-ISBN",
        isbn="9780593441275",
    )
    duplicate_by_related_isbn = _external(
        4,
        title="Happy Place Related ISBN",
        author="Emily Henry",
        work_key="/works/OL-HAPPY-RELATED",
        isbn="9780000000004",
    )
    duplicate_by_related_isbn["related_isbns"] = ["0593441273"]
    duplicate_by_edition = _external(
        5,
        title="Happy Place Alternate Edition",
        author="Emily Henry",
        work_key="/works/OL-HAPPY-EDITION",
        isbn="9780000000005",
    )
    duplicate_by_edition["edition_key"] = "OL-HAPPY-PLACE-M"
    absent_fixture = _external(
        6,
        title="The Very Secret Society of Irregular Witches",
        author="Sangu Mandanna",
        work_key="/works/OL-ABSENT-FIXTURE",
        isbn="9780593439357",
    )
    monkeypatch.setattr(
        "backend.services.recommendation_discovery._run_aggregation",
        lambda _query, _local: _success_aggregation(
            [
                duplicate_by_title_author,
                duplicate_by_work,
                duplicate_by_isbn,
                duplicate_by_related_isbn,
                duplicate_by_edition,
                absent_fixture,
            ]
        ),
    )

    result = get_recommendation(db, user_id, top_n=10, style="balanced")
    titles = [item["title"] for item in result]
    external_titles = [item["title"] for item in result if item["external_discovery"]]

    assert "Happy Place" not in external_titles
    assert "Alternate Happy Place" not in external_titles
    assert "Happy Place Other ISBN" not in external_titles
    assert "Happy Place Related ISBN" not in external_titles
    assert "Happy Place Alternate Edition" not in external_titles
    assert "The Very Secret Society of Irregular Witches" in titles


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
