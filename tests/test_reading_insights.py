from datetime import date
from uuid import uuid4

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from backend.db.database import Base
from backend.db.models import Book, Profile
from backend.services.reading_insights import get_reading_insights


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
    db.add(Profile(id=user_id, email="reader@example.com", username="reader"))
    db.commit()
    return user_id


def _book(user_id, title, pages, *, genres=None, author="Author", rating=4.0, start=None, end=None, status="read"):
    return Book(
        user_id=user_id,
        title=title,
        authors=author,
        isbn_uid=f"uid-{uuid4()}",
        read_status=status,
        star_rating=rating,
        total_pages=pages,
        pages_read=pages if status == "read" else 0,
        progress_percent=100 if status == "read" else 0,
        genres=genres or [],
        start_date=start,
        end_date=end,
    )


def _insight(response, type_):
    return next(item for item in response["insights"] if item["type"] == type_)


def test_reading_insights_average_pages_longest_shortest_and_completion_rate():
    db = _session()
    user_id = _profile(db)
    db.add_all(
        [
            _book(user_id, "Short", 100, genres=["Mystery"], start=date(2026, 1, 1), end=date(2026, 1, 2)),
            _book(user_id, "Middle", 300, genres=["Mystery"], start=date(2026, 2, 1), end=date(2026, 2, 6)),
            _book(user_id, "Long", 800, genres=["Classic"], start=date(2026, 3, 1), end=date(2026, 3, 10)),
            _book(user_id, "Dropped", 400, status="dnf"),
        ]
    )
    db.commit()

    response = get_reading_insights(db, user_id)

    assert response["status"] == "ready"
    assert _insight(response, "average_pages")["value"] == "400 pages"
    assert _insight(response, "longest_book")["value"] == "Long"
    assert _insight(response, "shortest_book")["value"] == "Short"
    assert _insight(response, "completion_rate")["value"] == "75%"


def test_reading_insights_top_genre_and_profile_classification():
    db = _session()
    user_id = _profile(db)
    db.add_all(
        [
            _book(user_id, "A", 220, genres=["Mystery"], author="Agatha Christie"),
            _book(user_id, "B", 260, genres=["Mystery"], author="Agatha Christie"),
            _book(user_id, "C", 280, genres=["Classic"], author="Other"),
        ]
    )
    db.commit()

    response = get_reading_insights(db, user_id)

    assert _insight(response, "top_genre")["value"] == "Mystery"
    assert _insight(response, "top_author")["value"] == "Agatha Christie"
    assert response["profile_label"] == "Mystery Enthusiast"


def test_reading_insights_big_book_reader_rule():
    db = _session()
    user_id = _profile(db)
    db.add_all(
        [
            _book(user_id, "A", 600, genres=["Fantasy"]),
            _book(user_id, "B", 700, genres=["Fantasy"]),
            _book(user_id, "C", 650, genres=["Fantasy"]),
        ]
    )
    db.commit()

    response = get_reading_insights(db, user_id)

    assert response["profile_label"] == "Big Book Reader"


def test_reading_insights_highest_rated_genre_when_available():
    db = _session()
    user_id = _profile(db)
    db.add_all(
        [
            _book(user_id, "A", 220, genres=["Mystery"], rating=3.0),
            _book(user_id, "B", 260, genres=["Classic"], rating=5.0),
            _book(user_id, "C", 280, genres=["Classic"], rating=4.0),
        ]
    )
    db.commit()

    response = get_reading_insights(db, user_id)

    assert _insight(response, "highest_rated_genre")["value"] == "Classic"


def test_reading_insights_empty_threshold_behavior():
    db = _session()
    user_id = _profile(db)
    db.add_all([_book(user_id, "A", 200), _book(user_id, "B", 220)])
    db.commit()

    response = get_reading_insights(db, user_id)

    assert response["status"] == "insufficient_activity"
    assert response["completed_books"] == 2
    assert response["unlock_threshold"] == 3
    assert response["insights"] == []
    assert "Finish a few books" in response["message"]
