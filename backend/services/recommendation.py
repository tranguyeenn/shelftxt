# backend/services/recommendation.py

from functools import lru_cache
from uuid import UUID
import logging
import time

import pandas as pd
from sqlalchemy.orm import Session

from backend.env import is_local_env
from backend.repository.postgres_books_repository import get_books_for_recommendation
from backend.services.recommendation_debug import rec_debug
from backend.services.recommendation_builder import build_recommendations
from backend.services.status import normalize_status

VALID_STYLES = frozenset({"balanced", "popular", "discovery"})
MAX_RECOMMENDATION_BOOKS = 1000
logger = logging.getLogger(__name__)
DEBUG_ANNA_TITLE = "anna karenina"


def _normalize_style(style: str) -> str:
    normalized = (style or "balanced").strip().lower()
    return normalized if normalized in VALID_STYLES else "balanced"


def _normalize_tags(value) -> list[str]:
    if not value:
        return []

    if isinstance(value, list):
        return [str(item).strip().lower() for item in value if str(item).strip()]

    if isinstance(value, str):
        return [item.strip().lower() for item in value.split(",") if item.strip()]

    return []


def _apply_recommendation_filters(
    df: pd.DataFrame,
    *,
    genre: str | None = None,
    min_pages: int | None = None,
    max_pages: int | None = None,
) -> pd.DataFrame:
    if df.empty:
        return df

    status_col = "Read Status" if "Read Status" in df.columns else "read_status"
    if status_col not in df.columns:
        return df

    status = df[status_col].astype(str).str.strip().str.lower()
    candidate_mask = status.isin(["to-read", "not_started"])
    matching_candidates = candidate_mask.copy()

    if genre:
        wanted = genre.strip().lower()
        if wanted and "Genres" in df.columns:
            matching_candidates &= df["Genres"].apply(
                lambda value: wanted in _normalize_tags(value)
            )

    page_col = "Total Pages" if "Total Pages" in df.columns else "total_pages"

    if page_col in df.columns:
        pages = pd.to_numeric(df[page_col], errors="coerce")

        if min_pages is not None:
            matching_candidates &= pages.fillna(0) >= min_pages

        if max_pages is not None:
            matching_candidates &= pages.fillna(float("inf")) <= max_pages

    return df[~candidate_mask | matching_candidates]


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
                "Description": book.description,
                "Cover URL": book.cover_url,
                "Subjects": book.subjects or [],
                "Genres": book.genres or [],
                "First Publish Year": book.first_publish_year,
                "Language": book.language,
                "Work Key": book.work_key,
                "Edition Key": book.edition_key,
                "metadata": book.book_metadata or {},
            }
        )

    return pd.DataFrame(rows)


def _log_recommendation_debug(df: pd.DataFrame) -> None:
    rec_debug("total_books_loaded=%s", len(df))
    if df.empty:
        rec_debug("status_counts={} anna_in_loaded_books=False")
        return

    status_col = "Read Status" if "Read Status" in df.columns else "read_status"
    title_col = "Title" if "Title" in df.columns else "title"

    if status_col not in df.columns:
        rec_debug("status_counts={} anna_in_loaded_books=False")
        return

    raw_status_counts = df[status_col].astype(str).str.strip().str.lower().value_counts().to_dict()
    normalized_status_counts = df[status_col].apply(normalize_status).value_counts().to_dict()
    anna_in_loaded = title_col in df.columns and any(
        str(title).strip().lower() == DEBUG_ANNA_TITLE for title in df[title_col]
    )
    rec_debug(
        "status_counts_raw=%s status_counts_normalized=%s anna_in_loaded_books=%s",
        raw_status_counts,
        normalized_status_counts,
        anna_in_loaded,
    )


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
    refresh: bool = False,
    exclude_ids: set[str] | None = None,
    genre: str | None = None,
    min_pages: int | None = None,
    max_pages: int | None = None,
):
    total_started = time.perf_counter()
    rec_debug("user_id=%s", user_id)
    phase_started = time.perf_counter()
    books = get_books_for_recommendation(db, user_id, MAX_RECOMMENDATION_BOOKS)
    get_books_ms = (time.perf_counter() - phase_started) * 1000

    phase_started = time.perf_counter()
    df = books_to_dataframe(books)
    dataframe_ms = (time.perf_counter() - phase_started) * 1000
    _log_recommendation_debug(df)

    normalized_style = _normalize_style(style)

    if df.empty:
        total_ms = (time.perf_counter() - total_started) * 1000
        if is_local_env():
            logger.info(
                "endpoint_timing endpoint=GET /recommend user_id=%s duration_ms=%.2f "
                "rows=%s get_books_ms=%.2f dataframe_ms=%.2f builder_ms=0.00 "
                "external_calls=0 external_requests=0 metadata_enrichment=0 background_backfill=0",
                user_id,
                total_ms,
                len(books),
                get_books_ms,
                dataframe_ms,
            )
        return []

    phase_started = time.perf_counter()
    df = _apply_recommendation_filters(
        df,
        genre=genre,
        min_pages=min_pages,
        max_pages=max_pages,
    )
    recommendations = build_recommendations(
        df,
        top_n=top_n,
        style=normalized_style,
        refresh=refresh,
        exclude_ids=exclude_ids,
    )
    builder_ms = (time.perf_counter() - phase_started) * 1000

    phase_started = time.perf_counter()
    final = list(recommendations)
    serialization_ms = (time.perf_counter() - phase_started) * 1000
    total_ms = (time.perf_counter() - total_started) * 1000
    if is_local_env():
        logger.info(
            "endpoint_timing endpoint=GET /recommend user_id=%s duration_ms=%.2f "
            "rows=%s recommendations=%s get_books_ms=%.2f dataframe_ms=%.2f "
            "builder_ms=%.2f final_serialization_ms=%.2f external_calls=0 "
            "external_requests=0 metadata_enrichment=0 background_backfill=0",
            user_id,
            total_ms,
            len(books),
            len(final),
            get_books_ms,
            dataframe_ms,
            builder_ms,
            serialization_ms,
        )
    return final


def invalidate_recommendation_cache():
    _get_recommendation_cached.cache_clear()
