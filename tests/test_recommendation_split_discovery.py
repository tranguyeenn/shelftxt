from uuid import uuid4

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from backend.db.database import Base
from backend.db.models import Book, Profile
from backend.services.recommendation import get_recommendation, get_recommendation_sections, _newly_found_items


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


def _book(user_id, title, *, status="to-read", rating=None, author="Author", genres=None, subjects=None, work_key=None):
    completed = status in {"read", "completed"}
    return Book(
        user_id=user_id,
        title=title,
        authors=author,
        isbn_uid=work_key or title,
        read_status=status,
        star_rating=rating,
        total_pages=320,
        pages_read=320 if completed else 0,
        progress_percent=100 if completed else 0,
        genres=genres or ["fantasy"],
        subjects=subjects or ["magic"],
        work_key=work_key,
    )


def _hardcover(index, *, title, genre, year=2025, users=18000, activities=2400, ratings=1200):
    key = title.lower().replace(" ", "-")
    return {
        "title": title,
        "authors": [f"Author {index}"],
        "isbn_uid": f"9780000000{index:03d}"[-13:],
        "description": f"A {genre} novel with current reader activity.",
        "cover_url": f"https://img.example/{key}.jpg",
        "total_pages": 320,
        "subjects": [genre],
        "genres": [genre],
        "first_publish_year": year,
        "publication_year": year,
        "work_publication_year": year,
        "work_publication_date": f"{year}-01-01",
        "release_date": f"{year}-01-01",
        "edition_release_dates": [f"{year}-01-01"],
        "edition_release_years": [year],
        "publication_year_source": "work",
        "metadata_source": "hardcover",
        "work_key": f"hardcover:book:{index}",
        "edition_key": f"hardcover:edition:{index}",
        "related_isbns": [],
        "source_urls": [f"https://hardcover.app/books/{key}"],
        "provider_rating": 4.2,
        "provider_rating_count": ratings,
        "provider_user_count": users,
        "provider_activity_count": activities,
        "confidence_score": 0.9,
    }


def _nyt(index, *, title, genre, rank=1, weeks=4, last_week=2, isbn=None):
    key = title.lower().replace(" ", "-")
    return {
        "external_id": f"nyt:{index}",
        "work_key": f"nyt:{index}",
        "title": title,
        "authors": [f"NYT Author {index}"],
        "author": f"NYT Author {index}",
        "publisher": "NYT Publisher",
        "description": f"A bestseller in {genre}.",
        "isbn_uid": isbn or f"9781111111{index:03d}"[-13:],
        "primary_isbn13": isbn or f"9781111111{index:03d}"[-13:],
        "primary_isbn10": None,
        "related_isbns": [isbn or f"9781111111{index:03d}"[-13:]],
        "cover_url": f"https://img.example/{key}.jpg",
        "source_url": f"https://example.com/{key}",
        "source_urls": [f"https://example.com/{key}"],
        "metadata_source": "nyt",
        "source": "nyt",
        "rank": rank,
        "rank_last_week": last_week,
        "weeks_on_list": weeks,
        "list_name": genre,
        "display_name": genre,
        "list_name_encoded": genre.lower().replace(" ", "-"),
        "published_date": "2026-07-12",
        "bestsellers_date": "2026-07-04",
        "genres": [genre],
        "subjects": [genre],
        "broad_genre": genre,
    }


def test_personalized_recommendations_only_return_library_books_when_external_provider_has_results(monkeypatch):
    db = _session()
    user_id = _profile(db)
    db.add(_book(user_id, "Loved Fantasy", status="read", rating=5, genres=["fantasy"], subjects=["magic"], work_key="read-1"))
    db.add(_book(user_id, "Already Reading", status="reading", genres=["fantasy"], subjects=["magic"], work_key="reading-1"))
    db.add(_book(user_id, "Shelf Fantasy", genres=["fantasy"], subjects=["magic"], work_key="shelf-1"))
    db.commit()
    monkeypatch.setattr(
        "backend.services.recommendation.search_candidates",
        lambda _query: [_hardcover(1, title="External Fantasy", genre="fantasy")],
    )

    result = get_recommendation(db, user_id, top_n=10)

    assert result
    assert all(item["in_library"] for item in result)
    assert all(item["library_status"] != "reading" for item in result)
    assert {item["title"] for item in result} == {"Shelf Fantasy"}


