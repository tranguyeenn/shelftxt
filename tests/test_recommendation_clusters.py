from collections import Counter
from datetime import date
from types import SimpleNamespace
from uuid import uuid4

import pandas as pd
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from backend.db.database import Base
from backend.db.models import Book, Profile
from backend.services.recommendation_clusters import (
    _cluster_anchor_groups,
    _cluster_dataframe,
    _final_admission_decision,
    _local_cluster_discovery_needs,
    build_reading_clusters_from_dataframe,
    flatten_clustered_recommendations,
    get_clustered_recommendations,
)
from backend.services.recommendation_discovery import _structured_discovery_queries
from backend.services.recommendation_feedback import create_feedback
from backend.schemas.recommendation import RecommendationFeedbackCreate


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
    *,
    author="Author",
    status="to-read",
    rating=None,
    genres=None,
    subjects=None,
    work_key=None,
    end_date=None,
):
    completed = status in {"read", "completed"}
    if isinstance(end_date, str):
        year, month, day = (int(part) for part in end_date.split("-"))
        end_date = date(year, month, day)
    return Book(
        user_id=user_id,
        title=title,
        authors=author,
        isbn_uid=f"isbn-{title.casefold().replace(' ', '-')}",
        read_status=status,
        star_rating=rating,
        total_pages=320,
        pages_read=320 if completed else 0,
        progress_percent=100 if completed else 0,
        end_date=end_date,
        last_date_read=end_date,
        genres=genres or [],
        subjects=subjects or [],
        work_key=work_key or f"/works/{title.casefold().replace(' ', '-')}",
    )


def _seed_multi_taste_profile(db, user_id):
    anchors = [
        _book(user_id, "Anna Karenina", author="Leo Tolstoy", status="read", rating=5, genres=["classics"], subjects=["russian literature"]),
        _book(user_id, "War and Peace", author="Leo Tolstoy", status="read", rating=5, genres=["classics"], subjects=["literary fiction"]),
        _book(user_id, "The Hunger Games", author="Suzanne Collins", status="read", rating=5, genres=["young adult"], subjects=["dystopian survival"]),
        _book(user_id, "The Naturals", author="Jennifer Lynn Barnes", status="read", rating=5, genres=["mystery"], subjects=["profiling crime thriller"]),
        _book(user_id, "Book Lovers", author="Emily Henry", status="read", rating=5, genres=["romance"], subjects=["contemporary romance"]),
        _book(user_id, "Deep End", author="Ali Hazelwood", status="read", rating=4, genres=["new adult"], subjects=["relationships romance"]),
    ]
    candidates = [
        _book(user_id, "Great Expectations", author="Charles Dickens", genres=["classics"], subjects=["literary fiction"]),
        _book(user_id, "A Tale of Two Cities", author="Charles Dickens", genres=["classics"], subjects=["historical fiction"]),
        _book(user_id, "Scythe", author="Neal Shusterman", genres=["young adult"], subjects=["dystopian science fiction"]),
        _book(user_id, "Brave New World", author="Aldous Huxley", genres=["science fiction"], subjects=["dystopian speculative fiction"]),
        _book(user_id, "Killer Instinct", author="Jennifer Lynn Barnes", genres=["mystery"], subjects=["profiling crime thriller"]),
        _book(user_id, "Truly Devious", author="Maureen Johnson", genres=["mystery"], subjects=["detective puzzle thriller"]),
        _book(user_id, "Happy Place", author="Emily Henry", genres=["romance"], subjects=["contemporary romance relationships"]),
        _book(user_id, "Funny Story", author="Emily Henry", genres=["romance"], subjects=["romantic comedy"]),
    ]
    db.add_all([*anchors, *candidates])
    db.commit()


def _cluster(clusters, cluster_id):
    return next(cluster for cluster in clusters if cluster["cluster_id"] == cluster_id)


def _titles(cluster):
    return {item["canonical_title"] for item in cluster["recommendations"]}


def _item_titles(cluster):
    return {
        item.get("title")
        or item.get("display_title")
        or item.get("canonical_title")
        or (item.get("book") or {}).get("title")
        or (item.get("recommended_book") or {}).get("title")
        for item in cluster["recommendations"]
    }


def _external_result(title, *, author="External Author", work_key=None, genres=None, subjects=None):
    slug = title.casefold().replace(" ", "-").replace("'", "")
    return {
        "title": title,
        "authors": [author],
        "isbn_uid": f"978{abs(hash(title)) % 10_000_000_000:010d}",
        "description": "A discovered book with matching fallback identity evidence.",
        "cover_url": f"https://example.com/{slug}.jpg",
        "total_pages": 280,
        "subjects": subjects or [],
        "genres": genres or [],
        "first_publish_year": 2020,
        "metadata_source": "open_library",
        "work_key": work_key or f"/works/{slug}",
        "edition_key": f"{slug}-edition",
        "related_isbns": [],
        "confidence_score": 0.88,
    }


def _aggregation(results):
    return SimpleNamespace(
        results=results,
        outcomes=[
            SimpleNamespace(source="local", success=True, result_count=0, outcome="success", error_type=None),
            SimpleNamespace(source="open_library", success=True, result_count=len(results), outcome="success", error_type=None),
        ],
    )


def _empty_exploration():
    return (
        [],
        SimpleNamespace(
            exploration_requests=[],
            total_open_library_candidates_fetched=0,
            broad_exploration_candidates=0,
        ),
    )


