from uuid import uuid4

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from backend.db.database import Base
from backend.db.models import Book, Profile
from backend.services.recommendation import (
    _newly_found_category,
    _newly_found_items,
    refresh_newly_found_section,
    replace_newly_found_item,
)


def _session():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine)()


def _profile(db):
    user_id = uuid4()
    db.add(Profile(id=user_id, email=f"{user_id}@example.com", username=f"u{user_id.hex[:8]}"))
    db.add(
        Book(
            user_id=user_id,
            title="Loved Fantasy",
            authors="Shelf Author",
            isbn_uid="shelf",
            read_status="completed",
            star_rating=5,
            genres=["fantasy"],
            subjects=["magic"],
            work_key="shelf",
        )
    )
    db.commit()
    return user_id


def _hc(index, title, *, genre="fiction", year=2026, work_year="default", editions=None, activity_date=None, work_key=None):
    effective_work_year = year if work_year == "default" else work_year
    return {
        "title": title,
        "authors": [f"Author {index}"],
        "isbn_uid": f"9780000000{index:03d}"[-13:],
        "description": f"A recent {genre} book.",
        "genres": [genre],
        "subjects": [genre],
        "first_publish_year": effective_work_year,
        "publication_year": effective_work_year,
        "work_publication_year": effective_work_year,
        "work_publication_date": f"{effective_work_year}-01-01" if effective_work_year else None,
        "release_date": f"{effective_work_year}-01-01" if effective_work_year else None,
        "edition_release_dates": editions if editions is not None else [f"{year}-01-01"],
        "edition_release_years": [int(value[:4]) for value in (editions if editions is not None else [f"{year}-01-01"]) if value],
        "publication_year_source": "work" if effective_work_year else "unknown",
        "metadata_source": "hardcover",
        "work_key": work_key or f"hardcover:book:{index}",
        "edition_key": f"hardcover:edition:{index}",
        "related_isbns": [],
        "source_urls": [f"https://hardcover.app/books/{index}"],
        "provider_rating": 4.1,
        "provider_rating_count": 100,
        "provider_user_count": 500,
        "provider_activity_count": 50,
        "provider_activity_date": activity_date,
        "confidence_score": 0.9,
    }


def _pool():
    return [
        _hc(1, "Recent Fiction", genre="fiction", year=2026),
        _hc(2, "Recent Romance", genre="romance", year=2026),
        _hc(3, "Recent Fantasy", genre="fantasy", year=2025),
        _hc(4, "Recent Mystery", genre="mystery thriller", year=2025),
        _hc(5, "Recent Literary", genre="literary fiction", year=2024),
        _hc(6, "Old Classic", genre="classic", year=1818),
        _hc(7, "Old Work New Edition", genre="classic", year=2026, work_year=1818, editions=["2026-01-01"]),
        _hc(8, "Unknown Date", genre="fiction", year=2026, work_year=None, editions=[]),
        _hc(9, "Activity Date Only", genre="fiction", year=2026, work_year=None, editions=[], activity_date="2026-07-01"),
        _hc(10, "Recent Boxed Set", genre="fantasy", year=2026),
        _hc(11, "Alternate Recent Fantasy", genre="fantasy", year=2025, work_key="hardcover:book:3"),
    ]


def test_romance_classifier_recognizes_explicit_romance_signals():
    assert _newly_found_category(_hc(30, "Contemporary", genre="contemporary romance")) == "romance"
    assert _newly_found_category(_hc(31, "Historical", genre="historical romance")) == "romance"
    assert _newly_found_category(_hc(32, "Comedy", genre="romantic comedy")) == "romance"
    assert _newly_found_category(_hc(33, "Stories", genre="love stories")) == "romance"


def test_romance_classifier_does_not_overclassify_generic_womens_fiction():
    candidate = _hc(
        34,
        "Family Saga",
        genre="women's fiction",
    )
    candidate["description"] = "A family drama about sisters, work, and a new beginning."

    assert _newly_found_category(candidate) == "fiction"