def test_sections_split_shelf_popular_and_newly_found_with_distinct_popular_genres(monkeypatch):
    db = _session()
    user_id = _profile(db)
    db.add(_book(user_id, "Loved Fantasy", status="read", rating=5, genres=["fantasy"], subjects=["magic"], work_key="read-1"))
    db.add(_book(user_id, "Owned Popular", genres=["fantasy"], subjects=["magic"], work_key="nyt:1"))
    db.add(_book(user_id, "Shelf Fantasy", genres=["fantasy"], subjects=["magic"], work_key="shelf-1"))
    db.commit()
    nyt_candidates = [
        _nyt(1, title="Owned Popular", genre="Fiction", rank=1),
        _nyt(11, title="Popular Fiction", genre="Fiction", rank=2, weeks=10),
        _nyt(12, title="Popular Romance", genre="Romance", rank=1, weeks=3),
        _nyt(13, title="Popular Mystery", genre="Mystery / Thriller", rank=1, weeks=4),
        _nyt(14, title="Popular Fantasy", genre="Fantasy / Science Fiction", rank=1, weeks=5),
        _nyt(15, title="Popular Nonfiction", genre="Nonfiction", rank=1, weeks=6),
        _nyt(99, title="Fantasy Box Set", genre="Young Adult", rank=1),
    ]
    hardcover_candidates = {
        "new": [
            _hardcover(21, title="New One", genre="fantasy", year=2026),
            _hardcover(22, title="New Two", genre="romance", year=2025),
            _hardcover(11, title="Popular Fiction", genre="fantasy", year=2025),
        ],
    }

    def search(query):
        return hardcover_candidates["new"]

    monkeypatch.setattr("backend.services.recommendation.search_candidates", search)
    monkeypatch.setattr(
        "backend.services.recommendation.nyt_current_overview",
        lambda: (nyt_candidates, type("Status", (), {"to_dict": lambda self: {"enabled": True, "available": True, "cached": False, "request_count": 1}, "request_count": 1, "cached": False})()),
    )

    response = get_recommendation_sections(db, user_id, top_n=10)

    assert [section["title"] for section in response["sections"]] == [
        "From Your Shelf",
        "Popular This Week",
        "Newly found",
    ]
    assert all(item["library_state"]["in_library"] for item in response["shelf_recommendations"])
    assert all(item["provider"] == "nyt" for item in response["popular_this_week"])
    assert len(response["popular_this_week"]) == 5
    assert len({item["broad_genre"] for item in response["popular_this_week"]}) == 5
    assert "Owned Popular" not in {item["canonical_title"] for item in response["popular_this_week"]}
    assert "Fantasy Box Set" not in {item["canonical_title"] for item in response["popular_this_week"]}
    assert all(item["match_label"] not in {"Strong match", "Good match", "Possible match", "Exploratory match"} for item in response["popular_this_week"])
    assert all(item["nyt_rank"] for item in response["popular_this_week"])
    popular_ids = {item["canonical_identity"] for item in response["popular_this_week"]}
    assert all(item["canonical_identity"] not in popular_ids for item in response["newly_found"])
    assert all((item["publication_year"] or 0) >= 2023 for item in response["newly_found"])
    assert response["discovery_diagnostics"]["weekly_popularity_supported"] is True
    assert response["provider_status"]["nyt"]["available"] is True


def test_popular_this_week_removes_duplicates_and_fills_after_diverse_lists(monkeypatch):
    db = _session()
    user_id = _profile(db)
    db.add(_book(user_id, "Shelf Fantasy", genres=["fantasy"], subjects=["magic"], work_key="shelf-1"))
    db.commit()
    nyt_candidates = [
        _nyt(1, title="Same Book", genre="Fiction", rank=1, isbn="9781111111111"),
        _nyt(2, title="Same Book", genre="Romance", rank=1, isbn="9781111111111"),
        _nyt(3, title="Mystery Hit", genre="Mystery / Thriller", rank=1),
        _nyt(4, title="Fantasy Hit", genre="Fantasy / Science Fiction", rank=1),
        _nyt(5, title="Nonfiction Hit", genre="Nonfiction", rank=1),
        _nyt(6, title="Another Fiction", genre="Fiction", rank=2),
        _nyt(7, title="More Fiction", genre="Fiction", rank=3),
    ]

    monkeypatch.setattr("backend.services.recommendation.search_candidates", lambda _query: [])
    monkeypatch.setattr(
        "backend.services.recommendation.nyt_current_overview",
        lambda: (nyt_candidates, type("Status", (), {"to_dict": lambda self: {"enabled": True, "available": True, "cached": False, "request_count": 1}, "request_count": 1, "cached": False})()),
    )

    response = get_recommendation_sections(db, user_id, top_n=10)
    titles = [item["canonical_title"] for item in response["popular_this_week"]]

    assert len(titles) == 5
    assert titles.count("Same Book") == 1
    assert "Another Fiction" in titles
    assert response["discovery_diagnostics"]["nyt_final_count"] == 5