def _recommendation_item(
    title,
    *,
    score=0.5,
    reader_likelihood=0.5,
    source="library",
    reason="Because you enjoyed Anchor Book, this shares survival competitions.",
    genres=None,
    subjects=None,
    breakdown=None,
):
    score_breakdown = {"reader_likelihood_score": reader_likelihood, **(breakdown or {})}
    return {
        "title": title,
        "recommended_book": {"title": title, "author": "A. Writer"},
        "recommendation_id": f"work:{title.casefold().replace(' ', '-')}",
        "score": score,
        "final_score": score,
        "reader_likelihood_score": reader_likelihood,
        "reason": reason,
        "matched_liked_books": [{"title": "Anchor Book"}] if "Anchor Book" in reason else [],
        "matched_genres": ["dystopian survival"] if genres is None else genres,
        "matched_subjects": [] if subjects is None else subjects,
        "score_breakdown": score_breakdown,
        "in_library": source == "library",
        "external_discovery": source != "library",
        "discovery_source": None if source == "library" else source,
    }


def test_final_admission_rejects_zero_score_and_extremely_low_reader_likelihood():
    zero = _recommendation_item("Zero Score", score=0.0, reader_likelihood=0.7)
    low_likelihood = _recommendation_item("Low Likelihood", score=0.7, reader_likelihood=0.09)

    assert _final_admission_decision(zero)["reason"] == "score_below_minimum"
    assert _final_admission_decision(low_likelihood)["reason"] == "reader_likelihood_below_minimum"


def test_final_admission_rejects_vague_related_theme_only_evidence():
    item = _recommendation_item(
        "Vague Pick",
        score=0.5,
        reader_likelihood=0.5,
        reason="This recommendation follows similar themes of related themes.",
        genres=[],
        subjects=[],
        breakdown={"weak_explanation_likelihood_penalty": 0.09},
    )
    item["matched_liked_books"] = []

    decision = _final_admission_decision(item)

    assert decision["admitted"] is False
    assert decision["reason"] == "vague_explanation_without_specific_evidence"


def test_final_admission_allows_exact_series_continuation_with_strong_label():
    item = _recommendation_item(
        "Exact Sequel",
        score=0.2,
        reader_likelihood=0.42,
        reason="Because you continued Example Series.",
        genres=[],
        subjects=[],
        breakdown={"series_continuity_boost": 0.12, "series_support": 0.9},
    )
    item["matched_liked_books"] = []

    assert _final_admission_decision(item)["admitted"] is True


def test_final_admission_applies_same_gate_to_library_and_external_candidates():
    library = _recommendation_item("Weak Library", score=0.0, reader_likelihood=0.08, source="library")
    external = _recommendation_item("Weak External", score=0.0, reader_likelihood=0.08, source="hardcover")

    assert _final_admission_decision(library)["reason"] == _final_admission_decision(external)["reason"]


def test_distinct_tastes_receive_distinct_cluster_sections():
    db = _session()
    user_id = _profile(db)
    _seed_multi_taste_profile(db, user_id)

    clusters = get_clustered_recommendations(db, user_id, include_discovery=False, max_per_cluster=3)
    ids = {cluster["cluster_id"] for cluster in clusters}

    assert "literary-classics" in ids
    assert "ya-mystery-thriller" in ids
    assert "contemporary-romance-new-adult" in ids

    assert {"Great Expectations", "A Tale of Two Cities"} & _titles(_cluster(clusters, "literary-classics"))
    assert {"Killer Instinct", "Truly Devious"} & _titles(_cluster(clusters, "ya-mystery-thriller"))
    assert {"Happy Place", "Funny Story"} & _titles(_cluster(clusters, "contemporary-romance-new-adult"))

    assert "Scythe" not in _titles(_cluster(clusters, "literary-classics"))
    assert "Killer Instinct" not in _titles(_cluster(clusters, "contemporary-romance-new-adult"))
    assert all(cluster["anchors"] for cluster in clusters)
    assert all(cluster["why"] for cluster in clusters)
    assert all(cluster["dominant_themes"] for cluster in clusters)
    assert all(cluster["cluster_size"] >= 1 for cluster in clusters)


def test_one_cluster_cannot_occupy_entire_top_ten():
    db = _session()
    user_id = _profile(db)
    _seed_multi_taste_profile(db, user_id)

    clusters = get_clustered_recommendations(db, user_id, include_discovery=False, max_per_cluster=5)
    flattened = flatten_clustered_recommendations(clusters, top_n=10, max_per_cluster=3)
    counts = Counter(item["taste_cluster_id"] for item in flattened)

    assert flattened
    assert max(counts.values()) <= 3
    assert len(counts) > 1


def test_single_dominant_taste_returns_single_sensible_cluster():
    db = _session()
    user_id = _profile(db)
    db.add_all(
        [
            _book(user_id, "Anna Karenina", author="Leo Tolstoy", status="read", rating=5, genres=["classics"], subjects=["russian literature"]),
            _book(user_id, "War and Peace", author="Leo Tolstoy", status="read", rating=5, genres=["classics"], subjects=["literary fiction"]),
            _book(user_id, "Great Expectations", author="Charles Dickens", genres=["classics"], subjects=["literary fiction"]),
            _book(user_id, "A Tale of Two Cities", author="Charles Dickens", genres=["classics"], subjects=["historical fiction"]),
        ]
    )
    db.commit()

    clusters = get_clustered_recommendations(db, user_id, include_discovery=False, max_per_cluster=3)

    assert [cluster["cluster_id"] for cluster in clusters] == ["literary-classics"]
    assert {"Great Expectations", "A Tale of Two Cities"} & _titles(clusters[0])


