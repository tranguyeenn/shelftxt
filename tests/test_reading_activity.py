from datetime import UTC, date, datetime, timedelta
from uuid import uuid4

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from backend.db.database import Base
from backend.db.models import Book, Profile, ReadingActivity
from backend.services.reading_activity import get_reading_streak_stats


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


def _activity(user_id, occurred_at, *, pages=0, progress=0, activity_type="progress"):
    return ReadingActivity(
        user_id=user_id,
        occurred_at=occurred_at,
        activity_type=activity_type,
        pages_read_delta=pages,
        progress_delta=progress,
    )


def test_streak_no_activity():
    db = _session()
    user_id = _profile(db)

    stats = get_reading_streak_stats(db, user_id, today=date(2026, 7, 14))

    assert stats["current_streak_days"] == 0
    assert stats["longest_streak_days"] == 0
    assert stats["read_today"] is False
    assert stats["pages_read_today"] == 0


def test_streak_activity_today_and_multiple_events_same_day():
    db = _session()
    user_id = _profile(db)
    today = date(2026, 7, 14)
    db.add_all(
        [
            _activity(user_id, datetime(2026, 7, 13, 12, tzinfo=UTC), pages=12),
            _activity(user_id, datetime(2026, 7, 14, 10, tzinfo=UTC), pages=20),
            _activity(user_id, datetime(2026, 7, 14, 20, tzinfo=UTC), pages=8),
        ]
    )
    db.commit()

    stats = get_reading_streak_stats(db, user_id, today=today)

    assert stats["current_streak_days"] == 2
    assert stats["longest_streak_days"] == 2
    assert stats["read_today"] is True
    assert stats["pages_read_today"] == 28


def test_streak_remains_active_when_last_read_yesterday():
    db = _session()
    user_id = _profile(db)
    db.add(_activity(user_id, datetime(2026, 7, 13, 12, tzinfo=UTC), pages=12))
    db.commit()

    stats = get_reading_streak_stats(db, user_id, today=date(2026, 7, 14))

    assert stats["current_streak_days"] == 1
    assert stats["read_today"] is False


def test_broken_streak_and_longest_streak():
    db = _session()
    user_id = _profile(db)
    db.add_all(
        [
            _activity(user_id, datetime(2026, 7, 1, 12, tzinfo=UTC), pages=10),
            _activity(user_id, datetime(2026, 7, 2, 12, tzinfo=UTC), pages=10),
            _activity(user_id, datetime(2026, 7, 3, 12, tzinfo=UTC), pages=10),
            _activity(user_id, datetime(2026, 7, 10, 12, tzinfo=UTC), pages=10),
        ]
    )
    db.commit()

    stats = get_reading_streak_stats(db, user_id, today=date(2026, 7, 14))

    assert stats["current_streak_days"] == 0
    assert stats["longest_streak_days"] == 3


def test_metadata_only_activity_does_not_count():
    db = _session()
    user_id = _profile(db)
    db.add(_activity(user_id, datetime(2026, 7, 14, 12, tzinfo=UTC), activity_type="metadata"))
    db.commit()

    stats = get_reading_streak_stats(db, user_id, today=date(2026, 7, 14))

    assert stats["current_streak_days"] == 0
    assert stats["has_reading_activity"] is False


def test_timezone_date_boundary():
    db = _session()
    user_id = _profile(db)
    db.add(_activity(user_id, datetime(2026, 7, 14, 3, 30, tzinfo=UTC), pages=15))
    db.commit()

    stats = get_reading_streak_stats(
        db,
        user_id,
        timezone_name="America/New_York",
        today=date(2026, 7, 13),
    )

    assert stats["read_today"] is True
    assert stats["last_reading_date"] == "2026-07-13"


def test_completion_after_prior_progress_fallback_counts():
    db = _session()
    user_id = _profile(db)
    db.add(
        Book(
            user_id=user_id,
            title="Finished",
            authors="Author",
            isbn_uid="finished",
            read_status="read",
            pages_read=100,
            progress_percent=100,
            total_pages=100,
            start_date=date(2026, 7, 13),
            end_date=date(2026, 7, 14),
        )
    )
    db.commit()

    stats = get_reading_streak_stats(db, user_id, today=date(2026, 7, 14))

    assert stats["current_streak_days"] == 1
    assert stats["read_today"] is True