def _search_factory(calls):
    def search(query):
        calls.append(query)
        return _pool()

    return search


def test_newly_found_replace_accepts_recent_and_rejects_old_unknown_activity(monkeypatch):
    db = _session()
    user_id = _profile(db)
    calls = []
    monkeypatch.setenv("HARDCOVER_ENABLED", "true")
    monkeypatch.setenv("HARDCOVER_API_TOKEN", "token")
    monkeypatch.setattr("backend.services.recommendation.search_candidates", _search_factory(calls))

    response = refresh_newly_found_section(db, user_id, preference="mixed")
    titles = [item["canonical_title"] for item in response["newly_found"]]
    diagnostics = response["diagnostics"]["rejection_diagnostics"]

    assert "Recent Fiction" in titles
    assert "Old Classic" not in titles
    assert "Old Work New Edition" not in titles
    assert "Unknown Date" not in titles
    assert "Activity Date Only" not in titles
    assert "Recent Boxed Set" not in titles
    assert diagnostics["work_too_old"] >= 1
    assert diagnostics["recent_edition_of_old_work"] >= 1
    assert diagnostics["missing_publication_date"] >= 2
    assert diagnostics["collection_or_bundle"] >= 1
    assert calls


def test_default_newly_found_returns_five_valid_recent_cards(monkeypatch):
    monkeypatch.setenv("HARDCOVER_ENABLED", "true")
    monkeypatch.setenv("HARDCOVER_API_TOKEN", "token")
    monkeypatch.setattr(
        "backend.services.recommendation.search_candidates",
        lambda _query: [
            _hc(101, "Recent Fiction", genre="fiction", year=2026),
            _hc(102, "Recent Romance", genre="romance", year=2026),
            _hc(103, "Recent Fantasy", genre="fantasy", year=2025),
            _hc(104, "Recent Mystery", genre="mystery thriller", year=2025),
            _hc(105, "Recent Literary", genre="literary fiction", year=2024),
        ],
    )

    items, diagnostics = _newly_found_items(set(), [])

    assert len(items) == 5
    assert diagnostics["final_count"] == 5
    assert diagnostics["source_path"] == "initial"
    assert diagnostics["accepted_count"] >= 5
    assert diagnostics["deduped_count"] >= 5


def test_default_newly_found_returns_three_when_only_three_valid_exist(monkeypatch):
    monkeypatch.setenv("HARDCOVER_ENABLED", "true")
    monkeypatch.setenv("HARDCOVER_API_TOKEN", "token")
    monkeypatch.setattr(
        "backend.services.recommendation.search_candidates",
        lambda _query: [
            _hc(111, "Recent Fiction", genre="fiction", year=2026),
            _hc(112, "Recent Romance", genre="romance", year=2025),
            _hc(113, "Recent Mystery", genre="mystery thriller", year=2024),
            _hc(114, "Old Classic", genre="classic", year=1818),
        ],
    )

    items, diagnostics = _newly_found_items(set(), [])

    assert len(items) == 3
    assert diagnostics["final_count"] == 3
    assert diagnostics["source_path"] == "initial"
    assert diagnostics["rejection_counts"]["work_too_old"] >= 1


def test_initial_and_refresh_use_same_recent_filtering_rules(monkeypatch):
    db = _session()
    user_id = _profile(db)
    monkeypatch.setenv("HARDCOVER_ENABLED", "true")
    monkeypatch.setenv("HARDCOVER_API_TOKEN", "token")
    monkeypatch.setattr(
        "backend.services.recommendation.search_candidates",
        lambda _query: [
            _hc(116, "Recent Fiction", genre="fiction", year=2026),
            _hc(117, "Recent Romance", genre="romance", year=2025),
            _hc(118, "Old Classic", genre="classic", year=1818),
            _hc(119, "Unknown Date", genre="fiction", year=2026, work_year=None, editions=[]),
        ],
    )

    initial_items, initial_diagnostics = _newly_found_items(set(), [])
    refresh_response = refresh_newly_found_section(db, user_id, preference="mixed")

    assert [item["canonical_title"] for item in initial_items] == [
        item["canonical_title"] for item in refresh_response["newly_found"]
    ]
    assert initial_diagnostics["rejection_counts"]["work_too_old"] >= 1
    assert refresh_response["diagnostics"]["rejection_counts"]["work_too_old"] >= 1
    assert initial_diagnostics["source_path"] == "initial"
    assert refresh_response["diagnostics"]["source_path"] == "refresh"