def test_recent_repeated_interest_orders_ahead_of_old_isolated_cluster():
    db = _session()
    user_id = _profile(db)
    db.add_all(
        [
            _book(user_id, "Anna Karenina", author="Leo Tolstoy", status="read", rating=5, end_date="2020-01-01", genres=["classic"], subjects=["russian literature"]),
            _book(user_id, "The Hunger Games", author="Suzanne Collins", status="read", rating=5, end_date="2026-07-01", genres=["young adult", "dystopian"], subjects=["survival", "rebellion"]),
            _book(user_id, "The Maze Runner", author="James Dashner", status="read", rating=5, end_date="2026-06-01", genres=["young adult", "dystopian"], subjects=["survival"]),
            _book(user_id, "Fahrenheit 451", author="Ray Bradbury", status="read", rating=4, end_date="2026-05-01", genres=["dystopian", "science fiction"], subjects=["state control"]),
            _book(user_id, "Great Expectations", author="Charles Dickens", genres=["classic"], subjects=["literary fiction"]),
            _book(user_id, "Scythe", author="Neal Shusterman", genres=["young adult", "dystopian"], subjects=["survival"]),
        ]
    )
    db.commit()

    clusters = get_clustered_recommendations(db, user_id, include_discovery=False, max_per_cluster=3)

    assert clusters[0]["cluster_id"] == "ya-dystopian-speculative"
    literary = next((cluster for cluster in clusters if cluster["cluster_id"] == "literary-classics"), None)
    if literary is not None:
        assert clusters[0]["diagnostics"]["final_display_priority"] > literary["diagnostics"]["final_display_priority"]


def test_repeated_recent_classic_reading_keeps_literary_cluster_high():
    db = _session()
    user_id = _profile(db)
    db.add_all(
        [
            _book(user_id, "Anna Karenina", author="Leo Tolstoy", status="read", rating=5, end_date="2026-07-01", genres=["classic"], subjects=["russian literature"]),
            _book(user_id, "War and Peace", author="Leo Tolstoy", status="read", rating=5, end_date="2026-06-15", genres=["classic"], subjects=["literary fiction"]),
            _book(user_id, "Pride and Prejudice", author="Jane Austen", status="read", rating=4.5, end_date="2026-06-01", genres=["classic"], subjects=["social life and customs"]),
            _book(user_id, "The Hunger Games", author="Suzanne Collins", status="read", rating=4, end_date="2021-01-01", genres=["young adult", "dystopian"], subjects=["survival"]),
            _book(user_id, "Great Expectations", author="Charles Dickens", genres=["classic"], subjects=["literary fiction"]),
            _book(user_id, "Scythe", author="Neal Shusterman", genres=["young adult", "dystopian"], subjects=["survival"]),
        ]
    )
    db.commit()

    clusters = get_clustered_recommendations(db, user_id, include_discovery=False, max_per_cluster=3)

    assert clusters[0]["cluster_id"] == "literary-classics"
    assert clusters[0]["diagnostics"]["cluster_reader_intent_score"] > 0.75


def test_clustered_recommendations_honor_dismissed_library_identity_and_refill():
    db = _session()
    user_id = _profile(db)
    _seed_multi_taste_profile(db, user_id)
    create_feedback(
        db,
        user_id,
        RecommendationFeedbackCreate(
            canonical_identity="work:/works/killer-instinct",
            recommendation_id="work:/works/killer-instinct",
            action="not_interested",
            source="library",
            cluster_id="ya-mystery-thriller",
            work_id="/works/killer-instinct",
            title="Killer Instinct",
            author="Jennifer Lynn Barnes",
        ),
    )

    clusters = get_clustered_recommendations(db, user_id, include_discovery=False, max_per_cluster=3)
    mystery = next((cluster for cluster in clusters if cluster["cluster_id"] == "ya-mystery-thriller"), None)
    if mystery is not None:
        assert "Killer Instinct" not in _titles(mystery)
        assert "Truly Devious" not in _titles(mystery)


def test_clustered_recommendations_honor_dismissed_external_identity_with_null_book_id(monkeypatch):
    db = _session()
    user_id = _profile(db)
    db.add(_book(user_id, "Book Lovers", author="Emily Henry", status="read", rating=5, genres=["romance"], subjects=["contemporary romance"]))
    db.commit()
    create_feedback(
        db,
        user_id,
        RecommendationFeedbackCreate(
            canonical_identity="work:/works/happy-place-external",
            recommendation_id="work:/works/happy-place-external",
            action="not_interested",
            source="external",
            cluster_id="contemporary-romance-new-adult",
            work_id="/works/happy-place-external",
            title="Happy Place",
            author="Emily Henry",
        ),
    )
    monkeypatch.setattr(
        "backend.services.recommendation_clusters.discovery_candidate_rows",
        lambda *_args, **_kwargs: (
            [
                {
                    "Title": "Happy Place",
                    "Authors": "Emily Henry",
                    "ISBN/UID": "external-happy-place",
                    "Read Status": "to-read",
                    "Star Rating": None,
                    "Progress (%)": 0,
                    "Pages Read": 0,
                    "Total Pages": 320,
                    "Subjects": ["contemporary romance"],
                    "Genres": ["romance"],
                    "In Library": False,
                    "Source Type": "external_discovery",
                    "Discovery Source": "open_library",
                    "Library Status": None,
                    "Book ID": None,
                    "External ID": "/works/happy-place-external",
                    "External Work ID": "/works/happy-place-external",
                    "External Edition ID": None,
                    "External ISBN": None,
                },
                {
                    "Title": "Funny Story",
                    "Authors": "Emily Henry",
                    "ISBN/UID": "external-funny-story",
                    "Read Status": "to-read",
                    "Star Rating": None,
                    "Progress (%)": 0,
                    "Pages Read": 0,
                    "Total Pages": 320,
                    "Subjects": ["romantic comedy"],
                    "Genres": ["romance"],
                    "In Library": False,
                    "Source Type": "external_discovery",
                    "Discovery Source": "open_library",
                    "Library Status": None,
                    "Book ID": None,
                    "External ID": "/works/funny-story-external",
                    "External Work ID": "/works/funny-story-external",
                    "External Edition ID": None,
                    "External ISBN": None,
                },
            ],
            object(),
        ),
    )

    clusters = get_clustered_recommendations(db, user_id, include_discovery=True, max_per_cluster=3)
    romance = _cluster(clusters, "contemporary-romance-new-adult")

    assert "Happy Place" not in _titles(romance)
    assert "Funny Story" in _titles(romance)


