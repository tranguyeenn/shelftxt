from __future__ import annotations

from collections import Counter, defaultdict
from datetime import date
from uuid import UUID

import time
from sqlalchemy import and_, func, or_
from sqlalchemy.orm import Session

from backend.db.models import Book
from backend.services.postgres_books import book_to_dict
from backend.services.reading_activity import get_reading_streak_stats
from backend.services.request_timing import add_timing, timed_stage
from backend.services.status import normalize_status

UNLOCK_THRESHOLD = 3


def _book_status(book: Book) -> str:
    return normalize_status(
        book.read_status,
        progress_percent=float(book.progress_percent or 0),
        pages_read=int(book.pages_read or 0),
    )


def _completion_date(book: Book) -> date | None:
    return book.end_date or book.last_date_read


def _completion_days(book: Book) -> int | None:
    end = _completion_date(book)
    if book.start_date is None or end is None or end < book.start_date:
        return None
    return max(1, (end - book.start_date).days + 1)


def _display_author(book: Book) -> str:
    return (book.authors or "Unknown author").split(",", 1)[0].strip() or "Unknown author"


def _profile_label(
    *,
    completed_count: int,
    average_pages: float | None,
    top_genre: tuple[str, int] | None,
    distinct_genres: int,
    books_per_month: float | None,
) -> str:
    if completed_count < UNLOCK_THRESHOLD:
        return "Building Reading Profile"
    if average_pages is not None and average_pages > 500:
        return "Big Book Reader"
    if top_genre is not None:
        genre, count = top_genre
        share = count / completed_count if completed_count else 0
        normalized = genre.casefold()
        if share >= 0.30 and "mystery" in normalized:
            return "Mystery Enthusiast"
        if share >= 0.30 and ("classic" in normalized or "literary" in normalized):
            return "Classic Explorer"
    if distinct_genres >= 5 and completed_count >= 5:
        return "Genre Hopper"
    if books_per_month is not None and books_per_month >= 2:
        return "Pace Reader"
    return "Steady Reader"


def _value_insight(type_: str, label: str, value: str, detail: str | None = None) -> dict:
    return {"type": type_, "label": label, "value": value, "detail": detail}


def get_reading_insights(db: Session, user_id: UUID) -> dict:
    started = time.perf_counter()
    with timed_stage("insights_query"):
        books = db.query(Book).filter(Book.user_id == user_id).all()
    completed = [book for book in books if _book_status(book) == "completed"]
    dnf = [book for book in books if _book_status(book) == "dnf"]
    completed_count = len(completed)

    page_books = [book for book in completed if book.total_pages and book.total_pages > 0]
    page_counts = [int(book.total_pages or 0) for book in page_books]
    average_pages = (sum(page_counts) / len(page_counts)) if page_counts else None

    genre_counts: Counter[str] = Counter()
    genre_ratings: dict[str, list[float]] = defaultdict(list)
    for book in completed:
        for genre in book.genres or []:
            clean = str(genre).strip()
            if not clean:
                continue
            genre_counts[clean] += 1
            if book.star_rating is not None:
                genre_ratings[clean].append(float(book.star_rating))
    top_genre = genre_counts.most_common(1)[0] if genre_counts else None

    author_counts = Counter(_display_author(book) for book in completed)
    top_author = author_counts.most_common(1)[0] if author_counts else None

    dated_completed = [book for book in completed if _completion_date(book) is not None]
    current_year = date.today().year
    completed_this_year = [
        book for book in dated_completed if _completion_date(book) and _completion_date(book).year == current_year
    ]
    books_per_month = len(completed_this_year) / max(1, date.today().month) if dated_completed else None

    completion_times = [days for book in completed if (days := _completion_days(book)) is not None]
    average_days_to_finish = (
        sum(completion_times) / len(completion_times) if completion_times else None
    )

    pages_with_days = [
        (int(book.total_pages or 0), days)
        for book in completed
        if book.total_pages and book.total_pages > 0 and (days := _completion_days(book)) is not None
    ]
    pages_per_day = (
        sum(pages for pages, _days in pages_with_days) / sum(days for _pages, days in pages_with_days)
        if pages_with_days
        else None
    )

    completion_rate = (
        completed_count / (completed_count + len(dnf)) if completed_count + len(dnf) > 0 else None
    )
    longest = max(page_books, key=lambda book: int(book.total_pages or 0), default=None)
    shortest = min(page_books, key=lambda book: int(book.total_pages or 0), default=None)
    highest_rated_genre = None
    if genre_ratings:
        highest_rated_genre = max(
            (
                (genre, sum(ratings) / len(ratings), len(ratings))
                for genre, ratings in genre_ratings.items()
            ),
            key=lambda item: (item[1], item[2], item[0]),
        )

    insights: list[dict] = []
    if pages_per_day is not None:
        insights.append(_value_insight("pages_per_day", "Reading Pace", f"{round(pages_per_day)} pages/day"))
    if average_days_to_finish is not None:
        insights.append(_value_insight("average_completion_time", "Average Finish Time", f"{round(average_days_to_finish)} days"))
    if top_genre is not None:
        insights.append(_value_insight("top_genre", "Most-Read Genre", top_genre[0], f"{top_genre[1]} completed"))
    if top_author is not None:
        insights.append(_value_insight("top_author", "Most-Read Author", top_author[0], f"{top_author[1]} completed"))
    if average_pages is not None:
        insights.append(_value_insight("average_pages", "Average Book Length", f"{round(average_pages)} pages"))
    if completion_rate is not None:
        insights.append(_value_insight("completion_rate", "Completion Rate", f"{round(completion_rate * 100)}%"))
    if longest is not None:
        insights.append(_value_insight("longest_book", "Longest Completed", longest.title, f"{longest.total_pages} pages"))
    if shortest is not None and shortest.id != longest.id:
        insights.append(_value_insight("shortest_book", "Shortest Completed", shortest.title, f"{shortest.total_pages} pages"))
    if highest_rated_genre is not None and len(insights) < 8:
        insights.append(
            _value_insight(
                "highest_rated_genre",
                "Highest-Rated Genre",
                highest_rated_genre[0],
                f"{highest_rated_genre[1]:.1f} / 5 average",
            )
        )
    if completed_this_year and len(insights) < 8:
        insights.append(_value_insight("completed_this_year", "Completed This Year", f"{len(completed_this_year)} books"))
    profile_label = _profile_label(
        completed_count=completed_count,
        average_pages=average_pages,
        top_genre=top_genre,
        distinct_genres=len(genre_counts),
        books_per_month=books_per_month,
    )

    status = "ready" if completed_count >= UNLOCK_THRESHOLD else "insufficient_activity"
    with timed_stage("streak_query"):
        streaks = get_reading_streak_stats(db, user_id)
    add_timing("insights_total", (time.perf_counter() - started) * 1000)
    return {
        "profile_label": profile_label,
        "insights": insights[:8] if status == "ready" else [],
        "completed_books": completed_count,
        "unlock_threshold": UNLOCK_THRESHOLD,
        "status": status,
        "message": (
            None
            if status == "ready"
            else "Finish a few books to unlock personalized reading insights."
        ),
        **streaks,
    }


