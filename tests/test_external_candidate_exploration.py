from uuid import uuid4

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from backend.db.database import Base
from backend.db.models import Book, Profile
from backend.services.external_candidate_exploration import (
    build_taste_dimensions,
    explore_external_candidates,
)
from backend.services.recommendation_clusters import flatten_clustered_recommendations, get_clustered_recommendations
from backend.services.recommendation_discovery import discovery_candidate_rows


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


def _book(user_id, title, author, *, status="read", rating=5, genres=None, subjects=None, work_key=None):
    completed = status in {"read", "completed"}
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
        genres=genres or [],
        subjects=subjects or [],
        work_key=work_key or f"/works/{title.casefold().replace(' ', '-')}",
    )


def _external(title, author, *, work_key, subjects=None, genres=None):
    return {
        "title": title,
        "authors": [author],
        "isbn_uid": None,
        "description": "A specific outside-library candidate.",
        "subjects": subjects or [],
        "genres": genres or [],
        "metadata_source": "open_library",
        "work_key": work_key,
        "confidence_score": 0.72,
    }


def test_taste_dimensions_are_abstract_not_anchor_queries():
    user_id = uuid4()
    dimensions = build_taste_dimensions(
        [
            _book(user_id, "The Naturals", "Jennifer Lynn Barnes", genres=["mystery"], subjects=["criminal profiling"]),
            _book(user_id, "Killer Instinct", "Jennifer Lynn Barnes", genres=["mystery"], subjects=["serial killers"]),
        ]
    )

    mystery = next(item for item in dimensions if item.cluster_id == "ya-mystery-thriller")

    assert "young adult mystery" in mystery.specific_genres
    assert "criminal profiling" in mystery.specific_themes
    assert "The Naturals" in mystery.anchor_titles


def test_open_library_subject_exploration_produces_non_anchor_candidates(monkeypatch):
    user_id = uuid4()
    calls = []

    def subject_results(subject, *, limit):
        calls.append(subject)
        return [_external(f"Subject Candidate {len(calls)}", "New Author", work_key=f"/works/subject-{len(calls)}", subjects=[subject])]

    monkeypatch.setattr("backend.services.external_candidate_exploration._open_library_subject_results", subject_results)

    candidates, diagnostics = explore_external_candidates(
        [_book(user_id, "The Naturals", "Jennifer Lynn Barnes", genres=["mystery"], subjects=["criminal profiling"])],
        limit=4,
        result_limit_per_source=2,
    )

    assert candidates
    assert diagnostics.subject_exploration_candidates >= 1
    assert any(candidate["exploration_mode"] == "subject" for candidate in candidates)
    assert all(candidate["discovery_query"] is None for candidate in candidates)
    assert "The Naturals" not in calls
    assert "Jennifer Lynn Barnes" not in calls


def test_discovery_collects_broad_external_candidates_before_library_dedupe(monkeypatch):
    db = _session()
    user_id = _profile(db)
    owned = _book(user_id, "Owned Mystery", "Anchor", genres=["mystery"], subjects=["criminal profiling"], work_key="/works/owned")
    db.add(owned)
    db.commit()

    monkeypatch.setattr(
        "backend.services.recommendation_discovery._run_aggregation",
        lambda *_args, **_kwargs: type("Aggregation", (), {"results": [], "outcomes": []})(),
    )
    monkeypatch.setattr(
        "backend.services.recommendation_discovery.explore_external_candidates",
        lambda *_args, **_kwargs: (
            [
                _external("Owned Mystery", "Anchor", work_key="/works/owned", subjects=["criminal profiling"], genres=["mystery"]),
                _external("New Profiling Mystery", "New Author", work_key="/works/new-profiling", subjects=["criminal profiling"], genres=["mystery"]),
            ],
            type(
                "Diagnostics",
                (),
                {
                    "exploration_requests": [{"mode": "subject", "source": "criminal_profilers", "cluster_id": "ya-mystery-thriller", "result_count": 2}],
                    "total_open_library_candidates_fetched": 2,
                    "broad_exploration_candidates": 2,
                },
            )(),
        ),
    )

    rows, diagnostics = discovery_candidate_rows(db, user_id, [owned], limit=10, allow_external=True)

    assert diagnostics.external_exploration_candidate_count == 2
    assert diagnostics.already_in_library_count == 1
    assert diagnostics.genuinely_new_work_count == 1
    assert [row["Title"] for row in rows] == ["New Profiling Mystery"]
    assert rows[0]["Exploration Mode"] is None or rows[0]["Discovery Cluster ID"] == "ya-mystery-thriller"


def test_external_first_clusters_can_return_more_external_than_library(monkeypatch):
    db = _session()
    user_id = _profile(db)
    db.add_all(
        [
            _book(user_id, "The Naturals", "Jennifer Lynn Barnes", status="read", rating=5, genres=["mystery"], subjects=["criminal profiling"]),
            _book(user_id, "Library Mystery", "Library Author", status="to-read", genres=["mystery"], subjects=["criminal profiling"]),
        ]
    )
    db.commit()
    monkeypatch.setattr(
        "backend.services.recommendation_clusters.discovery_candidate_rows",
        lambda *_args, **_kwargs: (
            [
                {
                    "Title": "External Mystery One",
                    "Authors": "New Author A",
                    "ISBN/UID": "external-one",
                    "Read Status": "to-read",
                    "Progress (%)": 0,
                    "Pages Read": 0,
                    "Subjects": ["criminal profiling"],
                    "Genres": ["mystery"],
                    "In Library": False,
                    "Source Type": "external_discovery",
                    "Discovery Source": "open_library",
                    "Discovery Cluster ID": "ya-mystery-thriller",
                    "Discovery Specific Themes": ["criminal profiling"],
                    "Discovery Query Confidence": 0.9,
                },
                {
                    "Title": "External Mystery Two",
                    "Authors": "New Author B",
                    "ISBN/UID": "external-two",
                    "Read Status": "to-read",
                    "Progress (%)": 0,
                    "Pages Read": 0,
                    "Subjects": ["criminal profiling", "serial killers"],
                    "Genres": ["mystery"],
                    "In Library": False,
                    "Source Type": "external_discovery",
                    "Discovery Source": "open_library",
                    "Discovery Cluster ID": "ya-mystery-thriller",
                    "Discovery Specific Themes": ["criminal profiling"],
                    "Discovery Query Confidence": 0.9,
                },
            ],
            None,
        ),
    )

    clusters = get_clustered_recommendations(db, user_id, top_n=3, style="external_first", max_per_cluster=3)
    flat = flatten_clustered_recommendations(clusters, top_n=3, max_per_cluster=3)

    assert sum(1 for item in flat if item.get("source") == "external") > sum(1 for item in flat if item.get("source") == "library")