def test_underpopulated_fantasy_cluster_gets_bounded_discovery_query(monkeypatch):
    monkeypatch.setenv("DISCOVERY_MAX_QUERIES", "3")
    books = [
        _book(None, "A Court of Thorns and Roses", author="Sarah J. Maas", status="read", rating=5, genres=["fantasy"], subjects=["magic", "fae courts"]),
        _book(None, "Amari and the Night Brothers", author="B. B. Alston", status="read", rating=5, genres=["juvenile fantasy"], subjects=["magic"]),
        _book(None, "The Hunger Games", author="Suzanne Collins", status="read", rating=5, genres=["dystopian"], subjects=["survival", "rebellion"]),
        _book(None, "Book Lovers", author="Emily Henry", status="read", rating=5, genres=["romance"], subjects=["contemporary romance"]),
        _book(None, "Anna Karenina", author="Leo Tolstoy", status="read", rating=5, genres=["classic"], subjects=["russian literature"]),
    ]

    queries = _structured_discovery_queries(
        books,
        preferred_cluster_ids={"fantasy"},
        allocation_reasons={"fantasy": "underpopulated_display_cluster strong_local_candidates=0 target=3 anchor_count=2"},
    )

    assert len(queries) <= 3
    fantasy_queries = [query for query in queries if query.cluster_id == "fantasy"]
    assert fantasy_queries
    assert fantasy_queries[0].allocation_reason.startswith("underpopulated_display_cluster")


def _allocation_df(candidate_count=3):
    rows = [
        {
            "Title": "Book Lovers",
            "Authors": "Emily Henry",
            "ISBN/UID": "anchor-book-lovers",
            "Read Status": "read",
            "Star Rating": 5,
            "Genres": ["contemporary romance"],
            "Subjects": ["romantic comedy"],
            "In Library": True,
        }
    ]
    rows.extend(
        {
            "Title": f"Local Romance {index}",
            "Authors": f"Author {index}",
            "ISBN/UID": f"local-romance-{index}",
            "Read Status": "to-read",
            "Genres": ["contemporary romance"],
            "Subjects": ["relationships"],
            "In Library": True,
        }
        for index in range(candidate_count)
    )
    return pd.DataFrame(rows)


def test_three_weak_local_candidates_still_trigger_external_discovery(monkeypatch):
    monkeypatch.setattr(
        "backend.services.recommendation_clusters.build_recommendations",
        lambda *_args, **_kwargs: [
            {"title": "Weak 1", "in_library": True, "score": 0.12, "score_breakdown": {"reader_intent_score": 0.04, "candidate_similarity": 0.05}},
            {"title": "Weak 2", "in_library": True, "score": 0.10, "score_breakdown": {"reader_intent_score": 0.03, "candidate_similarity": 0.04}},
            {"title": "Weak 3", "in_library": True, "score": 0.08, "score_breakdown": {"reader_intent_score": 0.02, "candidate_similarity": 0.03}},
        ],
    )

    preferred, reasons, _supplemental, diagnostics = _local_cluster_discovery_needs(
        _allocation_df(candidate_count=3),
        max_per_cluster=3,
    )

    assert "contemporary-romance-new-adult" in preferred
    assert "quality_aware_supply" in reasons["contemporary-romance-new-adult"]
    romance = next(item for item in diagnostics if item["cluster_id"] == "contemporary-romance-new-adult")
    assert romance["raw_local_candidate_count"] == 3
    assert romance["qualified_local_candidate_count"] == 0
    assert romance["requested_external_candidate_count"] == 3


def test_two_strong_local_candidates_suppress_unnecessary_discovery(monkeypatch):
    monkeypatch.setattr(
        "backend.services.recommendation_clusters.build_recommendations",
        lambda *_args, **_kwargs: [
            {"title": "Strong 1", "in_library": True, "score": 0.62, "score_breakdown": {"reader_intent_score": 0.5, "candidate_similarity": 0.4}},
            {"title": "Strong 2", "in_library": True, "score": 0.51, "score_breakdown": {"reader_intent_score": 0.4, "candidate_similarity": 0.3}},
        ],
    )

    preferred, _reasons, _supplemental, diagnostics = _local_cluster_discovery_needs(
        _allocation_df(candidate_count=3),
        max_per_cluster=3,
    )

    assert "contemporary-romance-new-adult" not in preferred
    romance = next(item for item in diagnostics if item["cluster_id"] == "contemporary-romance-new-adult")
    assert romance["raw_local_candidate_count"] == 3
    assert romance["qualified_local_candidate_count"] == 2
    assert romance["requested_external_candidate_count"] == 0


def test_exact_series_continuation_counts_as_strong_but_weak_filler_still_allows_discovery(monkeypatch):
    monkeypatch.setattr(
        "backend.services.recommendation_clusters.build_recommendations",
        lambda *_args, **_kwargs: [
            {"title": "Exact Series", "in_library": True, "score": 0.30, "score_breakdown": {"series_continuity_boost": 0.12}},
            {"title": "Weak Filler", "in_library": True, "score": 0.09, "score_breakdown": {"reader_intent_score": 0.02, "candidate_similarity": 0.03}},
        ],
    )

    preferred, _reasons, _supplemental, diagnostics = _local_cluster_discovery_needs(
        _allocation_df(candidate_count=2),
        max_per_cluster=3,
    )

    assert "contemporary-romance-new-adult" in preferred
    romance = next(item for item in diagnostics if item["cluster_id"] == "contemporary-romance-new-adult")
    assert romance["qualified_local_candidate_count"] == 1
    assert romance["strong_continuity_candidate_count"] == 1
    assert romance["requested_external_candidate_count"] == 2