def get_dashboard_summary(db: Session, user_id: UUID) -> dict:
    started = time.perf_counter()
    today = date.today()
    completion_date = func.coalesce(Book.end_date, Book.last_date_read)
    with timed_stage("dashboard_query"):
        current_books = (
            db.query(Book)
            .filter(
                Book.user_id == user_id,
                or_(
                    Book.read_status == "reading",
                    Book.read_status == "currently-reading",
                    and_(
                        Book.read_status == "to-read",
                        or_(
                            Book.progress_percent > 0,
                            Book.pages_read > 0,
                        ),
                    ),
                ),
            )
            .order_by(Book.start_date.desc().nullslast(), Book.progress_percent.desc().nullslast(), Book.title.asc())
            .limit(5)
            .all()
        )
        recent_completed = (
            db.query(Book)
            .filter(Book.user_id == user_id, Book.read_status.in_(["completed", "read"]))
            .order_by(Book.end_date.desc().nullslast(), Book.last_date_read.desc().nullslast(), Book.id.desc())
            .limit(4)
            .all()
        )
        completed_this_year = (
            db.query(func.count(Book.id))
            .filter(
                Book.user_id == user_id,
                Book.read_status.in_(["completed", "read"]),
                completion_date.is_not(None),
                completion_date <= today,
                func.extract("year", completion_date) == today.year,
            )
            .scalar()
            or 0
        )
        pages_this_year = (
            db.query(func.coalesce(func.sum(Book.total_pages), 0))
            .filter(
                Book.user_id == user_id,
                Book.read_status.in_(["completed", "read"]),
                completion_date.is_not(None),
                completion_date <= today,
                func.extract("year", completion_date) == today.year,
            )
            .scalar()
            or 0
        )
    with timed_stage("dashboard_serialize"):
        streaks = get_reading_streak_stats(db, user_id)
        payload = {
            "current_books": [book_to_dict(book, include_large_fields=False) for book in current_books],
            "recent_completed": [book_to_dict(book, include_large_fields=False) for book in recent_completed],
            "completed_this_year": int(completed_this_year),
            "pages_read_this_year": int(pages_this_year),
            **streaks,
        }
    add_timing("dashboard_total", (time.perf_counter() - started) * 1000)
    return payload
