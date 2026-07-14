from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from typing import Iterable
from uuid import UUID
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from sqlalchemy.orm import Session

from backend.db.models import Book, ReadingActivity
from backend.services.status import normalize_status


@dataclass(frozen=True)
class ReadingActivityEvent:
    occurred_at: datetime
    pages_read_delta: int = 0
    progress_delta: float = 0.0
    activity_type: str = "progress"


def _timezone(value: str | None) -> ZoneInfo:
    if not value:
        return ZoneInfo("UTC")
    try:
        return ZoneInfo(value)
    except ZoneInfoNotFoundError:
        return ZoneInfo("UTC")


def _local_date(value: datetime, timezone_name: str | None) -> date:
    tz = _timezone(timezone_name)
    aware = value if value.tzinfo is not None else value.replace(tzinfo=UTC)
    return aware.astimezone(tz).date()


def _book_status(book: Book) -> str:
    return normalize_status(
        book.read_status,
        progress_percent=float(book.progress_percent or 0),
        pages_read=int(book.pages_read or 0),
    )


def record_progress_activity(
    db: Session,
    *,
    user_id: UUID,
    book: Book,
    previous_pages_read: int | None,
    previous_progress_percent: float | None,
    previous_status: str,
) -> None:
    current_pages = int(book.pages_read or 0)
    previous_pages = int(previous_pages_read or 0)
    current_progress = float(book.progress_percent or 0)
    previous_progress = float(previous_progress_percent or 0)
    pages_delta = max(0, current_pages - previous_pages)
    progress_delta = max(0.0, current_progress - previous_progress)
    current_status = _book_status(book)

    completed_after_progress = (
        current_status == "completed"
        and previous_status != "completed"
        and (previous_pages > 0 or previous_progress > 0)
    )
    if pages_delta <= 0 and progress_delta <= 0 and not completed_after_progress:
        return

    db.add(
        ReadingActivity(
            user_id=user_id,
            book_id=book.id,
            activity_type="completion" if completed_after_progress else "progress",
            pages_read_delta=pages_delta,
            progress_delta=progress_delta,
            activity_metadata={
                "title": book.title,
                "previous_status": previous_status,
                "current_status": current_status,
            },
        )
    )
    db.commit()


def _meaningful_events(
    db: Session,
    user_id: UUID,
    *,
    timezone_name: str | None = None,
) -> list[ReadingActivityEvent]:
    rows = (
        db.query(ReadingActivity)
        .filter(ReadingActivity.user_id == user_id)
        .order_by(ReadingActivity.occurred_at.asc())
        .all()
    )
    events = [
        ReadingActivityEvent(
            occurred_at=row.occurred_at,
            pages_read_delta=int(row.pages_read_delta or 0),
            progress_delta=float(row.progress_delta or 0),
            activity_type=row.activity_type,
        )
        for row in rows
        if int(row.pages_read_delta or 0) > 0
        or float(row.progress_delta or 0) > 0
        or row.activity_type == "session"
        or row.activity_type == "completion"
    ]

    if events:
        return events

    # Backfill-only fallback for libraries that predate activity logging.
    books = db.query(Book).filter(Book.user_id == user_id).all()
    fallback: list[ReadingActivityEvent] = []
    for book in books:
        status = _book_status(book)
        if status == "completed" and (book.end_date or book.last_date_read):
            completed_date = book.end_date or book.last_date_read
            if completed_date is not None and (book.pages_read or book.progress_percent or book.start_date):
                fallback.append(
                    ReadingActivityEvent(
                        occurred_at=datetime.combine(completed_date, datetime.min.time(), tzinfo=_timezone(timezone_name)),
                        pages_read_delta=int(book.total_pages or book.pages_read or 0),
                        progress_delta=100.0,
                        activity_type="completion",
                    )
                )
        elif int(book.pages_read or 0) > 0 or float(book.progress_percent or 0) > 0:
            activity_date = book.last_date_read or book.start_date
            if activity_date is not None:
                fallback.append(
                    ReadingActivityEvent(
                        occurred_at=datetime.combine(activity_date, datetime.min.time(), tzinfo=_timezone(timezone_name)),
                        pages_read_delta=int(book.pages_read or 0),
                        progress_delta=float(book.progress_percent or 0),
                        activity_type="progress",
                    )
                )
    return sorted(fallback, key=lambda event: event.occurred_at)


def _longest_streak(days: Iterable[date]) -> int:
    ordered = sorted(set(days))
    if not ordered:
        return 0
    longest = current = 1
    previous = ordered[0]
    for day in ordered[1:]:
        if day == previous + timedelta(days=1):
            current += 1
        else:
            current = 1
        longest = max(longest, current)
        previous = day
    return longest


def get_reading_streak_stats(
    db: Session,
    user_id: UUID,
    *,
    timezone_name: str | None = None,
    today: date | None = None,
) -> dict:
    events = _meaningful_events(db, user_id, timezone_name=timezone_name)
    tz = _timezone(timezone_name)
    local_today = today or datetime.now(tz).date()

    pages_by_day: dict[date, int] = defaultdict(int)
    active_days: set[date] = set()
    for event in events:
        day = _local_date(event.occurred_at, timezone_name)
        active_days.add(day)
        pages_by_day[day] += max(0, event.pages_read_delta)

    if not active_days:
        return {
            "current_streak_days": 0,
            "longest_streak_days": 0,
            "read_today": False,
            "last_reading_date": None,
            "pages_read_today": 0,
            "active_days_this_year": 0,
            "has_reading_activity": False,
        }

    read_today = local_today in active_days
    yesterday = local_today - timedelta(days=1)
    if read_today:
        cursor = local_today
    elif yesterday in active_days:
        cursor = yesterday
    else:
        cursor = None

    current_streak = 0
    while cursor is not None and cursor in active_days:
        current_streak += 1
        cursor -= timedelta(days=1)

    last_reading_date = max(active_days)
    return {
        "current_streak_days": current_streak,
        "longest_streak_days": _longest_streak(active_days),
        "read_today": read_today,
        "last_reading_date": last_reading_date.isoformat(),
        "pages_read_today": pages_by_day.get(local_today, 0),
        "active_days_this_year": sum(1 for day in active_days if day.year == local_today.year),
        "has_reading_activity": True,
    }