def test_title_text_alone_does_not_create_false_mystery_thriller_evidence():
    rows = pd.DataFrame(
        [
            {
                "Title": "The Naturals",
                "Authors": "Jennifer Lynn Barnes",
                "ISBN/UID": "anchor-naturals",
                "Read Status": "read",
                "Star Rating": 5,
                "Genres": ["mystery"],
                "Subjects": ["criminal profiling"],
                "In Library": True,
            },
            {
                "Title": "A Thriller-Sounding Memoir",
                "Authors": "Memoir Author",
                "ISBN/UID": "title-only-thriller",
                "Read Status": "to-read",
                "Genres": ["memoir"],
                "Subjects": ["life"],
                "In Library": True,
            },
        ]
    )
    grouped, rules = _cluster_anchor_groups(rows)
    anchors = grouped["ya-mystery-thriller"]

    cluster_df = _cluster_dataframe(rows, anchors, rules["ya-mystery-thriller"])

    assert "A Thriller-Sounding Memoir" not in set(cluster_df["Title"])


def test_cross_cluster_migration_requires_destination_metadata_evidence():
    rows = pd.DataFrame(
        [
            {
                "Title": "The Hunger Games",
                "Authors": "Suzanne Collins",
                "ISBN/UID": "hg",
                "Read Status": "read",
                "Star Rating": 5,
                "Genres": ["dystopian"],
                "Subjects": ["survival", "rebellion"],
                "In Library": True,
            },
            {
                "Title": "The Naturals",
                "Authors": "Jennifer Lynn Barnes",
                "ISBN/UID": "naturals",
                "Read Status": "read",
                "Star Rating": 5,
                "Genres": ["mystery"],
                "Subjects": ["criminal profiling"],
                "In Library": True,
            },
            {
                "Title": "Every Other Day",
                "Authors": "Jennifer Lynn Barnes",
                "ISBN/UID": "every-other-day",
                "Read Status": "to-read",
                "Genres": ["young adult", "dystopian"],
                "Subjects": ["survival", "supernatural"],
                "In Library": False,
                "Source Type": "external_discovery",
                "Discovery Source": "hardcover",
                "Discovery Query": "Jennifer Lynn Barnes young adult mystery thriller",
                "Discovery Cluster ID": "ya-mystery-thriller",
            },
            {
                "Title": "Retrieved Fantasy Only",
                "Authors": "External Author",
                "ISBN/UID": "query-only",
                "Read Status": "to-read",
                "Genres": ["literary fiction"],
                "Subjects": ["family life"],
                "In Library": False,
                "Source Type": "external_discovery",
                "Discovery Source": "hardcover",
                "Discovery Query": "Sarah J. Maas fantasy fantasy fiction",
                "Discovery Cluster ID": "fantasy",
            },
        ]
    )

    clusters = build_reading_clusters_from_dataframe(rows, style="external_first", max_per_cluster=3)
    titles_by_cluster = {cluster["cluster_id"]: _item_titles(cluster) for cluster in clusters}
    all_titles = [title for cluster in clusters for title in _item_titles(cluster)]
    dystopian = next(cluster for cluster in clusters if cluster["cluster_id"] == "ya-dystopian-speculative")
    migrated = next(item for item in dystopian["recommendations"] if item["display_title"] == "Every Other Day")

    assert "Every Other Day" in titles_by_cluster["ya-dystopian-speculative"]
    assert all_titles.count("Every Other Day") == 1
    assert "Retrieved Fantasy Only" not in all_titles
    assert "Dystopian" in migrated["explanation"]["shared_genres"]


def test_fantasy_cluster_rejects_contamination_and_allows_genuine_fantasy():
    rows = [
        {
            "Title": "A Court of Thorns and Roses",
            "Authors": "Sarah J. Maas",
            "ISBN/UID": "anchor-acotar",
            "Read Status": "read",
            "Star Rating": 5,
            "Genres": ["fantasy"],
            "Subjects": ["magic", "fae courts"],
            "In Library": True,
        },
        {
            "Title": "Amari and the Night Brothers",
            "Authors": "B. B. Alston",
            "ISBN/UID": "anchor-amari",
            "Read Status": "read",
            "Star Rating": 5,
            "Genres": ["juvenile fantasy"],
            "Subjects": ["magic"],
            "In Library": True,
        },
        {
            "Title": "Just Mercy Adjacent",
            "Authors": "Legal Memoir Author",
            "ISBN/UID": "weak-legal",
            "Read Status": "to-read",
            "Genres": ["nonfiction", "memoir", "young adult", "fantasy fiction"],
            "Subjects": ["law", "criminal justice", "civil rights"],
            "In Library": True,
        },
        {
            "Title": "Political Dystopia Adjacent",
            "Authors": "Political Author",
            "ISBN/UID": "weak-dystopia",
            "Read Status": "to-read",
            "Genres": ["fantasy fiction"],
            "Subjects": ["dystopian", "political fiction", "totalitarian"],
            "In Library": True,
        },
        {
            "Title": "The Dragon Quest",
            "Authors": "Fantasy Author",
            "ISBN/UID": "strong-fantasy",
            "Read Status": "to-read",
            "Genres": ["fantasy"],
            "Subjects": ["magic", "dragons", "quests"],
            "In Library": True,
        },
    ]

    clusters = build_reading_clusters_from_dataframe(pd.DataFrame(rows), max_per_cluster=3)
    fantasy = _cluster(clusters, "fantasy")
    titles = _item_titles(fantasy)

    assert "The Dragon Quest" in titles
    assert "Just Mercy Adjacent" not in titles
    assert "Political Dystopia Adjacent" not in titles
    assert fantasy["diagnostics"]["candidate_count_before_evidence_gating"] == 3
    assert fantasy["diagnostics"]["candidate_count_after_evidence_gating"] == 1
    assert {item["title"] for item in fantasy["diagnostics"]["evidence_rejections"]} == {
        "Just Mercy Adjacent",
        "Political Dystopia Adjacent",
    }