def test_default_newly_found_has_no_artificial_one_card_cap(monkeypatch):
    monkeypatch.setenv("HARDCOVER_ENABLED", "true")
    monkeypatch.setenv("HARDCOVER_API_TOKEN", "token")
    monkeypatch.setattr(
        "backend.services.recommendation.search_candidates",
        lambda _query: [
            _hc(121, "Recent One", genre="fiction", year=2026),
            _hc(122, "Recent Two", genre="fiction", year=2026),
        ],
    )

    items, _diagnostics = _newly_found_items(set(), [])

    assert [item["canonical_title"] for item in items] == ["Recent One", "Recent Two"]


def test_default_newly_found_duplicate_editions_do_not_hide_available_unique_works(monkeypatch):
    monkeypatch.setenv("HARDCOVER_ENABLED", "true")
    monkeypatch.setenv("HARDCOVER_API_TOKEN", "token")
    monkeypatch.setattr(
        "backend.services.recommendation.search_candidates",
        lambda _query: [
            _hc(131, "Duplicate A", genre="fiction", year=2026, work_key="hardcover:work:dup"),
            _hc(132, "Duplicate B", genre="fiction", year=2026, work_key="hardcover:work:dup"),
            _hc(133, "Unique One", genre="romance", year=2026),
            _hc(134, "Unique Two", genre="fantasy", year=2025),
            _hc(135, "Unique Three", genre="mystery thriller", year=2025),
            _hc(136, "Unique Four", genre="literary fiction", year=2024),
        ],
    )

    items, diagnostics = _newly_found_items(set(), [])
    titles = [item["canonical_title"] for item in items]

    assert len(items) == 5
    assert len({"Duplicate A", "Duplicate B"} & set(titles)) == 1
    assert diagnostics["rejection_counts"]["duplicate_in_library"] >= 1


def test_default_newly_found_category_diversity_does_not_discard_valid_books(monkeypatch):
    monkeypatch.setenv("HARDCOVER_ENABLED", "true")
    monkeypatch.setenv("HARDCOVER_API_TOKEN", "token")
    monkeypatch.setattr(
        "backend.services.recommendation.search_candidates",
        lambda _query: [_hc(index, f"Romance {index}", genre="romance", year=2026) for index in range(141, 146)],
    )

    items, diagnostics = _newly_found_items(set(), [])

    assert len(items) == 5
    assert diagnostics["category_distribution"]["romance"] >= 5


def test_default_newly_found_expands_to_replacement_romance_pool(monkeypatch):
    monkeypatch.setenv("HARDCOVER_ENABLED", "true")
    monkeypatch.setenv("HARDCOVER_API_TOKEN", "token")

    def search(query):
        if query.startswith("2025 romance"):
            return [
                _hc(151, "Replacement Pool Romance One", genre="romance", year=2025),
                _hc(152, "Replacement Pool Romance Two", genre="contemporary romance", year=2025),
            ]
        return [_hc(153, "Old Generic", genre="classic", year=1900)]

    monkeypatch.setattr("backend.services.recommendation.search_candidates", search)

    items, diagnostics = _newly_found_items(set(), [])

    assert [item["canonical_title"] for item in items] == [
        "Replacement Pool Romance One",
        "Replacement Pool Romance Two",
    ]
    assert diagnostics["provider_refetch_performed"] is True


