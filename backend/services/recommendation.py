# backend/services/recommendation.py

from functools import lru_cache

import pandas as pd
from sqlalchemy.orm import Session

from backend.repository.postgres_books_repository import get_all_books
from backend.services.recommendation_builder import build_recommendations

VALID_STYLES = frozenset({"balanced", "popular", "discovery"})


def _normalize_style(style: str) -> str:
    normalized = (style or "balanced").strip().lower()
    return normalized if normalized in VALID_STYLES else "balanced"


def books_to_dataframe(books) -> pd.DataFrame:
    rows = []

    for book in books:
        rows.append(
            {
                "Title": book.title,
                "Authors": book.authors,
                "ISBN/UID": book.isbn_uid,
                "Read Status": book.read_status,
                "Star Rating": book.star_rating,
                "Last Date Read": book.last_date_read,
                "Progress (%)": book.progress_percent,
                "Pages Read": book.pages_read,
                "Total Pages": book.total_pages,
            }
        )

    return pd.DataFrame(rows)


@lru_cache(maxsize=32)
def _get_recommendation_cached(cache_key: tuple, top_n: int, style: str):
    _, books_snapshot = cache_key

    df = pd.DataFrame(list(books_snapshot))
    normalized_style = _normalize_style(style)

    if df.empty:
        return []

    return build_recommendations(df, top_n=top_n, style=normalized_style)


def get_recommendation(db: Session, top_n: int = 10, style: str = "balanced"):
    books = get_all_books(db)
    df = books_to_dataframe(books)

    normalized_style = _normalize_style(style)

    if df.empty:
        return []

    return build_recommendations(df, top_n=top_n, style=normalized_style)


def invalidate_recommendation_cache():
    _get_recommendation_cached.cache_clear()