def test_fantasy_backfill_does_not_fill_empty_slots_with_weak_library_books():
    rows = [
        {
            "Title": "A Court of Thorns and Roses",
            "Authors": "Sarah J. Maas",
            "ISBN/UID": "anchor-acotar",
            "Read Status": "read",
            "Star Rating": 5,
            "Genres": ["fantasy"],
            "Subjects": ["magic", "fae courts"],
            "In Library": True,
        },
        {
            "Title": "Weak Legal Backfill",
            "Authors": "Legal Memoir Author",
            "ISBN/UID": "weak-legal",
            "Read Status": "to-read",
            "Genres": ["nonfiction", "memoir", "young adult", "fantasy fiction"],
            "Subjects": ["law", "criminal justice", "civil rights"],
            "In Library": True,
        },
        {
            "Title": "Strong Library Fantasy",
            "Authors": "Fantasy Author",
            "ISBN/UID": "strong-fantasy",
            "Read Status": "to-read",
            "Genres": ["fantasy"],
            "Subjects": ["magic", "witches"],
            "In Library": True,
        },
    ]

    clusters = build_reading_clusters_from_dataframe(pd.DataFrame(rows), max_per_cluster=3)
    fantasy = next((cluster for cluster in clusters if cluster["cluster_id"] == "fantasy"), None)
    if fantasy is not None:
        titles = _item_titles(fantasy)
        assert "Weak Legal Backfill" not in titles
        assert fantasy["diagnostics"]["final_recommendation_count"] <= 1


def test_clustered_recommendations_reject_just_mercy_like_runtime_metadata(monkeypatch):
    db = _session()
    user_id = _profile(db)
    db.add_all(
        [
            _book(
                user_id,
                "A Court of Thorns and Roses",
                author="Sarah J. Maas",
                status="read",
                rating=5,
                genres=["fantasy"],
                subjects=["magic", "fae courts"],
            ),
            _book(
                user_id,
                "Amari and the Night Brothers",
                author="B. B. Alston",
                status="read",
                rating=5,
                genres=["juvenile fantasy"],
                subjects=["magic"],
            ),
            _book(
                user_id,
                "Just Mercy",
                author="Bryan Stevenson",
                genres=["nonfiction", "memoir", "young adult"],
                subjects=[
                    "autobiographies",
                    "biography",
                    "administration of criminal justice",
                    "supreme court of the united states",
                    "law",
                    "criminal law",
                    "social science",
                ],
                work_key="/works/OL17231441W",
            ),
            _book(
                user_id,
                "Amari and the Great Game",
                author="B. B. Alston",
                genres=["juvenile fantasy"],
                subjects=["magic", "supernatural", "quests"],
                work_key="/works/amari-great-game",
            ),
        ]
    )
    db.commit()
    monkeypatch.setattr(
        "backend.services.recommendation_clusters.discovery_candidate_rows",
        lambda *_args, **_kwargs: ([], type("Diagnostics", (), {"structured_queries": []})()),
    )

    clusters = get_clustered_recommendations(db, user_id, include_discovery=True, max_per_cluster=3)
    fantasy = _cluster(clusters, "fantasy")
    titles = _item_titles(fantasy)

    assert "Just Mercy" not in titles
    assert "Amari and the Great Game" in titles
    amari = next(item for item in fantasy["recommendations"] if item["canonical_title"] == "Amari and the Great Game")
    assert amari["diagnostics"]["score_breakdown"]["reader_intent_score"] > 0
    assert fantasy["diagnostics"]["final_recommendation_count"] == 1
    assert all(item["title"] != "Just Mercy" for item in fantasy["diagnostics"]["evidence_rejections"])


def test_fallback_topic_cluster_rejects_young_adult_audience_only_matches(monkeypatch):
    db = _session()
    user_id = _profile(db)
    db.add_all(
        [
            _book(
                user_id,
                "Heartstopper, Volume 1",
                author="Alice Oseman",
                status="read",
                rating=5,
                genres=["young adult"],
                subjects=[
                    "young adult fiction comics graphic novels lgbt",
                    "high schools",
                    "comic books strips",
                    "boys",
                    "gays",
                    "love in adolescence",
                    "friendship",
                    "children s fiction",
                ],
            ),
            _book(
                user_id,
                "Heartstopper, Volume 2",
                author="Alice Oseman",
                status="read",
                rating=5,
                genres=["young adult"],
                subjects=[
                    "high schools",
                    "comic books strips",
                    "boys",
                    "gays",
                    "gay teenagers",
                    "love in adolescence",
                    "friendship",
                    "children s fiction",
                ],
            ),
            _book(
                user_id,
                "Girl in Pieces",
                author="Kathleen Glasgow",
                status="read",
                rating=5,
                genres=["young adult", "contemporary"],
                subjects=["emotional problems", "survival", "cutting self mutilation", "sex crimes"],
            ),
            _book(
                user_id,
                "The Kite Runner",
                author="Khaled Hosseini",
                genres=["historical fiction", "young adult"],
                subjects=["boys", "teenage boys", "friendship", "fiction coming of age"],
            ),
            _book(
                user_id,
                "Great Expectations",
                author="Charles Dickens",
                genres=["classic literature"],
                subjects=["boys", "young men", "child and youth fiction", "coming of age"],
            ),
            _book(
                user_id,
                "Refugee",
                author="Alan Gratz",
                genres=["historical fiction", "young adult"],
                subjects=["survival", "children s fiction", "refugees", "emigration and immigration"],
            ),
            _book(
                user_id,
                "Heartstopper, Volume 3",
                author="Alice Oseman",
                genres=["young adult"],
                subjects=[
                    "young adult fiction comics graphic novels lgbt",
                    "love in adolescence",
                    "comic books strips",
                    "friendship",
                ],
            ),
        ]
    )
    db.commit()
    monkeypatch.setattr(
        "backend.services.recommendation_clusters.discovery_candidate_rows",
        lambda *_args, **_kwargs: ([], type("Diagnostics", (), {"structured_queries": []})()),
    )

    clusters = get_clustered_recommendations(db, user_id, include_discovery=True, max_per_cluster=3)
    all_titles = {title for cluster in clusters for title in _item_titles(cluster)}
    cluster_titles = {cluster["title"] for cluster in clusters}
    specific = next(cluster for cluster in clusters if "Heartstopper, Volume 3" in _item_titles(cluster))

    assert "Young adult" not in cluster_titles
    assert "The Kite Runner" not in all_titles
    assert "Great Expectations" not in all_titles
    assert "Refugee" not in all_titles
    assert specific["title"] == "Contemporary teen relationships"
    assert _item_titles(specific) == {"Heartstopper, Volume 3"}
    assert specific["diagnostics"]["final_recommendation_count"] == 1


