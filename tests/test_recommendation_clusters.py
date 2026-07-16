from collections import Counter
from uuid import uuid4

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from backend.db.database import Base
from backend.db.models import Book, Profile
from backend.services.recommendation_clusters import (
    flatten_clustered_recommendations,
    get_clustered_recommendations,
)
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
):
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


def test_distinct_tastes_receive_distinct_cluster_sections():
    db = _session()
    user_id = _profile(db)
    _seed_multi_taste_profile(db, user_id)

    clusters = get_clustered_recommendations(db, user_id, include_discovery=False, max_per_cluster=3)
    ids = {cluster["cluster_id"] for cluster in clusters}

    assert "literary-classics" in ids
    assert "ya-dystopian-speculative" in ids
    assert "ya-mystery-thriller" in ids
    assert "contemporary-romance-new-adult" in ids

    assert {"Great Expectations", "A Tale of Two Cities"} & _titles(_cluster(clusters, "literary-classics"))
    assert {"Scythe", "Brave New World"} & _titles(_cluster(clusters, "ya-dystopian-speculative"))
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
    mystery = _cluster(clusters, "ya-mystery-thriller")

    assert "Killer Instinct" not in _titles(mystery)
    assert "Truly Devious" in _titles(mystery)


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