def test_default_newly_found_empty_remains_valid_when_no_recent_candidates(monkeypatch):
    monkeypatch.setenv("HARDCOVER_ENABLED", "true")
    monkeypatch.setenv("HARDCOVER_API_TOKEN", "token")
    monkeypatch.setattr(
        "backend.services.recommendation.search_candidates",
        lambda _query: [_hc(161, "Old Only", genre="classic", year=1900)],
    )

    items, diagnostics = _newly_found_items(set(), [])

    assert items == []
    assert diagnostics["final_count"] == 0
    assert diagnostics["rejection_counts"]["work_too_old"] >= 1


def test_refresh_excludes_currently_visible_newly_found_ids(monkeypatch):
    db = _session()
    user_id = _profile(db)
    monkeypatch.setenv("HARDCOVER_ENABLED", "true")
    monkeypatch.setenv("HARDCOVER_API_TOKEN", "token")
    monkeypatch.setattr(
        "backend.services.recommendation.search_candidates",
        lambda _query: [
            _hc(171, "Visible Recent", genre="fiction", year=2026),
            _hc(172, "Next Recent", genre="romance", year=2026),
            _hc(173, "Another Recent", genre="fantasy", year=2025),
        ],
    )

    response = refresh_newly_found_section(
        db,
        user_id,
        current_recommendation_ids=["newly_found:hardcover:book:171"],
        excluded_recommendation_ids=[],
        preference="mixed",
    )

    titles = [item["canonical_title"] for item in response["newly_found"]]
    assert "Visible Recent" not in titles
    assert "Next Recent" in titles
    assert response["diagnostics"]["source_path"] == "refresh"


def test_newly_found_replace_excludes_visible_skipped_same_work_and_filters_category(monkeypatch):
    db = _session()
    user_id = _profile(db)
    calls = []
    monkeypatch.setenv("HARDCOVER_ENABLED", "true")
    monkeypatch.setenv("HARDCOVER_API_TOKEN", "token")
    monkeypatch.setattr("backend.services.recommendation.search_candidates", _search_factory(calls))

    response = replace_newly_found_item(
        db,
        user_id,
        current_recommendation_ids=["newly_found:hardcover:book:3"],
        excluded_recommendation_ids=["newly_found:hardcover:book:1"],
        replace_recommendation_id="newly_found:hardcover:book:3",
        category="fantasy_scifi",
    )

    assert response["replacement"] is None
    assert response["reason"] == "no_matching_candidates"


def test_newly_found_replacement_preserves_other_cards_in_client_order(monkeypatch):
    db = _session()
    user_id = _profile(db)
    calls = []
    monkeypatch.setenv("HARDCOVER_ENABLED", "true")
    monkeypatch.setenv("HARDCOVER_API_TOKEN", "token")
    monkeypatch.setattr("backend.services.recommendation.search_candidates", _search_factory(calls))
    row = ["newly_found:hardcover:book:1", "newly_found:hardcover:book:2", "newly_found:hardcover:book:3"]

    response = replace_newly_found_item(
        db,
        user_id,
        current_recommendation_ids=row,
        excluded_recommendation_ids=[],
        replace_recommendation_id=row[1],
        category="mystery_thriller",
    )
    next_row = [row[0], response["replacement"]["recommendation_id"], row[2]]

    assert next_row[0] == row[0]
    assert next_row[2] == row[2]
    assert response["replacement"]["canonical_title"] == "Recent Mystery"


def test_newly_found_refresh_returns_zero_without_old_backfill(monkeypatch):
    db = _session()
    user_id = _profile(db)
    monkeypatch.setenv("HARDCOVER_ENABLED", "true")
    monkeypatch.setenv("HARDCOVER_API_TOKEN", "token")
    monkeypatch.setattr(
        "backend.services.recommendation.search_candidates",
        lambda _query: [_hc(20, "Old Only", genre="classic", year=1900)],
    )

    response = refresh_newly_found_section(db, user_id, preference="mixed")

    assert response["newly_found"] == []
    assert response["remaining_candidate_count"] == 0