def test_fallback_topic_ignores_nyt_list_and_date_metadata(monkeypatch):
    db = _session()
    user_id = _profile(db)
    db.add_all(
        [
            _book(
                user_id,
                "Restart",
                author="Gordon Korman",
                status="read",
                rating=5,
                genres=["children s fiction"],
                subjects=[
                    "amnesia fiction",
                    "schools fiction",
                    "nyt middle grade paperback monthly 2019 10 13",
                    "new york times bestseller",
                ],
            ),
            _book(
                user_id,
                "Ghost Boys",
                author="Jewell Parker Rhodes",
                status="read",
                rating=5,
                genres=["children s fiction"],
                subjects=[
                    "death fiction",
                    "nyt middle grade paperback monthly 2019 10 13",
                    "nyt childrens middle grade hardcover 2018 05 06",
                    "new york times bestseller",
                ],
            ),
            _book(
                user_id,
                "Noisy List Candidate",
                subjects=["nyt middle grade paperback monthly 2019 10 13", "new york times bestseller"],
            ),
        ]
    )
    db.commit()
    monkeypatch.setattr(
        "backend.services.recommendation_clusters.discovery_candidate_rows",
        lambda *_args, **_kwargs: ([], type("Diagnostics", (), {"structured_queries": []})()),
    )

    clusters = get_clustered_recommendations(db, user_id, include_discovery=True, max_per_cluster=3)

    assert all("nyt" not in cluster["cluster_id"] for cluster in clusters)
    assert all("new-york-times" not in cluster["cluster_id"] for cluster in clusters)
    assert "Noisy List Candidate" not in {title for cluster in clusters for title in _item_titles(cluster)}


def test_fallback_topic_rejects_broad_nonfiction_alone(monkeypatch):
    db = _session()
    user_id = _profile(db)
    db.add_all(
        [
            _book(user_id, "Memoir One", status="read", rating=5, genres=["nonfiction"], subjects=["memoir"]),
            _book(user_id, "Memoir Two", status="read", rating=5, genres=["nonfiction"], subjects=["biography"]),
            _book(user_id, "Broad Nonfiction Candidate", genres=["nonfiction"], subjects=["memoir"]),
        ]
    )
    db.commit()
    monkeypatch.setattr(
        "backend.services.recommendation_clusters.discovery_candidate_rows",
        lambda *_args, **_kwargs: ([], type("Diagnostics", (), {"structured_queries": []})()),
    )

    clusters = get_clustered_recommendations(db, user_id, include_discovery=True, max_per_cluster=3)

    assert all(cluster["cluster_id"] != "topic-nonfiction" for cluster in clusters)
    assert "Broad Nonfiction Candidate" not in {title for cluster in clusters for title in _item_titles(cluster)}


def test_specific_nonfiction_fallback_identity_can_survive(monkeypatch):
    db = _session()
    user_id = _profile(db)
    db.add_all(
        [
            _book(
                user_id,
                "Justice Memoir One",
                status="read",
                rating=5,
                genres=["nonfiction"],
                subjects=["criminal justice memoir", "legal reform"],
            ),
            _book(
                user_id,
                "Justice Memoir Two",
                status="read",
                rating=5,
                genres=["nonfiction"],
                subjects=["criminal justice memoir", "wrongful convictions"],
            ),
            _book(
                user_id,
                "Justice Memoir Candidate",
                genres=["nonfiction"],
                subjects=["criminal justice memoir", "legal reform"],
            ),
        ]
    )
    db.commit()
    monkeypatch.setattr(
        "backend.services.recommendation_clusters.discovery_candidate_rows",
        lambda *_args, **_kwargs: ([], type("Diagnostics", (), {"structured_queries": []})()),
    )

    clusters = get_clustered_recommendations(db, user_id, include_discovery=True, max_per_cluster=3)
    specific = next(cluster for cluster in clusters if cluster["cluster_id"] == "topic-criminal-justice-memoirs")

    assert specific["title"] == "Criminal justice memoirs"
    assert _item_titles(specific) == {"Justice Memoir Candidate"}


def test_single_specific_nonfiction_anchor_with_strong_candidate_can_survive(monkeypatch):
    db = _session()
    user_id = _profile(db)
    db.add_all(
        [
            _book(
                user_id,
                "Martha Graham: A Dancer's Life",
                status="read",
                rating=5,
                genres=["nonfiction", "biography"],
                subjects=["modern dance", "choreographers", "dancers biography"],
            ),
            _book(
                user_id,
                "Modern Dance Lives",
                genres=["nonfiction", "biography"],
                subjects=["modern dance", "choreographers", "dancers biography"],
            ),
        ]
    )
    db.commit()
    monkeypatch.setattr(
        "backend.services.recommendation_clusters.discovery_candidate_rows",
        lambda *_args, **_kwargs: ([], type("Diagnostics", (), {"structured_queries": []})()),
    )

    clusters = get_clustered_recommendations(db, user_id, include_discovery=True, max_per_cluster=3)
    specific = next(cluster for cluster in clusters if cluster["cluster_id"] == "topic-modern-dance-biographies")

    assert specific["title"] == "Modern dance biographies"
    assert _item_titles(specific) == {"Modern Dance Lives"}


