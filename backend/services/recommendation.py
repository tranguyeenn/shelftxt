# backend/services/recommendation.py

from functools import lru_cache
from uuid import UUID
import logging
import time

import pandas as pd
from sqlalchemy.orm import Session

from backend.repository.postgres_books_repository import get_all_books
from backend.services.recommendation_builder import build_recommendations

VALID_STYLES = frozenset({"balanced", "popular", "discovery"})
logger = logging.getLogger(__name__)


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
                "Start Date": book.start_date,
                "End Date": book.end_date,
                "Progress (%)": book.progress_percent,
                "Pages Read": book.pages_read,
                "Total Pages": book.total_pages,
                "Subjects": book.subjects or [],
                "Genres": book.genres or [],
                "Language": book.language,
                "Work Key": book.work_key,
                "Edition Key": book.edition_key,
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


def get_recommendation(
    db: Session,
    user_id: UUID,
    top_n: int = 10,
    style: str = "balanced",
):
    total_started = time.perf_counter()
    phase_started = time.perf_counter()
    books = get_all_books(db, user_id)
    get_books_ms = (time.perf_counter() - phase_started) * 1000

    phase_started = time.perf_counter()
    df = books_to_dataframe(books)
    dataframe_ms = (time.perf_counter() - phase_started) * 1000

    normalized_style = _normalize_style(style)

    if df.empty:
        total_ms = (time.perf_counter() - total_started) * 1000
        logger.info(
            "recommendation_endpoint_timing get_books=%.2fms dataframe=%.2fms "
            "builder=0.00ms final_serialization=0.00ms total=%.2fms "
            "books=%s recommendations=0 external_requests=0 metadata_enrichment=0 background_backfill=0",
            get_books_ms,
            dataframe_ms,
            total_ms,
            len(books),
        )
        return []

    phase_started = time.perf_counter()
    recommendations = build_recommendations(df, top_n=top_n, style=normalized_style)
    builder_ms = (time.perf_counter() - phase_started) * 1000

    phase_started = time.perf_counter()
    final = list(recommendations)
    serialization_ms = (time.perf_counter() - phase_started) * 1000
    total_ms = (time.perf_counter() - total_started) * 1000
    logger.info(
        "recommendation_endpoint_timing get_books=%.2fms dataframe=%.2fms "
        "builder=%.2fms final_serialization=%.2fms total=%.2fms "
        "books=%s recommendations=%s external_requests=0 metadata_enrichment=0 background_backfill=0",
        get_books_ms,
        dataframe_ms,
        builder_ms,
        serialization_ms,
        total_ms,
        len(books),
        len(final),
    )
    return final


def invalidate_recommendation_cache():
    _get_recommendation_cached.cache_clear()
