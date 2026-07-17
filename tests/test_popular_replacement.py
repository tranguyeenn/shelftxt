from uuid import uuid4

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from backend.db.database import Base
from backend.db.models import Book, Profile
from backend.services.recommendation import (
    _popular_this_week_items,
    refresh_popular_this_week_section,
    replace_popular_this_week_item,
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
            title="Shelf Book",
            authors="Shelf Author",
            isbn_uid="shelf",
            read_status="to-read",
            genres=["fiction"],
            subjects=["fiction"],
            work_key="shelf",
        )
    )
    db.commit()
    return user_id


def _status():
    return type(
        "Status",
        (),
        {
            "to_dict": lambda self: {"enabled": True, "available": True, "cached": True, "request_count": 0},
            "request_count": 0,
            "cached": True,
        },
    )()


def _nyt(index, title, *, display="Hardcover Fiction", broad="Fiction", rank=1, weeks=4, year=2026, isbn=None):
    isbn_value = isbn or f"9781111111{index:03d}"[-13:]
    return {
        "external_id": f"nyt:{index}",
        "work_key": f"nyt:{index}",
        "title": title,
        "authors": [f"Author {index}"],
        "author": f"Author {index}",
        "description": f"A {display} book.",
        "isbn_uid": isbn_value,
        "primary_isbn13": isbn_value,
        "related_isbns": [isbn_value],
        "rank": rank,
        "rank_last_week": rank + 1,
        "weeks_on_list": weeks,
        "display_name": display,
        "list_name": display,
        "broad_genre": broad,
        "publication_year": year,
        "source_urls": [f"https://example.com/{index}"],
        "metadata_source": "nyt",
    }


def _candidates():
    return [
        _nyt(1, "Fresh Fiction", rank=2, weeks=2),
        _nyt(2, "Fresh YA", display="Young Adult Hardcover", broad="Young Adult", rank=1, weeks=3),
        _nyt(3, "Better Than the Movies", display="Young Adult Paperback", broad="Young Adult", rank=2, weeks=8),
        _nyt(4, "Fresh Romance", display="Paperback Trade Fiction Romance", broad="Romance", rank=1, weeks=5),
        _nyt(5, "Fresh Fantasy", display="Fantasy Science Fiction", broad="Fantasy / Science Fiction", rank=1, weeks=7),
        _nyt(6, "Fresh Mystery", display="Mystery Thriller", broad="Mystery / Thriller", rank=1, weeks=6),
        _nyt(7, "The Let Them Theory", display="Advice How-To and Miscellaneous", broad="Nonfiction", rank=1, weeks=9),
        _nyt(8, "Second Nonfiction", display="Hardcover Nonfiction", broad="Nonfiction", rank=2, weeks=2),
        _nyt(9, "Adult Manga", display="Graphic Books and Manga", broad="Graphic / Manga", rank=1, weeks=4),
        _nyt(10, "Second Manga", display="Graphic Books and Manga", broad="Graphic / Manga", rank=2, weeks=4),
        _nyt(11, "Wonder", display="Children's Middle Grade Hardcover", broad="Young Adult", rank=1, weeks=1),
        _nyt(12, "Investigators: Weather Or Not", display="Children's Graphic Books", broad="Graphic / Manga", rank=1, weeks=1),
        _nyt(13, "Stale Bestseller", display="Hardcover Fiction", broad="Fiction", rank=1, weeks=120),
        _nyt(14, "Ancient Bestseller", display="Hardcover Fiction", broad="Fiction", rank=1, weeks=520),
        _nyt(15, "Next Fiction", display="Hardcover Fiction", broad="Fiction", rank=3, weeks=5),
    ]


def test_popular_default_filters_audience_and_applies_category_caps(monkeypatch):
    monkeypatch.setattr("backend.services.recommendation.nyt_current_overview", lambda: (_candidates(), _status()))

    items, diagnostics = _popular_this_week_items(set())
    titles = [item["canonical_title"] for item in items]
    categories = [item["popular_category"] for item in items]

    assert "Fresh Fiction" in titles
    assert "Fresh YA" in titles or "Better Than the Movies" in titles
    assert "Wonder" not in titles
    assert "Investigators: Weather Or Not" not in titles
    assert categories.count("nonfiction") <= 1
    assert categories.count("young_adult") <= 2
    assert categories.count("manga_graphic") <= 1
    assert diagnostics["rejection_diagnostics"]["children_or_middle_grade"] >= 1
    assert diagnostics["rejection_diagnostics"]["juvenile_graphic"] >= 1