def test_newly_found_query_diagnostics_include_counts_and_years(monkeypatch):
    db = _session()
    user_id = _profile(db)
    calls = []
    monkeypatch.setenv("HARDCOVER_ENABLED", "true")
    monkeypatch.setenv("HARDCOVER_API_TOKEN", "token")
    monkeypatch.setattr("backend.services.recommendation.search_candidates", _search_factory(calls))

    response = refresh_newly_found_section(db, user_id, preference="romance")
    first_query = response["diagnostics"]["queries"][0]

    assert "query" in first_query
    assert first_query["raw_count"] > 0
    assert first_query["normalized_count"] == first_query["raw_count"]
    assert first_query["recent_count"] >= 1
    assert "2026" in first_query["year_distribution"]


def test_newly_found_search_uses_bounded_query_cache_path(monkeypatch):
    db = _session()
    user_id = _profile(db)
    calls = []
    monkeypatch.setenv("HARDCOVER_ENABLED", "true")
    monkeypatch.setenv("HARDCOVER_API_TOKEN", "token")
    monkeypatch.setattr("backend.services.recommendation.search_candidates", _search_factory(calls))

    replace_newly_found_item(db, user_id, category="romance")

    assert calls
    assert all("new" in query for query in calls[:2])


def test_romance_specific_refetch_occurs_when_initial_pool_has_no_romance(monkeypatch):
    db = _session()
    user_id = _profile(db)
    calls = []

    def search(query):
        calls.append(query)
        if "romance" in query and "2024" in query:
            return [_hc(60, "Recent Historical Romance", genre="historical romance", year=2024)]
        return [_hc(61, "Recent Fantasy", genre="fantasy", year=2026)]

    monkeypatch.setenv("HARDCOVER_ENABLED", "true")
    monkeypatch.setenv("HARDCOVER_API_TOKEN", "token")
    monkeypatch.setattr("backend.services.recommendation.search_candidates", search)

    response = replace_newly_found_item(db, user_id, category="romance")

    assert response["replacement"]["canonical_title"] == "Recent Historical Romance"
    assert response["diagnostics"]["category_requested"] == "romance"
    assert response["diagnostics"]["provider_refetch_performed"] is True
    assert response["diagnostics"]["category_match_count"] >= 1
    assert any("2024" in query for query in calls)


def test_romance_replacement_excludes_visible_and_skipped_then_returns_next(monkeypatch):
    db = _session()
    user_id = _profile(db)

    def search(_query):
        return [
            _hc(70, "Visible Romance", genre="romance", year=2026),
            _hc(71, "Skipped Romance", genre="romance", year=2026),
            _hc(72, "Next Romance", genre="contemporary romance", year=2025),
        ]

    monkeypatch.setenv("HARDCOVER_ENABLED", "true")
    monkeypatch.setenv("HARDCOVER_API_TOKEN", "token")
    monkeypatch.setattr("backend.services.recommendation.search_candidates", search)

    response = replace_newly_found_item(
        db,
        user_id,
        current_recommendation_ids=["newly_found:hardcover:book:70"],
        excluded_recommendation_ids=["newly_found:hardcover:book:71"],
        replace_recommendation_id="newly_found:hardcover:book:70",
        category="romance",
    )

    assert response["replacement"]["canonical_title"] == "Next Romance"


def test_romance_no_valid_candidate_returns_null_reason(monkeypatch):
    db = _session()
    user_id = _profile(db)
    monkeypatch.setenv("HARDCOVER_ENABLED", "true")
    monkeypatch.setenv("HARDCOVER_API_TOKEN", "token")
    monkeypatch.setattr(
        "backend.services.recommendation.search_candidates",
        lambda _query: [_hc(80, "Old Romance", genre="romance", year=1900)],
    )

    response = replace_newly_found_item(db, user_id, category="romance")

    assert response["replacement"] is None
    assert response["reason"] == "no_matching_candidates"
    assert response["diagnostics"]["category_requested"] == "romance"