def test_popular_provider_failure_does_not_hide_shelf_or_newly_found(monkeypatch):
    db = _session()
    user_id = _profile(db)
    db.add(_book(user_id, "Shelf Fantasy", genres=["fantasy"], subjects=["magic"], work_key="shelf-1"))
    db.commit()

    monkeypatch.setenv("HARDCOVER_ENABLED", "true")
    monkeypatch.setenv("HARDCOVER_API_TOKEN", "test-token")
    monkeypatch.setattr(
        "backend.services.recommendation.search_candidates",
        lambda _query: [_hardcover(21, title="New One", genre="fantasy", year=2026)],
    )
    monkeypatch.setattr(
        "backend.services.recommendation.nyt_current_overview",
        lambda: ([], type("Status", (), {"to_dict": lambda self: {"enabled": True, "available": False, "cached": False, "request_count": 1, "error": "HTTPStatusError"}, "request_count": 1, "cached": False})()),
    )

    response = get_recommendation_sections(db, user_id, top_n=10)

    assert [item["canonical_title"] for item in response["shelf_recommendations"]] == ["Shelf Fantasy"]
    assert response["popular_this_week"] == []
    assert [item["canonical_title"] for item in response["newly_found"]] == ["New One"]
    assert response["provider_status"]["nyt"]["available"] is False


def test_newly_found_recency_accepts_only_recent_work_publications(monkeypatch):
    monkeypatch.setenv("HARDCOVER_ENABLED", "true")
    monkeypatch.setenv("HARDCOVER_API_TOKEN", "test-token")
    monkeypatch.setattr(
        "backend.services.recommendation.search_candidates",
        lambda _query: [
            _hardcover(31, title="Genuinely Recent", genre="fantasy", year=2026),
            _hardcover(32, title="Old Classic", genre="classic", year=1759),
            {
                **_hardcover(33, title="Old Work New Edition", genre="classic", year=1759),
                "edition_release_dates": ["2026-01-01"],
                "edition_release_years": [2026],
            },
            {
                **_hardcover(34, title="Unknown Date", genre="fantasy", year=2026),
                "first_publish_year": None,
                "publication_year": None,
                "work_publication_year": None,
                "work_publication_date": None,
                "release_date": None,
                "edition_release_dates": [],
                "edition_release_years": [],
            },
            {
                **_hardcover(35, title="Activity Date Only", genre="fantasy", year=2026),
                "first_publish_year": None,
                "publication_year": None,
                "work_publication_year": None,
                "work_publication_date": None,
                "release_date": None,
                "edition_release_dates": [],
                "edition_release_years": [],
                "provider_activity_date": "2026-07-01",
            },
            {
                **_hardcover(36, title="Candide", genre="classic", year=1759),
                "authors": ["Voltaire"],
                "edition_release_dates": ["2026-02-01"],
                "edition_release_years": [2026],
            },
        ],
    )

    items, diagnostics = _newly_found_items(set(), [])
    titles = [item["canonical_title"] for item in items]
    rejections = diagnostics["rejection_diagnostics"]

    assert titles == ["Genuinely Recent"]
    assert items[0]["publication_year"] == 2026
    assert items[0]["discovery_label"] == "Published in 2026"
    assert "Candide" not in titles
    assert rejections["work_too_old"] >= 1
    assert rejections["recent_edition_of_old_work"] >= 2
    assert rejections["missing_publication_date"] >= 2


def test_newly_found_may_return_zero_when_candidates_are_old_or_unknown(monkeypatch):
    monkeypatch.setenv("HARDCOVER_ENABLED", "true")
    monkeypatch.setenv("HARDCOVER_API_TOKEN", "test-token")
    monkeypatch.setattr(
        "backend.services.recommendation.search_candidates",
        lambda _query: [
            _hardcover(41, title="Old Classic", genre="classic", year=1818),
            {
                **_hardcover(42, title="Unknown Date", genre="fantasy", year=2026),
                "first_publish_year": None,
                "publication_year": None,
                "work_publication_year": None,
                "work_publication_date": None,
                "release_date": None,
                "edition_release_dates": [],
                "edition_release_years": [],
            },
        ],
    )

    items, diagnostics = _newly_found_items(set(), [])

    assert items == []
    assert diagnostics["provider_status"]["available"] is True
    assert diagnostics["rejection_diagnostics"]["missing_publication_date"] >= 1


def test_newly_found_reports_duplicate_and_collection_rejections(monkeypatch):
    monkeypatch.setenv("HARDCOVER_ENABLED", "true")
    monkeypatch.setenv("HARDCOVER_API_TOKEN", "test-token")
    duplicate = _hardcover(51, title="Already Owned", genre="fantasy", year=2026)
    collection = _hardcover(52, title="Recent Fantasy Collection", genre="fantasy", year=2026)
    library_keys = {
        "work:hardcover:book:51",
        "title_author:already-owned:author-51",
    }
    monkeypatch.setattr(
        "backend.services.recommendation.search_candidates",
        lambda _query: [duplicate, collection],
    )

    items, diagnostics = _newly_found_items(library_keys, [])

    assert items == []
    assert diagnostics["rejection_diagnostics"]["duplicate_in_library"] >= 1
    assert diagnostics["rejection_diagnostics"]["collection_or_bundle"] >= 1