def test_popular_stale_books_are_fallback_only(monkeypatch):
    monkeypatch.setattr("backend.services.recommendation.nyt_current_overview", lambda: (_candidates(), _status()))

    items, diagnostics = _popular_this_week_items(set())
    titles = [item["canonical_title"] for item in items]

    assert "Stale Bestseller" not in titles
    assert "Ancient Bestseller" not in titles
    assert diagnostics["rejection_diagnostics"]["stale_bestseller"] >= 2


def test_popular_replace_excludes_visible_skipped_and_same_book(monkeypatch):
    db = _session()
    user_id = _profile(db)
    monkeypatch.setattr("backend.services.recommendation.nyt_current_overview", lambda: (_candidates(), _status()))

    response = replace_popular_this_week_item(
        db,
        user_id,
        current_recommendation_ids=["popular_this_week:nyt:1"],
        excluded_recommendation_ids=["popular_this_week:nyt:4"],
        replace_recommendation_id="popular_this_week:nyt:1",
        category="fiction",
    )

    assert response["replacement"] is not None
    assert response["replacement"]["canonical_title"] not in {"Fresh Fiction", "Fresh Romance"}
    assert response["replacement"]["popular_category"] == "fiction"


def test_popular_replacement_preserves_other_cards_in_client_order(monkeypatch):
    db = _session()
    user_id = _profile(db)
    monkeypatch.setattr("backend.services.recommendation.nyt_current_overview", lambda: (_candidates(), _status()))
    row = ["popular_this_week:nyt:1", "popular_this_week:nyt:2", "popular_this_week:nyt:5"]

    response = replace_popular_this_week_item(
        db,
        user_id,
        current_recommendation_ids=row,
        excluded_recommendation_ids=[],
        replace_recommendation_id=row[1],
        category="romance",
    )
    next_row = [row[0], response["replacement"]["recommendation_id"], row[2]]

    assert next_row[0] == row[0]
    assert next_row[2] == row[2]
    assert response["replacement"]["popular_category"] == "romance"


def test_popular_nonfiction_replacement_respects_row_limit(monkeypatch):
    db = _session()
    user_id = _profile(db)
    monkeypatch.setattr("backend.services.recommendation.nyt_current_overview", lambda: (_candidates(), _status()))

    response = replace_popular_this_week_item(
        db,
        user_id,
        current_recommendation_ids=["popular_this_week:nyt:7", "popular_this_week:nyt:1"],
        excluded_recommendation_ids=[],
        replace_recommendation_id="popular_this_week:nyt:1",
        category="nonfiction",
    )

    assert response["replacement"] is None
    assert response["reason"] == "no_matching_candidates"


def test_popular_ya_and_graphic_categories_exclude_juvenile(monkeypatch):
    db = _session()
    user_id = _profile(db)
    monkeypatch.setattr("backend.services.recommendation.nyt_current_overview", lambda: (_candidates(), _status()))

    ya = replace_popular_this_week_item(db, user_id, category="young_adult")
    graphic = replace_popular_this_week_item(db, user_id, category="manga_graphic")

    assert ya["replacement"]["canonical_title"] in {"Fresh YA", "Better Than the Movies"}
    assert graphic["replacement"]["canonical_title"] == "Adult Manga"


def test_popular_refresh_excludes_visible_ids_and_reuses_overview_path(monkeypatch):
    db = _session()
    user_id = _profile(db)
    calls = {"count": 0}

    def overview():
        calls["count"] += 1
        return _candidates(), _status()

    monkeypatch.setattr("backend.services.recommendation.nyt_current_overview", overview)

    response = refresh_popular_this_week_section(
        db,
        user_id,
        current_recommendation_ids=["popular_this_week:nyt:1"],
        excluded_recommendation_ids=[],
        preference="mixed",
    )

    assert "Fresh Fiction" not in [item["canonical_title"] for item in response["popular_this_week"]]
    assert calls["count"] == 1