def test_unrelated_nonfiction_anchors_do_not_group_as_nonfiction(monkeypatch):
    db = _session()
    user_id = _profile(db)
    db.add_all(
        [
            _book(
                user_id,
                "Martha Graham: A Dancer's Life",
                status="read",
                rating=5,
                genres=["nonfiction", "biography"],
                subjects=["modern dance", "choreographers", "dancers biography"],
            ),
            _book(
                user_id,
                "Night",
                status="read",
                rating=5,
                genres=["memoir", "historical", "nonfiction"],
                subjects=[],
            ),
            _book(
                user_id,
                "Broad Nonfiction Candidate",
                genres=["nonfiction"],
                subjects=["memoir", "history"],
            ),
            _book(
                user_id,
                "Modern Dance Lives",
                genres=["nonfiction", "biography"],
                subjects=["modern dance", "choreographers"],
            ),
        ]
    )
    db.commit()
    monkeypatch.setattr(
        "backend.services.recommendation_clusters.discovery_candidate_rows",
        lambda *_args, **_kwargs: ([], type("Diagnostics", (), {"structured_queries": []})()),
    )

    clusters = get_clustered_recommendations(db, user_id, include_discovery=True, max_per_cluster=3)
    titles_by_id = {cluster["cluster_id"]: _item_titles(cluster) for cluster in clusters}

    assert "topic-nonfiction" not in titles_by_id
    assert "Broad Nonfiction Candidate" not in {title for titles in titles_by_id.values() for title in titles}
    assert titles_by_id["topic-modern-dance-biographies"] == {"Modern Dance Lives"}


def test_synthesized_ya_fallback_receives_discovery_and_serializes_aligned_candidate(monkeypatch):
    monkeypatch.setenv("DISCOVERY_MAX_QUERIES", "3")
    db = _session()
    user_id = _profile(db)
    db.add_all(
        [
            _book(
                user_id,
                "Heartstopper, Volume 1",
                author="Alice Oseman",
                status="read",
                rating=5,
                genres=["young adult"],
                subjects=[
                    "young adult fiction comics graphic novels lgbt",
                    "love in adolescence",
                    "high schools",
                    "boys",
                ],
            ),
            _book(
                user_id,
                "Heartstopper, Volume 2",
                author="Alice Oseman",
                status="read",
                rating=5,
                genres=["young adult"],
                subjects=[
                    "young adult fiction comics graphic novels lgbt",
                    "young adult fiction comics graphic novels romance",
                    "love in adolescence",
                ],
            ),
            _book(
                user_id,
                "The Kite Runner",
                genres=["historical fiction", "young adult"],
                subjects=["boys", "teenage boys", "friendship", "fiction coming of age"],
            ),
        ]
    )
    db.commit()
    calls = []

    def fake_aggregation(query, _local_candidates, **_kwargs):
        calls.append(query)
        if query == "queer teen graphic romance":
            return _aggregation(
                [
                    _external_result(
                        "Queer Hearts",
                        genres=["young adult graphic novel", "romance"],
                        subjects=["young adult fiction comics graphic novels lgbt", "love in adolescence"],
                    ),
                    _external_result(
                        "Generic Teen Story",
                        genres=["young adult"],
                        subjects=["boys", "schools", "friendship"],
                    ),
                ]
            )
        return _aggregation([])

    monkeypatch.setattr("backend.services.recommendation_discovery._run_aggregation", fake_aggregation)
    monkeypatch.setattr("backend.services.recommendation_discovery.explore_external_candidates", lambda *_args, **_kwargs: _empty_exploration())

    clusters = get_clustered_recommendations(db, user_id, include_discovery=True, max_per_cluster=3)
    specific = next(cluster for cluster in clusters if cluster["cluster_id"] == "topic-queer-teen-graphic-romance")
    all_titles = {title for cluster in clusters for title in _item_titles(cluster)}

    assert len(calls) <= 3
    assert "queer teen graphic romance" in specific["diagnostics"]["discovery_queries_allocated"]
    assert _item_titles(specific) == {"Queer Hearts"}
    assert "The Kite Runner" not in all_titles
    assert "Generic Teen Story" not in all_titles
    assert all(cluster["title"] != "Young adult" for cluster in clusters)


def test_synthesized_nonfiction_fallback_receives_discovery_and_serializes_aligned_candidate(monkeypatch):
    monkeypatch.setenv("DISCOVERY_MAX_QUERIES", "3")
    db = _session()
    user_id = _profile(db)
    db.add(
        _book(
            user_id,
            "Martha Graham: A Dancer's Life",
            status="read",
            rating=5,
            genres=["nonfiction", "biography"],
            subjects=["modern dance", "choreographers", "dancers biography"],
        )
    )
    db.commit()
    calls = []

    def fake_aggregation(query, _local_candidates, **_kwargs):
        calls.append(query)
        if query == "modern dance biography choreographers":
            return _aggregation(
                [
                    _external_result(
                        "Modern Dance Lives",
                        genres=["biography"],
                        subjects=["modern dance", "choreographers", "dancers biography"],
                    ),
                    _external_result(
                        "Generic Biography",
                        genres=["biography"],
                        subjects=["women", "history"],
                    ),
                ]
            )
        return _aggregation([])

    monkeypatch.setattr("backend.services.recommendation_discovery._run_aggregation", fake_aggregation)
    monkeypatch.setattr("backend.services.recommendation_discovery.explore_external_candidates", lambda *_args, **_kwargs: _empty_exploration())

    clusters = get_clustered_recommendations(db, user_id, include_discovery=True, max_per_cluster=3)
    specific = next(cluster for cluster in clusters if cluster["cluster_id"] == "topic-modern-dance-biographies")
    all_titles = {title for cluster in clusters for title in _item_titles(cluster)}

    assert len(calls) <= 3
    assert "modern dance biography choreographers" in specific["diagnostics"]["discovery_queries_allocated"]
    assert _item_titles(specific) == {"Modern Dance Lives"}
    assert "Generic Biography" not in all_titles
    assert all(cluster["title"] != "Nonfiction" for cluster in clusters)
