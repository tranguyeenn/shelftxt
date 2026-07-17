# backend/services/recommendation.py

from collections import Counter, defaultdict
from datetime import datetime, timezone
from functools import lru_cache
from uuid import UUID
import asyncio
import logging
import math
import re
import time

import pandas as pd
from sqlalchemy.orm import Session

from app.integrations.hardcover import hardcover_enabled, search_candidates
from app.integrations.nyt_books import current_overview as nyt_current_overview
from backend.env import is_local_env, ollama_enabled
from backend.repository.postgres_books_repository import get_books_for_recommendation
from backend.services.candidate_integrity import evaluate_candidate_integrity
from backend.services.metadata_normalization import clean_reader_tags, normalize_genre, normalize_subject
from backend.services.recommendation_debug import rec_debug
from backend.services.recommendation_builder import build_recommendations, _feedback_identity_keys
from backend.services.recommendation_discovery import DiscoveryDiagnostics
from backend.services.ollama_embeddings import (
    OllamaEmbeddingClient,
    ensure_recommendation_embeddings,
    rerank_with_semantics,
)
from backend.services.recommendation_feedback import (
    active_feedback_for_user,
    active_not_interested_identities,
    feedback_to_ranking_records,
)
from backend.services.series_metadata import book_series_metadata
from backend.services.status import normalize_status

VALID_STYLES = frozenset({"balanced", "popular", "discovery", "external_first"})
MAX_RECOMMENDATION_BOOKS = 1000
logger = logging.getLogger(__name__)
DEBUG_ANNA_TITLE = "anna karenina"
SHELF_RECOMMENDATION_LIMIT = 5
POPULAR_NOW_LIMIT = 5
NEWLY_FOUND_LIMIT = 5
HARDCOVER_GENRE_BUCKETS = (
    ("fantasy", "Fantasy", ("fantasy", "magic", "epic fantasy", "romantasy")),
    ("romance", "Romance", ("romance", "love stories", "romantic comedy")),
    ("mystery_thriller", "Mystery / Thriller", ("mystery", "thriller", "suspense", "crime")),
    ("science_fiction_dystopian", "Science Fiction / Dystopian", ("science fiction", "sci-fi", "dystopian", "dystopia")),
    ("literary_contemporary", "Literary / Contemporary Fiction", ("literary fiction", "contemporary fiction", "family life")),
)
NEWLY_FOUND_QUERIES = (
    "new fiction releases",
    "new hardcover fiction 2026",
    "new hardcover fiction 2025",
)
NEWLY_FOUND_REJECTION_REASONS = (
    "missing_publication_date",
    "work_too_old",
    "recent_edition_of_old_work",
    "duplicate_in_library",
    "collection_or_bundle",
    "invalid_metadata",
)
POPULAR_REJECTION_REASONS = (
    "children_or_middle_grade",
    "juvenile_graphic",
    "stale_bestseller",
    "nonfiction_limit",
    "ya_limit",
    "graphic_limit",
    "duplicate",
    "missing_metadata",
)
POPULAR_CATEGORY_LIMITS = {
    "young_adult": 2,
    "nonfiction": 1,
    "manga_graphic": 1,
}
POPULAR_ALLOWED_CATEGORIES = {
    "fiction",
    "young_adult",
    "romance",
    "fantasy_scifi",
    "mystery_thriller",
    "manga_graphic",
    "nonfiction",
}
NEWLY_FOUND_ALLOWED_CATEGORIES = {
    "fiction",
    "young_adult",
    "romance",
    "fantasy_scifi",
    "mystery_thriller",
    "manga_graphic",
    "literary_fiction",
    "historical_fiction",
}
NEWLY_FOUND_QUERY_LIMIT = 25


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


def _safe_float(value: object, default: float = 0.0) -> float:
    try:
        parsed = float(value if value is not None else default)
    except (TypeError, ValueError):
        return default
    if pd.isna(parsed):
        return default
    return parsed


def _safe_int(value: object, default: int = 0) -> int:
    try:
        parsed = int(value if value is not None else default)
    except (TypeError, ValueError):
        return default
    return parsed


def _candidate_status(row) -> str:
    return normalize_status(
        row.get("Read Status"),
        progress_percent=_safe_float(row.get("Progress (%)")),
        pages_read=_safe_int(row.get("Pages Read")),
    )


def _is_eligible_candidate(row) -> bool:
    return (
        _candidate_status(row) == "not_started"
        and _safe_float(row.get("Progress (%)")) <= 0
        and _safe_int(row.get("Pages Read")) <= 0
    )


def _singular_variant(value: str) -> str:
    if value.endswith("ies") and len(value) > 3:
        return f"{value[:-3]}y"
    if value.endswith("s") and not value.endswith("ss") and len(value) > 3:
        return value[:-1]
    return value


def _normalized_genre_keys(value: object) -> set[str]:
    keys = {
        normalize_genre(value),
        normalize_subject(value),
    }
    keys = {key for key in keys if key}
    keys.update(_singular_variant(key) for key in list(keys))
    return {key for key in keys if key}


def _row_genre_keys(row) -> set[str]:
    keys: set[str] = set()
    for value in list(row.get("Genres") or []) + list(row.get("Subjects") or []):
        keys.update(_normalized_genre_keys(value))
    return keys


def _row_matches_genre(row, wanted_keys: set[str]) -> bool:
    return bool(wanted_keys and _row_genre_keys(row).intersection(wanted_keys))


def _source_type(row) -> str:
    return str(row.get("Source Type") or ("library" if bool(row.get("In Library", True)) else "external_discovery"))


PUBLIC_DISCOVERY_SOURCES = {"library", "series_metadata", "hardcover", "open_library", "librarything"}


def _public_discovery_source(source: str | None, *, in_library: bool) -> str:
    if in_library:
        return "library"
    normalized = str(source or "").strip().casefold()
    if normalized in PUBLIC_DISCOVERY_SOURCES:
        return normalized
    if normalized in {"seeded_fixture", "local_catalog", "metadata_aggregation", "manual_override"}:
        return "open_library"
    return "open_library"


def _genre_filter_diagnostics(
    df: pd.DataFrame,
    *,
    raw_genre: str,
    final_count: int,
    deduplicated_count: int,
) -> None:
    wanted_keys = _normalized_genre_keys(raw_genre)
    normalized = sorted(wanted_keys)[0] if wanted_keys else ""
    matching_rows = [row for _, row in df.iterrows() if _row_matches_genre(row, wanted_keys)]
    eligible_rows = [row for row in matching_rows if _is_eligible_candidate(row)]
    excluded_completed = sum(1 for row in matching_rows if _candidate_status(row) == "completed")
    excluded_reading = sum(1 for row in matching_rows if _candidate_status(row) == "reading")
    excluded_dnf = sum(1 for row in matching_rows if _candidate_status(row) == "dnf")
    logger.info(
        "recommendation_genre_filter_diagnostics raw_selected_genre=%r "
        "normalized_selected_genre=%r total_matching_candidates_before_filtering=%s "
        "library_matches=%s external_matches=%s excluded_completed_count=%s "
        "excluded_currently_reading_count=%s excluded_dnf_count=%s deduplicated_count=%s "
        "final_recommendation_count=%s",
        raw_genre,
        normalized,
        len(matching_rows),
        sum(1 for row in eligible_rows if _source_type(row) == "library"),
        sum(1 for row in eligible_rows if _source_type(row) == "external_discovery"),
        excluded_completed,
        excluded_reading,
        excluded_dnf,
        deduplicated_count,
        final_count,
    )


def _display_author(value: object) -> str:
    return (str(value or "").split(",", 1)[0].strip() or "Unknown author")


def _apply_recommendation_filters(
    df: pd.DataFrame,
    *,
    genre: str | None = None,
    author: str | None = None,
    min_pages: int | None = None,
    max_pages: int | None = None,
) -> pd.DataFrame:
    if df.empty:
        return df

    status_col = "Read Status" if "Read Status" in df.columns else "read_status"
    if status_col not in df.columns:
        return df

    candidate_mask = df.apply(_is_eligible_candidate, axis=1)
    matching_candidates = candidate_mask.copy()

    if genre:
        wanted_keys = _normalized_genre_keys(genre)
        if wanted_keys:
            matching_candidates &= df.apply(lambda row: _row_matches_genre(row, wanted_keys), axis=1)

    if author:
        wanted_author = author.strip().lower()
        if wanted_author and "Authors" in df.columns:
            matching_candidates &= df["Authors"].apply(
                lambda value: wanted_author in _display_author(value).lower()
            )

    page_col = "Total Pages" if "Total Pages" in df.columns else "total_pages"

    if page_col in df.columns:
        pages = pd.to_numeric(df[page_col], errors="coerce")

        if min_pages is not None:
            matching_candidates &= pages.fillna(0) >= min_pages

        if max_pages is not None:
            matching_candidates &= pages.fillna(float("inf")) <= max_pages

    return df[~candidate_mask | matching_candidates]


def books_to_dataframe(books, user_id: UUID | None = None) -> pd.DataFrame:
    rows = []

    for book in books:
        in_library = bool(user_id is not None and book.user_id == user_id)
        series = book_series_metadata(book)
        rows.append(
            {
                "Title": book.title,
                "Authors": book.authors,
                "ISBN/UID": book.isbn_uid,
                "Read Status": book.read_status if in_library else "to-read",
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
                "In Library": in_library,
                "Source Type": "library" if in_library else "external_discovery",
                "Discovery Source": "library" if in_library else (book.metadata_source or "local_catalog"),
                "Library Status": book.read_status if in_library else None,
                "Book ID": book.id if in_library else None,
                "External ID": None if in_library else (book.work_key or book.edition_key or book.isbn_uid),
                "External Work ID": book.work_key,
                "External Edition ID": book.edition_key,
                "External ISBN": book.isbn_uid,
                "Series Name": series.get("series_name") if series else None,
                "Series Position": series.get("series_position") if series else None,
                "Series Position Label": series.get("series_position_label") if series else None,
                "Series Type": series.get("series_type") if series else None,
                "Series Books": series.get("series_books") if series else [],
                "Series Source": series.get("series_source") if series else None,
                "Series Confidence": series.get("series_confidence") if series else None,
                "Series Publication Order": series.get("series_publication_order") if series else None,
                "Series Chronological Order": series.get("series_chronological_order") if series else None,
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
    author: str | None = None,
    min_pages: int | None = None,
    max_pages: int | None = None,
    excluded_identities: set[str] | None = None,
):
    total_started = time.perf_counter()
    rec_debug("user_id=%s", user_id)
    phase_started = time.perf_counter()
    books = get_books_for_recommendation(db, user_id, MAX_RECOMMENDATION_BOOKS)
    get_books_ms = (time.perf_counter() - phase_started) * 1000

    phase_started = time.perf_counter()
    base_df = books_to_dataframe(books, user_id)
    active_feedback = active_feedback_for_user(db, user_id)
    active_exclusions = active_not_interested_identities(db, user_id) | (excluded_identities or set())
    library_candidate_count = 0
    if not base_df.empty:
        status = base_df["Read Status"].apply(
            lambda value: normalize_status(value)
        )
        pages = pd.to_numeric(base_df.get("Pages Read", 0), errors="coerce").fillna(0)
        progress = pd.to_numeric(base_df.get("Progress (%)", 0), errors="coerce").fillna(0)
        library_candidate_count = int(((status == "not_started") & (pages <= 0) & (progress <= 0)).sum())

    discovery_diagnostics = DiscoveryDiagnostics(library_candidate_count=library_candidate_count)

    def _build_from_library() -> tuple[list[dict], pd.DataFrame, pd.DataFrame]:
        df = base_df.copy()
        df = df.astype(object).where(pd.notnull(df), None) if not df.empty else df
        if df.empty:
            return [], df, df
        unfiltered = df
        filtered = _apply_recommendation_filters(
            df,
            genre=genre,
            author=author,
            min_pages=min_pages,
            max_pages=max_pages,
        )
        return (
            build_recommendations(
                filtered,
                top_n=top_n,
                style=normalized_style,
                refresh=refresh,
                exclude_ids=exclude_ids,
                feedback_records=feedback_to_ranking_records(active_feedback),
                excluded_identities=active_exclusions,
            ),
            filtered,
            unfiltered,
        )

    dataframe_ms = (time.perf_counter() - phase_started) * 1000

    normalized_style = _normalize_style(style)
    phase_started = time.perf_counter()
    recommendations, df, unfiltered_df = _build_from_library()

    _log_recommendation_debug(df)

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

    builder_ms = (time.perf_counter() - phase_started) * 1000

    phase_started = time.perf_counter()
    final = [item for item in recommendations if item.get("in_library", True)][:SHELF_RECOMMENDATION_LIMIT]
    if ollama_enabled():
        try:
            embedding_client = OllamaEmbeddingClient()
            embedding_stats = None
            try:
                embedding_stats = asyncio.run(ensure_recommendation_embeddings(db, final, client=embedding_client))
            except RuntimeError:
                loop = asyncio.new_event_loop()
                try:
                    embedding_stats = loop.run_until_complete(ensure_recommendation_embeddings(db, final, client=embedding_client))
                finally:
                    loop.close()
            if embedding_stats is not None:
                logger.info(
                    "recommendation_external_embedding_diagnostics model=%s candidates_scanned=%s "
                    "candidates_embedded=%s cache_hits=%s failures=%s",
                    embedding_client.embedding_model,
                    embedding_stats.scanned,
                    embedding_stats.created + embedding_stats.updated,
                    embedding_stats.reused,
                    embedding_stats.failures,
                )
            final = rerank_with_semantics(
                db,
                final,
                library_books=[book for book in books if book.user_id == user_id],
                embedding_model=embedding_client.embedding_model,
                debug=is_local_env(),
            )
        except Exception as exc:
            logger.info("semantic_recommendation_rerank_unavailable error=%s", exc)
            for item in final:
                item["semantic_available"] = False
    final_library_count = sum(1 for item in final if item.get("in_library"))
    final_external_count = sum(1 for item in final if item.get("external_discovery"))
    feedback_removed_count = 0
    if active_exclusions and not df.empty:
        feedback_removed_count = sum(
            1 for _, row in df.iterrows() if _feedback_identity_keys(row) & active_exclusions
        )
    source_breakdown = dict(
        Counter(str(item.get("discovery_source") or ("library" if item.get("in_library") else "unknown")) for item in final)
    )
    external_final = [
        {
            "title": item.get("title"),
            "source": item.get("discovery_source"),
            "identity": item.get("recommendation_id"),
            "outside_library": item.get("outside_library"),
        }
        for item in final
        if item.get("outside_library")
    ]
    discovery_diagnostics.feedback_removed_count = feedback_removed_count
    discovery_diagnostics.final_eligible_candidate_count = len(final)
    discovery_diagnostics.final_source_breakdown = source_breakdown
    serialization_ms = (time.perf_counter() - phase_started) * 1000
    total_ms = (time.perf_counter() - total_started) * 1000
    if genre:
        _genre_filter_diagnostics(
            unfiltered_df,
            raw_genre=genre,
            final_count=len(final),
            deduplicated_count=discovery_diagnostics.deduplicated_external_count,
        )
    logger.info(
        "recommendation_candidate_diagnostics user_id=%s library_candidate_count=%s "
        "open_library_candidate_count=%s librarything_candidate_count=%s "
        "other_provider_candidate_count=%s external_candidate_count=%s external_provider_attempts=%s "
        "external_provider_successes=%s deduplicated_external_count=%s "
        "feedback_removed_count=%s final_eligible_candidate_count=%s "
        "final_library_count=%s final_external_count=%s final_source_breakdown=%s "
        "provider_failures=%s queries=%s",
        user_id,
        library_candidate_count,
        discovery_diagnostics.open_library_candidate_count,
        discovery_diagnostics.librarything_candidate_count,
        discovery_diagnostics.other_provider_candidate_count,
        discovery_diagnostics.external_candidate_count,
        discovery_diagnostics.external_provider_attempts,
        discovery_diagnostics.external_provider_successes,
        discovery_diagnostics.deduplicated_external_count,
        feedback_removed_count,
        len(final),
        final_library_count,
        final_external_count,
        source_breakdown,
        discovery_diagnostics.provider_failures,
        discovery_diagnostics.queries,
    )
    logger.info(
        "recommendation_provider_threshold_diagnostics user_id=%s provider_failures=%s "
        "external_candidates_returned=%s external_candidates_accepted=%s final_source_breakdown=%s",
        user_id,
        discovery_diagnostics.provider_failures,
        discovery_diagnostics.external_candidate_count,
        final_external_count,
        source_breakdown,
    )
    logger.info("recommendation_external_final_titles user_id=%s external=%s", user_id, external_final)
    if is_local_env():
        logger.info(
            "endpoint_timing endpoint=GET /recommend user_id=%s duration_ms=%.2f "
            "rows=%s recommendations=%s get_books_ms=%.2f dataframe_ms=%.2f "
            "builder_ms=%.2f final_serialization_ms=%.2f external_calls=%s "
            "external_requests=%s metadata_enrichment=0 background_backfill=0",
            user_id,
            total_ms,
            len(df),
            len(final),
            get_books_ms,
            dataframe_ms,
            builder_ms,
            serialization_ms,
            discovery_diagnostics.external_provider_attempts,
            discovery_diagnostics.external_provider_attempts,
        )
    return final


def recommendation_match_label(
    score: float | int | None,
    *,
    reader_likelihood_score: float | int | None = None,
    score_breakdown: dict | None = None,
) -> str:
    try:
        normalized = float(score or 0)
    except (TypeError, ValueError):
        normalized = 0.0
    breakdown = score_breakdown if isinstance(score_breakdown, dict) else {}
    likelihood_raw = reader_likelihood_score if reader_likelihood_score is not None else breakdown.get("reader_likelihood_score")
    try:
        likelihood = float(likelihood_raw if likelihood_raw is not None else normalized)
    except (TypeError, ValueError):
        likelihood = 0.0
    continuity = (
        float(breakdown.get("series_continuity_boost") or 0.0) > 0
        or float(breakdown.get("series_support") or 0.0) >= 0.8
        or float(breakdown.get("author_support") or 0.0) >= 0.85
    )
    weak_explanation = float(breakdown.get("weak_explanation_likelihood_penalty") or 0.0) > 0
    if continuity and likelihood >= 0.35:
        return "Strong match"
    if weak_explanation and normalized < 0.65:
        return "Exploratory match"
    if normalized >= 0.85:
        return "Strong match"
    if normalized >= 0.65 and likelihood >= 0.25:
        return "Good match"
    if normalized >= 0.4 and likelihood >= 0.25:
        return "Possible match"
    return "Exploratory match"


def recommendation_match_percentage(score: float | int | None) -> int:
    try:
        normalized = float(score or 0)
    except (TypeError, ValueError):
        normalized = 0.0
    return round(min(1.0, max(0.0, normalized)) * 100)


MAX_RECOMMENDATION_SECTIONS = 4
MIN_SECTION_BOOKS = 3


def _section_id(label: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", label.casefold()).strip("-") or "section"


def _display_tags(values: object, *, max_tags: int = 5) -> list[str]:
    if max_tags <= 0:
        return []
    grouped = _reading_level_labels(values)
    cleaned = clean_reader_tags(values, max_tags=max_tags)
    tags: list[str] = []
    seen: set[str] = set()
    for tag in [*grouped, *cleaned]:
        key = tag.casefold()
        if key in seen:
            continue
        seen.add(key)
        tags.append(tag)
        if len(tags) >= max_tags:
            break
    return tags


def _display_value_list(values: object) -> list[str]:
    if values is None:
        return []
    if isinstance(values, list | tuple | set):
        return [str(value) for value in values]
    return [str(values)]


def _reading_level_labels(values: object) -> list[str]:
    grades: set[int] = set()
    for value in _display_value_list(values):
        normalized = value.casefold()
        match = re.search(r"\b(?:reading\s+level\s+)?grade\s+(\d{1,2})\b", normalized)
        if match:
            grades.add(int(match.group(1)))
    if not grades:
        return []
    if any(grade >= 10 for grade in grades):
        return ["Advanced reads"]
    if any(grade >= 7 for grade in grades):
        return ["Teen reads"]
    return []


def _section_labels_for_item(item: dict) -> list[str]:
    labels = _display_tags([*(item.get("genres") or []), *(item.get("traits") or [])], max_tags=4)
    return labels


def _build_grouped_recommendation_sections(items: list[dict]) -> list[dict]:
    by_label: dict[str, list[dict]] = defaultdict(list)
    seen_by_label: dict[str, set[str]] = defaultdict(set)

    for item in items:
        work_id = str(item.get("work_id") or "").strip()
        if not work_id:
            continue
        for label in _section_labels_for_item(item):
            key = label.casefold()
            if work_id in seen_by_label[key]:
                continue
            seen_by_label[key].add(work_id)
            by_label[label].append(item)

    eligible = [
        (label, section_items)
        for label, section_items in by_label.items()
        if len({str(item.get("work_id") or "") for item in section_items}) >= MIN_SECTION_BOOKS
    ]
    eligible.sort(
        key=lambda entry: (
            -len(entry[1]),
            -max(float(item.get("score") or 0.0) for item in entry[1]),
            entry[0].casefold(),
        )
    )

    sections: list[dict] = []
    seen_section_ids: set[str] = set()
    for label, section_items in eligible:
        section_id = _section_id(label)
        if section_id in seen_section_ids:
            continue
        seen_section_ids.add(section_id)
        sections.append(
            {
                "id": f"topic-{section_id}",
                "type": "topic",
                "title": label,
                "source_book": None,
                "items": section_items[:10],
            }
        )
        if len(sections) >= MAX_RECOMMENDATION_SECTIONS - 1:
            break
    return sections


def _facet_label(value: object) -> str:
    keys = _normalized_genre_keys(value)
    if keys:
        return sorted(keys)[0]
    return str(value or "").strip()


def _normalized_identity_text(value: object) -> str:
    return re.sub(r"[^a-z0-9]+", " ", str(value or "").casefold()).strip()


def _book_identity_keys_from_values(
    *,
    title: object = None,
    author: object = None,
    work_id: object = None,
    isbn: object = None,
    related_isbns: object = None,
) -> set[str]:
    keys: set[str] = set()
    work = str(work_id or "").strip().casefold()
    if work:
        keys.add(f"work:{work}")
    cleaned_isbn = re.sub(r"[^0-9Xx]", "", str(isbn or "")).upper()
    if len(cleaned_isbn) in {10, 13}:
        keys.add(f"isbn:{cleaned_isbn}")
    if isinstance(related_isbns, (list, tuple, set)):
        for value in related_isbns:
            related = re.sub(r"[^0-9Xx]", "", str(value or "")).upper()
            if len(related) in {10, 13}:
                keys.add(f"isbn:{related}")
    title_key = _normalized_identity_text(title)
    author_key = _normalized_identity_text(str(author or "").split(",", 1)[0])
    if title_key and author_key:
        keys.add(f"title_author:{title_key}:{author_key}")
    return keys


def _library_identity_keys(books: list) -> set[str]:
    keys: set[str] = set()
    for book in books:
        metadata = book.book_metadata if isinstance(book.book_metadata, dict) else {}
        external = metadata.get("external") if isinstance(metadata.get("external"), dict) else {}
        librarything = metadata.get("librarything") if isinstance(metadata.get("librarything"), dict) else {}
        related_isbns = [
            *(external.get("related_isbns") or []),
            *(librarything.get("related_isbns") or []),
        ]
        keys.update(
            _book_identity_keys_from_values(
                title=book.title,
                author=book.authors,
                work_id=book.work_key,
                isbn=book.isbn_uid,
                related_isbns=related_isbns,
            )
        )
    return keys


def _candidate_identity_keys(candidate: dict) -> set[str]:
    authors = candidate.get("authors") if isinstance(candidate.get("authors"), list) else []
    return _book_identity_keys_from_values(
        title=candidate.get("title"),
        author=authors[0] if authors else candidate.get("author"),
        work_id=candidate.get("work_key"),
        isbn=candidate.get("isbn_uid"),
        related_isbns=candidate.get("related_isbns"),
    )


def _section_item_identity_keys(item: dict) -> set[str]:
    return _book_identity_keys_from_values(
        title=item.get("canonical_title") or item.get("title"),
        author=item.get("canonical_author") or item.get("author"),
        work_id=item.get("canonical_identity") or item.get("work_id") or item.get("external_id"),
        isbn=item.get("isbn_13") or item.get("isbn_10") or item.get("isbn"),
        related_isbns=[item.get("isbn_13"), item.get("isbn_10"), item.get("isbn")],
    )


def _recommendation_ids_for_item(item: dict) -> set[str]:
    return {
        str(value).strip()
        for value in (
            item.get("recommendation_id"),
            item.get("canonical_identity"),
            item.get("work_id"),
            item.get("external_id"),
            item.get("provider_source_id"),
        )
        if str(value or "").strip()
    }


def _candidate_recommendation_ids(candidate: dict, *, section: str) -> set[str]:
    if section == "popular_this_week":
        external_id = str(candidate.get("external_id") or candidate.get("work_key") or "").strip()
        if not external_id:
            authors = candidate.get("authors") if isinstance(candidate.get("authors"), list) else []
            author = authors[0] if authors else candidate.get("author")
            external_id = f"nyt:{_normalized_identity_text(candidate.get('title'))}:{_normalized_identity_text(author)}"
        return {external_id, f"popular_this_week:{external_id}"}
    work_id = str(candidate.get("work_key") or candidate.get("edition_key") or "").strip()
    if not work_id:
        authors = candidate.get("authors") if isinstance(candidate.get("authors"), list) else []
        author = authors[0] if authors else candidate.get("author")
        work_id = f"hardcover:{_normalized_identity_text(candidate.get('title'))}:{_normalized_identity_text(author)}"
    return {work_id, f"newly_found:{work_id}"}


def _ids_match_candidate(candidate: dict, ids: set[str], *, section: str) -> bool:
    return bool(_candidate_recommendation_ids(candidate, section=section) & ids)


def _candidate_year(candidate: dict) -> int | None:
    for key in ("first_publish_year", "publication_year", "release_year"):
        value = candidate.get(key)
        try:
            parsed = int(value)
        except (TypeError, ValueError):
            continue
        if 1000 <= parsed <= datetime.now(timezone.utc).year + 1:
            return parsed
    return None


def _year_from_date(value: object) -> int | None:
    match = re.match(r"^(\d{4})", str(value or "").strip())
    if not match:
        return None
    parsed = int(match.group(1))
    if 1000 <= parsed <= datetime.now(timezone.utc).year + 1:
        return parsed
    return None


def _year_values(value: object) -> list[int]:
    values = value if isinstance(value, (list, tuple, set)) else [value]
    years: list[int] = []
    for item in values:
        year = _year_from_date(item)
        if year is None:
            try:
                parsed = int(item)
            except (TypeError, ValueError):
                continue
            year = parsed if 1000 <= parsed <= datetime.now(timezone.utc).year + 1 else None
        if year is not None and year not in years:
            years.append(year)
    return years


def _candidate_work_publication_year(candidate: dict) -> int | None:
    year_source = str(candidate.get("publication_year_source") or "").strip().casefold()
    keys = [
        "work_publication_year",
        "original_publication_year",
    ]
    if year_source != "edition":
        keys.extend(["first_publish_year", "publication_year"])
    for key in keys:
        year = _year_from_date(candidate.get(key))
        if year is not None:
            return year
        try:
            parsed = int(candidate.get(key))
        except (TypeError, ValueError):
            continue
        if 1000 <= parsed <= datetime.now(timezone.utc).year + 1:
            return parsed
    date_keys = [
        "work_publication_date",
        "original_publication_date",
        "first_publication_date",
    ]
    if year_source != "edition":
        date_keys.append("release_date")
    for key in date_keys:
        year = _year_from_date(candidate.get(key))
        if year is not None:
            return year
    return None


def _candidate_edition_years(candidate: dict) -> list[int]:
    return [
        * _year_values(candidate.get("edition_release_years")),
        * _year_values(candidate.get("edition_release_dates")),
        * _year_values(candidate.get("release_year")),
    ]


def _is_collection_or_bundle(candidate: dict) -> bool:
    title = str(candidate.get("title") or "").casefold()
    subtitle = str(candidate.get("subtitle") or "").casefold()
    haystack = f"{title} {subtitle}"
    return bool(re.search(r"\b(collection|collected|omnibus|box(?:ed)? set|bundle|anthology)\b", haystack))


def _newly_found_rejection_reason(candidate: dict, library_keys: set[str]) -> str | None:
    title = str(candidate.get("title") or "").strip()
    authors = candidate.get("authors") if isinstance(candidate.get("authors"), list) else []
    if not title or not authors:
        return "invalid_metadata"
    if _candidate_identity_keys(candidate) & library_keys:
        return "duplicate_in_library"
    if _is_collection_or_bundle(candidate):
        return "collection_or_bundle"
    if not evaluate_candidate_integrity(candidate).recommendation_eligible:
        return "invalid_metadata"

    current_year = datetime.now(timezone.utc).year
    minimum_year = current_year - 2
    work_year = _candidate_work_publication_year(candidate)
    edition_years = _candidate_edition_years(candidate)
    recent_edition = any(year >= minimum_year for year in edition_years)
    if work_year is None:
        if str(candidate.get("publication_year_source") or "").strip().casefold() == "edition":
            edition_anchored_years = [
                *_year_values(candidate.get("first_publish_year")),
                *_year_values(candidate.get("publication_year")),
                *edition_years,
            ]
            if edition_anchored_years and min(edition_anchored_years) < minimum_year:
                return "recent_edition_of_old_work" if recent_edition else "work_too_old"
        return "missing_publication_date"
    if work_year < minimum_year:
        return "recent_edition_of_old_work" if recent_edition else "work_too_old"
    return None


def _candidate_rating(candidate: dict) -> float | None:
    for key in ("provider_rating", "rating"):
        value = candidate.get(key)
        try:
            parsed = float(value)
        except (TypeError, ValueError):
            continue
        if math.isfinite(parsed) and parsed > 0:
            return parsed
    return None


def _candidate_count(candidate: dict, *keys: str) -> int:
    for key in keys:
        value = candidate.get(key)
        try:
            parsed = int(value)
        except (TypeError, ValueError):
            continue
        if parsed > 0:
            return parsed
    return 0


def _broad_genre(candidate: dict, preferred_bucket: str | None = None) -> tuple[str, str] | None:
    values = [
        *(candidate.get("genres") or []),
        *(candidate.get("subjects") or []),
        *(candidate.get("cached_tags") or []),
        candidate.get("description") or "",
    ]
    haystack = " ".join(str(value or "").casefold() for value in values)
    if preferred_bucket:
        for key, label, terms in HARDCOVER_GENRE_BUCKETS:
            if key == preferred_bucket and any(term in haystack for term in terms):
                return key, label
    for key, label, terms in HARDCOVER_GENRE_BUCKETS:
        if any(term in haystack for term in terms):
            return key, label
    return None


def _candidate_source_url(candidate: dict) -> str | None:
    urls = candidate.get("source_urls")
    if isinstance(urls, list):
        for url in urls:
            text = str(url or "").strip()
            if text:
                return text
    return str(candidate.get("source_url") or "").strip() or None


def _valid_external_candidate(candidate: dict, library_keys: set[str]) -> bool:
    title = str(candidate.get("title") or "").strip()
    authors = candidate.get("authors") if isinstance(candidate.get("authors"), list) else []
    if not title or not authors:
        return False
    if _candidate_identity_keys(candidate) & library_keys:
        return False
    integrity = evaluate_candidate_integrity(candidate)
    return integrity.recommendation_eligible


def _popularity_score(candidate: dict) -> float:
    users = _candidate_count(candidate, "provider_user_count", "users_count")
    activities = _candidate_count(candidate, "provider_activity_count", "activities_count")
    ratings_count = _candidate_count(candidate, "provider_rating_count", "ratings_count")
    rating = _candidate_rating(candidate) or 0.0
    year = _candidate_year(candidate)
    current_year = datetime.now(timezone.utc).year
    recency = 0.0 if year is None else max(0.0, 1.0 - max(0, current_year - year) / 5)
    return (
        math.log1p(users) * 0.32
        + math.log1p(activities) * 0.28
        + math.log1p(ratings_count) * 0.22
        + max(0.0, rating - 3.5) * 0.32
        + recency * 1.15
    )


def _discovery_label(candidate: dict, *, genre_label: str | None = None, newly_found: bool = False) -> str:
    year = _candidate_work_publication_year(candidate) if newly_found else _candidate_year(candidate)
    if newly_found and year:
        return f"Published in {year}"
    if genre_label:
        return f"Trending {genre_label.split('/')[0].strip()}"
    return "Recently published" if newly_found else "Newly found"


def _external_section_item(candidate: dict, *, section: str, genre_label: str | None = None) -> dict:
    authors = [str(author).strip() for author in candidate.get("authors") or [] if str(author).strip()]
    author = authors[0] if authors else "Unknown author"
    year = _candidate_work_publication_year(candidate) if section == "newly_found" else _candidate_year(candidate)
    rating = _candidate_rating(candidate)
    ratings_count = _candidate_count(candidate, "provider_rating_count", "ratings_count") or None
    users_count = _candidate_count(candidate, "provider_user_count", "users_count") or None
    activities_count = _candidate_count(candidate, "provider_activity_count", "activities_count") or None
    isbn = candidate.get("isbn_uid")
    source_url = _candidate_source_url(candidate)
    identities = sorted(_candidate_identity_keys(candidate))
    work_id = str(candidate.get("work_key") or candidate.get("edition_key") or (identities[0] if identities else "")).strip()
    if not work_id:
        work_id = f"hardcover:{_normalized_identity_text(candidate.get('title'))}:{_normalized_identity_text(author)}"
    discovery_reason = f"Published in {year}" if year else "Recently published"
    label = _discovery_label(candidate, genre_label=genre_label, newly_found=section == "newly_found")
    return {
        "recommendation_id": f"{section}:{work_id}",
        "work_id": work_id,
        "external_id": candidate.get("work_key") or candidate.get("edition_key"),
        "edition_id": candidate.get("edition_key"),
        "isbn": isbn,
        "isbn_10": isbn if isinstance(isbn, str) and len(isbn) == 10 else None,
        "isbn_13": isbn if isinstance(isbn, str) and len(isbn) == 13 else None,
        "book_id": None,
        "canonical_identity": work_id,
        "canonical_title": candidate.get("title") or "Untitled",
        "display_title": candidate.get("title") or "Untitled",
        "original_title": candidate.get("original_title"),
        "canonical_author": author,
        "authors": authors,
        "cover_url": candidate.get("cover_url"),
        "publication_year": year,
        "first_publish_year": year,
        "page_count": candidate.get("total_pages"),
        "total_pages": candidate.get("total_pages"),
        "publisher": candidate.get("publisher"),
        "source_url": source_url,
        "source_urls": [source_url] if source_url else [],
        "provider_source_id": candidate.get("work_key") or candidate.get("edition_key"),
        "provider_rating": rating,
        "rating": rating,
        "ratings_count": ratings_count,
        "users_count": users_count,
        "activities_count": activities_count,
        "language": candidate.get("language"),
        "score": None,
        "final_score": None,
        "reader_likelihood_score": None,
        "match_percentage": None,
        "match_label": label,
        "qualitative_match_label": label,
        "discovery_label": label,
        "genres": [genre_label] if genre_label else clean_reader_tags(candidate.get("genres") or [], max_tags=5),
        "traits": clean_reader_tags(candidate.get("subjects") or [], max_tags=5),
        "explanation": {
            "primary_reason": discovery_reason,
            "related_books": [],
            "shared_genres": [],
            "shared_traits": [],
            "style": "discovery",
        },
        "reader_explanation": discovery_reason,
        "library_state": {
            "in_library": False,
            "status": None,
            "selected_edition_id": None,
        },
        "in_library": False,
        "is_in_library": False,
        "source": "hardcover",
        "external_discovery": True,
        "discovery_source": "hardcover",
        "discovery_reason": discovery_reason,
        "source_type": "external_discovery",
        "provider": "hardcover",
        "broad_genre": genre_label,
    }


def _search_hardcover(query: str) -> list[dict]:
    try:
        return search_candidates(query)
    except Exception as exc:
        logger.info("hardcover_discovery_unavailable query=%r error=%s", query, exc)
        return []


def _nyt_text(candidate: dict) -> str:
    values = [
        candidate.get("title"),
        candidate.get("description"),
        candidate.get("list_name"),
        candidate.get("display_name"),
        candidate.get("broad_genre"),
        *(candidate.get("genres") or []),
        *(candidate.get("subjects") or []),
    ]
    return " ".join(str(value or "").casefold() for value in values)


def _nyt_publication_year(candidate: dict) -> int | None:
    for key in ("publication_year", "first_publish_year", "published_year"):
        try:
            parsed = int(candidate.get(key))
        except (TypeError, ValueError):
            continue
        if 1000 <= parsed <= datetime.now(timezone.utc).year + 1:
            return parsed
    return _year_from_date(candidate.get("published_date"))


def _nyt_audience_category(candidate: dict) -> tuple[str | None, str | None]:
    text = _nyt_text(candidate)
    if not str(candidate.get("title") or "").strip() or not (candidate.get("authors") or candidate.get("author")):
        return None, "missing_metadata"
    juvenile_terms = (
        "children",
        "middle grade",
        "picture book",
        "picture books",
        "early reader",
        "early readers",
        "juvenile",
        "school age",
        "school-age",
    )
    juvenile_titles = ("wonder", "investigators")
    title_key = _normalized_identity_text(candidate.get("title"))
    if any(term in text for term in juvenile_terms) or any(title_key.startswith(title) for title in juvenile_titles):
        if any(term in text for term in ("graphic", "manga", "comic", "comics")) or "investigators" in title_key:
            return None, "juvenile_graphic"
        return None, "children_or_middle_grade"
    if any(term in text for term in ("graphic", "manga", "comic", "comics")):
        return "manga_graphic", None
    if "young adult" in text or re.search(r"\bya\b", text):
        return "young_adult", None
    if "romance" in text:
        return "romance", None
    if any(term in text for term in ("fantasy", "science fiction", "sci fi", "sci-fi")):
        return "fantasy_scifi", None
    if any(term in text for term in ("mystery", "thriller", "suspense", "crime")):
        return "mystery_thriller", None
    if any(term in text for term in ("nonfiction", "business", "advice", "how to", "memoir", "biography")):
        return "nonfiction", None
    if "fiction" in text or not candidate.get("broad_genre"):
        return "fiction", None
    return "fiction", None


def _nyt_freshness_tier(candidate: dict) -> int:
    weeks = _safe_int(candidate.get("weeks_on_list"), default=999)
    if weeks <= 12:
        return 0
    if weeks <= 26:
        return 1
    if weeks < 100:
        return 2
    if weeks < 500:
        return 3
    return 4


def _popular_candidate_sort_key(candidate: dict) -> tuple[int, int, int, int, str]:
    category, _reason = _nyt_audience_category(candidate)
    weeks = _safe_int(candidate.get("weeks_on_list"), default=999)
    rank = _safe_int(candidate.get("rank"), default=999)
    year = _nyt_publication_year(candidate)
    current_year = datetime.now(timezone.utc).year
    recent_year_penalty = 0 if year is not None and year >= current_year - 3 else 1 if year is not None else 2
    category_penalty = 0 if category == "fiction" else 1
    stable_id = sorted(_candidate_recommendation_ids(candidate, section="popular_this_week"))[0]
    return (weeks, rank, recent_year_penalty, category_penalty, stable_id)


def _popular_category_matches(category: str | None, wanted: str | None) -> bool:
    normalized = str(wanted or "any").strip().casefold()
    if normalized in {"", "any", "mixed", "refresh_all"}:
        return True
    if normalized == "fiction_heavy":
        return category == "fiction"
    return category == normalized


def _popular_category_counts(items: list[dict]) -> Counter[str]:
    counts: Counter[str] = Counter()
    for item in items:
        category = item.get("popular_category") or item.get("category")
        if category:
            counts[str(category)] += 1
    return counts


def _popular_limit_reason(category: str | None, counts: Counter[str]) -> str | None:
    if not category:
        return "missing_metadata"
    limit = POPULAR_CATEGORY_LIMITS.get(category)
    if limit is None or counts[category] < limit:
        return None
    if category == "young_adult":
        return "ya_limit"
    if category == "nonfiction":
        return "nonfiction_limit"
    if category == "manga_graphic":
        return "graphic_limit"
    return None


def _valid_nyt_candidate(candidate: dict, library_keys: set[str]) -> bool:
    if not _valid_external_candidate(candidate, library_keys):
        return False
    category, reason = _nyt_audience_category(candidate)
    return bool(category and not reason and candidate.get("rank"))


def _nyt_selection_key(candidate: dict) -> tuple[int, int, int, int, int]:
    rank = _safe_int(candidate.get("rank"), default=999)
    weeks = _safe_int(candidate.get("weeks_on_list"), default=0)
    last_week = _safe_int(candidate.get("rank_last_week"), default=0)
    movement = (last_week - rank) if last_week > 0 else 0
    has_cover = 1 if candidate.get("cover_url") else 0
    has_isbn = 1 if candidate.get("primary_isbn13") or candidate.get("primary_isbn10") or candidate.get("isbn_uid") else 0
    return (rank, -weeks, -movement, -has_cover, -has_isbn)


def _nyt_discovery_label(candidate: dict) -> str:
    rank = _safe_int(candidate.get("rank"), default=0)
    weeks = _safe_int(candidate.get("weeks_on_list"), default=0)
    last_week = _safe_int(candidate.get("rank_last_week"), default=0)
    genre = str(candidate.get("broad_genre") or "").strip()
    if rank == 1:
        return "#1 NYT Bestseller"
    if last_week <= 0:
        return "New to the NYT list"
    if weeks >= 2:
        return f"{weeks} weeks on the NYT list"
    return f"Trending in {genre}" if genre else "Popular this week"


def _nyt_section_item(candidate: dict) -> dict:
    authors = [str(author).strip() for author in candidate.get("authors") or [] if str(author).strip()]
    author = authors[0] if authors else "Unknown author"
    source_url = _candidate_source_url(candidate)
    isbn13 = candidate.get("primary_isbn13") or (candidate.get("isbn_uid") if len(str(candidate.get("isbn_uid") or "")) == 13 else None)
    isbn10 = candidate.get("primary_isbn10") or (candidate.get("isbn_uid") if len(str(candidate.get("isbn_uid") or "")) == 10 else None)
    external_id = str(candidate.get("external_id") or candidate.get("work_key") or "").strip()
    if not external_id:
        external_id = f"nyt:{_normalized_identity_text(candidate.get('title'))}:{_normalized_identity_text(author)}"
    label = _nyt_discovery_label(candidate)
    list_name = candidate.get("display_name") or candidate.get("list_name")
    rank = _safe_int(candidate.get("rank"), default=0) or None
    weeks = _safe_int(candidate.get("weeks_on_list"), default=0) or None
    category, _reason = _nyt_audience_category(candidate)
    reason = (
        f"#{rank} on {list_name}" if rank and list_name else
        f"{weeks} weeks on the NYT list" if weeks else
        "Popular this week on the New York Times bestseller lists"
    )
    return {
        "recommendation_id": f"popular_this_week:{external_id}",
        "work_id": external_id,
        "external_id": external_id,
        "edition_id": None,
        "isbn": isbn13 or isbn10,
        "isbn_10": isbn10,
        "isbn_13": isbn13,
        "book_id": None,
        "canonical_identity": external_id,
        "canonical_title": candidate.get("title") or "Untitled",
        "display_title": candidate.get("title") or "Untitled",
        "canonical_author": author,
        "authors": authors,
        "cover_url": candidate.get("cover_url"),
        "publication_year": None,
        "publisher": candidate.get("publisher"),
        "source_url": source_url,
        "source_urls": [source_url] if source_url else [],
        "provider_source_id": external_id,
        "score": None,
        "final_score": None,
        "reader_likelihood_score": None,
        "match_percentage": None,
        "match_label": label,
        "qualitative_match_label": label,
        "discovery_label": label,
        "genres": [candidate.get("broad_genre")] if candidate.get("broad_genre") else [],
        "traits": [list_name] if list_name else [],
        "broad_genre": candidate.get("broad_genre"),
        "popular_category": category,
        "category": category,
        "nyt_rank": rank,
        "nyt_rank_last_week": _safe_int(candidate.get("rank_last_week"), default=0) or None,
        "nyt_weeks_on_list": weeks,
        "nyt_list_name": list_name,
        "nyt_list_name_encoded": candidate.get("list_name_encoded"),
        "nyt_published_date": candidate.get("published_date"),
        "nyt_bestsellers_date": candidate.get("bestsellers_date"),
        "contributor": candidate.get("contributor"),
        "explanation": {
            "primary_reason": reason,
            "related_books": [],
            "shared_genres": [],
            "shared_traits": [],
            "style": "discovery",
        },
        "reader_explanation": reason,
        "library_state": {"in_library": False, "status": None, "selected_edition_id": None},
        "in_library": False,
        "is_in_library": False,
        "source": "nyt",
        "external_discovery": True,
        "discovery_source": "nyt",
        "discovery_reason": reason,
        "source_type": "external_discovery",
        "provider": "nyt",
    }


def _popular_candidate_pool(
    library_keys: set[str],
    *,
    excluded_ids: set[str] | None = None,
    category: str | None = None,
    preference: str | None = None,
    current_items: list[dict] | None = None,
) -> tuple[list[dict], dict]:
    candidates, status = nyt_current_overview()
    excluded = set(excluded_ids or set())
    rejection_counts: Counter[str] = Counter({reason: 0 for reason in POPULAR_REJECTION_REASONS})
    base_valid: list[tuple[dict, str]] = []
    fresh_valid_count = 0
    has_newer_valid = False
    seen_keys: set[str] = set()
    for candidate in sorted(candidates, key=_nyt_selection_key):
        category_name, reason = _nyt_audience_category(candidate)
        if reason:
            rejection_counts[reason] += 1
            continue
        if not category_name or not _valid_external_candidate(candidate, library_keys) or not candidate.get("rank"):
            rejection_counts["missing_metadata"] += 1
            continue
        identities = _candidate_identity_keys(candidate)
        if identities & seen_keys:
            rejection_counts["duplicate"] += 1
            continue
        seen_keys.update(identities)
        weeks = _safe_int(candidate.get("weeks_on_list"), default=999)
        if weeks <= 26:
            fresh_valid_count += 1
        if weeks < 500:
            has_newer_valid = True
        base_valid.append((candidate, category_name))

    pool: list[dict] = []
    current_counts = _popular_category_counts(current_items or [])
    for candidate, category_name in base_valid:
        weeks = _safe_int(candidate.get("weeks_on_list"), default=999)
        if weeks >= 500 and has_newer_valid:
            rejection_counts["stale_bestseller"] += 1
            continue
        if weeks >= 100 and fresh_valid_count >= 3:
            rejection_counts["stale_bestseller"] += 1
            continue
        if not _popular_category_matches(category_name, category or preference):
            continue
        if _ids_match_candidate(candidate, excluded, section="popular_this_week"):
            rejection_counts["duplicate"] += 1
            continue
        item = _nyt_section_item(candidate)
        item["popular_category"] = category_name
        item["category"] = category_name
        item["_sort_candidate"] = candidate
        item["_sort_key"] = _popular_candidate_sort_key(candidate)
        item["_category_counts"] = current_counts
        pool.append(item)

    pool.sort(key=lambda item: item["_sort_key"])
    diagnostics = {
        "provider_status": status.to_dict(),
        "nyt_request_count": status.request_count,
        "cached": status.cached,
        "raw_count": len(candidates),
        "normalized_count": len(candidates),
        "valid_count": len(base_valid),
        "rejection_diagnostics": dict(rejection_counts),
        "weekly_popularity_supported": True,
        "popularity_basis": "NYT bestseller list rank, weeks on list, rank movement, audience category, and freshness",
    }
    return pool, diagnostics


def _select_popular_items(
    pool: list[dict],
    *,
    limit: int,
    preference: str | None = None,
    current_items: list[dict] | None = None,
) -> tuple[list[dict], Counter[str]]:
    selected: list[dict] = []
    rejection_counts: Counter[str] = Counter({reason: 0 for reason in POPULAR_REJECTION_REASONS})
    selected_identities: set[str] = set()
    counts = _popular_category_counts(current_items or [])

    preferred = str(preference or "mixed").strip().casefold()
    ordered_pool = list(pool)
    if preferred not in {"", "mixed", "refresh_all"}:
        ordered_pool.sort(
            key=lambda item: (
                0 if _popular_category_matches(str(item.get("popular_category")), preferred) else 1,
                item.get("_sort_key") or (),
            )
        )

    for item in ordered_pool:
        if len(selected) >= limit:
            break
        category_name = str(item.get("popular_category") or "")
        limit_reason = _popular_limit_reason(category_name, counts)
        if limit_reason:
            rejection_counts[limit_reason] += 1
            continue
        identities = _section_item_identity_keys(item)
        if identities & selected_identities:
            rejection_counts["duplicate"] += 1
            continue
        clean_item = {key: value for key, value in item.items() if not key.startswith("_")}
        selected.append(clean_item)
        selected_identities.update(identities)
        counts[category_name] += 1
    return selected, rejection_counts


def _popular_this_week_items(library_keys: set[str]) -> tuple[list[dict], dict]:
    pool, diagnostics = _popular_candidate_pool(library_keys)
    selected, selection_rejections = _select_popular_items(pool, limit=POPULAR_NOW_LIMIT)
    rejection_counts = Counter(diagnostics.get("rejection_diagnostics") or {})
    rejection_counts.update(selection_rejections)
    diagnostics["rejection_diagnostics"] = dict(rejection_counts)
    diagnostics["final_count"] = len(selected)
    diagnostics["remaining_candidate_count"] = max(0, len(pool) - len(selected))
    return selected, diagnostics


def _newly_found_category(candidate: dict) -> str:
    values = [
        candidate.get("title"),
        candidate.get("subtitle"),
        candidate.get("description"),
        *(candidate.get("genres") or []),
        *(candidate.get("subjects") or []),
        *(candidate.get("cached_tags") or []),
    ]
    text = " ".join(str(value or "").casefold() for value in values)
    if "young adult" in text or re.search(r"\bya\b", text):
        return "young_adult"
    romance_signals = (
        "romance",
        "contemporary romance",
        "romantic fiction",
        "historical romance",
        "romantic comedy",
        "rom-com",
        "rom com",
        "love story",
        "love stories",
    )
    womens_fiction_with_romance = "women" in text and "fiction" in text and any(
        signal in text for signal in ("romance", "romantic", "love story", "love stories")
    )
    if any(signal in text for signal in romance_signals) or womens_fiction_with_romance:
        return "romance"
    if any(term in text for term in ("fantasy", "science fiction", "sci fi", "sci-fi", "speculative")):
        return "fantasy_scifi"
    if any(term in text for term in ("mystery", "thriller", "suspense", "crime")):
        return "mystery_thriller"
    if any(term in text for term in ("manga", "graphic novel", "comics", "comic")):
        return "manga_graphic"
    if "historical" in text:
        return "historical_fiction"
    if "literary" in text:
        return "literary_fiction"
    return "fiction"


def _newly_candidate_detail(candidate: dict, rejection_reason: str | None = None) -> dict:
    return {
        "title": candidate.get("title"),
        "publication_year": _candidate_work_publication_year(candidate) or _candidate_year(candidate),
        "normalized_genres": clean_reader_tags(candidate.get("genres") or [], max_tags=8),
        "subjects_tags": clean_reader_tags([*(candidate.get("subjects") or []), *(candidate.get("cached_tags") or [])], max_tags=12),
        "category_classification": _newly_found_category(candidate),
        "rejection_reason": rejection_reason,
    }


def _newly_category_matches(category: str | None, wanted: str | None) -> bool:
    normalized = str(wanted or "any").strip().casefold()
    if normalized in {"", "any", "mixed", "refresh_all"}:
        return True
    if normalized == "fiction_heavy":
        return category == "fiction"
    if normalized == "fiction":
        return category in {"fiction", "literary_fiction", "historical_fiction"}
    return category == normalized


def _strong_user_genres(books: list) -> list[str]:
    weights: Counter[str] = Counter()
    for book in books:
        values = [*(book.genres or []), *(book.subjects or [])]
        status = normalize_status(book.read_status)
        multiplier = 3 if status == "completed" and (book.star_rating or 0) >= 4 else 2 if status == "completed" else 1
        for value in values:
            label = _facet_label(value)
            if label:
                weights[label] += multiplier
    return [label for label, _count in weights.most_common(4)]


def _newly_found_queries(preferred_genres: list[str] | None = None, preference: str | None = None) -> list[str]:
    current_year = datetime.now(timezone.utc).year
    previous_year = current_year - 1
    genre_terms = [term for term in (preferred_genres or []) if term][:3]
    preference_map = {
        "young_adult": "young adult",
        "romance": "romance",
        "fantasy_scifi": "fantasy science fiction",
        "mystery_thriller": "mystery thriller",
        "manga_graphic": "manga graphic novel",
        "literary_fiction": "literary fiction",
        "historical_fiction": "historical fiction",
        "fiction": "fiction",
        "fiction_heavy": "fiction",
    }
    preferred = preference_map.get(str(preference or "").strip().casefold())
    queries: list[str] = []
    if preferred:
        queries.extend([
            f"new {preferred} books {current_year}",
            f"new {preferred} releases {previous_year}",
        ])
    for genre in genre_terms:
        queries.append(f"new {genre} books {current_year}")
    queries.extend([
        f"new fiction releases {current_year}",
        f"best new fiction {current_year}",
        f"new hardcover fiction {current_year}",
        f"new fiction releases {previous_year}",
    ])
    return list(dict.fromkeys(query.strip() for query in queries if query.strip()))[:8]


def _romance_refetch_queries() -> list[str]:
    current_year = datetime.now(timezone.utc).year
    years = [current_year, current_year - 1, current_year - 2]
    queries: list[str] = []
    for year in years:
        queries.extend(
            [
                f"{year} romance",
                f"romance novels {year}",
                f"historical romance {year}",
                f"contemporary romance {year}",
            ]
        )
    for year in years:
        queries.extend(
            [
                f"new romance books {year}",
                f"new romance novels {year}",
                f"romance releases {year}",
                f"best romance books {year}",
                f"new contemporary romance books {year}",
                f"contemporary romance novels {year}",
                f"new historical romance books {year}",
                f"historical romance novels {year}",
            ]
        )
    return queries[:24]


def _default_newly_found_expansion_queries(preferred_genres: list[str] | None = None) -> list[str]:
    current_year = datetime.now(timezone.utc).year
    years = [current_year, current_year - 1, current_year - 2]
    queries: list[str] = []
    for year in years:
        queries.extend(
            [
                f"{year} romance",
                f"romance novels {year}",
                f"{year} fantasy",
                f"{year} science fiction",
                f"{year} mystery thriller",
                f"{year} literary fiction",
                f"{year} historical fiction",
                f"{year} young adult fiction",
            ]
        )
    for genre in preferred_genres or []:
        for year in years[:2]:
            queries.append(f"{year} {genre}")
    return list(dict.fromkeys(query.strip() for query in queries if query.strip()))[:24]


def _newly_genre_overlap(candidate: dict, preferred_genres: list[str] | None) -> int:
    preferred = {_normalized_identity_text(value) for value in (preferred_genres or []) if _normalized_identity_text(value)}
    if not preferred:
        return 0
    values = [
        *(candidate.get("genres") or []),
        *(candidate.get("subjects") or []),
        *(candidate.get("cached_tags") or []),
        candidate.get("description") or "",
    ]
    text = _normalized_identity_text(" ".join(str(value or "") for value in values))
    return sum(1 for value in preferred if value and value in text)


def _year_distribution(candidates: list[dict]) -> dict[str, int]:
    counts: Counter[str] = Counter()
    for candidate in candidates:
        year = _candidate_work_publication_year(candidate) or _candidate_year(candidate)
        counts[str(year) if year else "unknown"] += 1
    return dict(sorted(counts.items()))


def _newly_found_pool(
    library_keys: set[str],
    popular_items: list[dict],
    *,
    excluded_ids: set[str] | None = None,
    category: str | None = None,
    preference: str | None = None,
    preferred_genres: list[str] | None = None,
    source_path: str = "initial",
) -> tuple[list[dict], dict]:
    if not hardcover_enabled():
        diagnostics = _hardcover_discovery_diagnostics([], [], Counter())
        diagnostics["source_path"] = source_path
        diagnostics["cache_hit"] = False
        return [], diagnostics
    excluded = set(excluded_ids or set())
    popular_keys: set[str] = set()
    for item in popular_items:
        popular_keys.update(
            _book_identity_keys_from_values(
                title=item.get("canonical_title"),
                author=item.get("canonical_author"),
                work_id=item.get("canonical_identity") or item.get("work_id"),
                isbn=item.get("isbn_13") or item.get("isbn_10") or item.get("isbn"),
                related_isbns=[item.get("isbn_13"), item.get("isbn_10"), item.get("isbn")],
            )
        )
    pool: list[dict] = []
    seen_identities: set[str] = set(popular_keys)
    rejection_counts: Counter[str] = Counter()
    query_diagnostics: list[dict] = []
    category_candidate_details: list[dict] = []
    category_requested = str(category or preference or "any").strip().casefold() or "any"
    provider_refetch_performed = False
    provider_raw_count = 0
    cache_candidate_count = 0
    recent_count = 0
    accepted_count = 0
    cache_hit = False

    def process_queries(queries: list[str], *, refetch: bool = False) -> None:
        nonlocal provider_raw_count, cache_candidate_count, recent_count, accepted_count, cache_hit
        for query in queries:
            raw_candidates = _search_hardcover(query)[:NEWLY_FOUND_QUERY_LIMIT]
            cache_hit = cache_hit or any(bool(candidate.get("cache_hit")) for candidate in raw_candidates)
            provider_raw_count += len(raw_candidates)
            if not refetch:
                cache_candidate_count += len(raw_candidates)
            accepted_for_query = 0
            recent_for_query = 0
            for candidate in raw_candidates:
                rejection_reason = _newly_found_rejection_reason(candidate, library_keys)
                item_category = _newly_found_category(candidate)
                if category_requested == "romance" or item_category == "romance":
                    category_candidate_details.append(_newly_candidate_detail(candidate, rejection_reason))
                if rejection_reason:
                    rejection_counts[rejection_reason] += 1
                    continue
                recent_for_query += 1
                recent_count += 1
                identities = _candidate_identity_keys(candidate)
                duplicate_reason = None
                if identities & seen_identities:
                    duplicate_reason = "duplicate_in_library"
                if _ids_match_candidate(candidate, excluded, section="newly_found"):
                    duplicate_reason = "duplicate_in_library"
                if duplicate_reason:
                    rejection_counts[duplicate_reason] += 1
                    if category_requested == "romance" or item_category == "romance":
                        category_candidate_details.append(_newly_candidate_detail(candidate, duplicate_reason))
                    continue
                if not _newly_category_matches(item_category, category or preference):
                    continue
                item = _external_section_item(
                    candidate,
                    section="newly_found",
                    genre_label=_broad_genre(candidate)[1] if _broad_genre(candidate) else None,
                )
                item["newly_found_category"] = item_category
                item["category"] = item_category
                confidence = _safe_float(candidate.get("confidence_score"), default=0.0)
                item["_sort_key"] = (
                    -confidence,
                    -_popularity_score(candidate),
                    -_newly_genre_overlap(candidate, preferred_genres),
                    sorted(_candidate_recommendation_ids(candidate, section="newly_found"))[0],
                )
                pool.append(item)
                seen_identities.update(identities)
                accepted_for_query += 1
                accepted_count += 1
            query_diagnostics.append(
                {
                    "query": query,
                    "raw_count": len(raw_candidates),
                    "normalized_count": len(raw_candidates),
                    "recent_count": recent_for_query,
                    "accepted_count": accepted_for_query,
                    "year_distribution": _year_distribution(raw_candidates),
                    "rejection_reasons": {reason: int(rejection_counts.get(reason, 0)) for reason in NEWLY_FOUND_REJECTION_REASONS},
                    "refetch": refetch,
                }
            )

    initial_queries = _newly_found_queries(preferred_genres, preference or category)
    process_queries(initial_queries)
    if category_requested in {"any", "mixed", "refresh_all"} and len(pool) < NEWLY_FOUND_LIMIT:
        fallback_queries = [query for query in _default_newly_found_expansion_queries(preferred_genres) if query not in set(initial_queries)]
        if fallback_queries:
            provider_refetch_performed = True
            process_queries(fallback_queries, refetch=True)
    if category_requested == "romance" and not any(item.get("newly_found_category") == "romance" for item in pool):
        fallback_queries = [query for query in _romance_refetch_queries() if query not in set(initial_queries)]
        if fallback_queries:
            provider_refetch_performed = True
            process_queries(fallback_queries, refetch=True)
    pool.sort(key=lambda item: item["_sort_key"])
    diagnostics = _hardcover_discovery_diagnostics(pool, query_diagnostics, rejection_counts)
    diagnostics.update(
        {
            "category_requested": category_requested,
            "source_path": source_path,
            "cache_candidate_count": cache_candidate_count,
            "category_match_count": sum(1 for item in pool if _newly_category_matches(str(item.get("newly_found_category")), category_requested)),
            "provider_refetch_performed": provider_refetch_performed,
            "provider_raw_count": provider_raw_count,
            "cache_hit": cache_hit,
            "raw_count": provider_raw_count,
            "normalized_count": provider_raw_count,
            "recent_count": recent_count,
            "deduped_count": len(pool),
            "accepted_count": accepted_count,
            "rejection_counts": {reason: int(rejection_counts.get(reason, 0)) for reason in NEWLY_FOUND_REJECTION_REASONS},
            "category_distribution": dict(Counter(str(item.get("newly_found_category") or "unknown") for item in pool)),
            "category_candidates": category_candidate_details,
        }
    )
    diagnostics["remaining_candidate_count"] = len(pool)
    return pool, diagnostics


def _select_newly_found_items(pool: list[dict], *, limit: int, preference: str | None = None) -> list[dict]:
    ordered_pool = list(pool)
    preferred = str(preference or "mixed").strip().casefold()
    if preferred not in {"", "mixed", "refresh_all"}:
        ordered_pool.sort(
            key=lambda candidate: (
                0 if _newly_category_matches(str(candidate.get("newly_found_category")), preferred) else 1,
                candidate.get("_sort_key") or (),
            )
        )
    selected: list[dict] = []
    seen_categories: set[str] = set()
    if preferred in {"", "mixed", "refresh_all"}:
        for item in ordered_pool:
            if len(selected) >= limit:
                break
            category = str(item.get("newly_found_category") or "unknown")
            if category in seen_categories:
                continue
            selected.append(item)
            seen_categories.add(category)
    for item in ordered_pool:
        if len(selected) >= limit:
            break
        if item in selected:
            continue
        selected.append(item)
    return [{key: value for key, value in item.items() if not key.startswith("_")} for item in selected[:limit]]


def _build_newly_found_section(
    library_keys: set[str],
    popular_items: list[dict],
    *,
    preferred_genres: list[str] | None = None,
    excluded_ids: set[str] | None = None,
    preference: str | None = None,
    category: str | None = None,
    limit: int = NEWLY_FOUND_LIMIT,
    source_path: str = "initial",
) -> tuple[list[dict], dict]:
    pool, diagnostics = _newly_found_pool(
        library_keys,
        popular_items,
        excluded_ids=excluded_ids,
        preference=preference,
        category=category,
        preferred_genres=preferred_genres,
        source_path=source_path,
    )
    selected = _select_newly_found_items(pool, limit=max(1, min(NEWLY_FOUND_LIMIT, limit)), preference=preference or category)
    diagnostics["remaining_candidate_count"] = max(0, len(pool) - len(selected))
    diagnostics["final_count"] = len(selected)
    return selected, diagnostics


def _newly_found_items(
    library_keys: set[str],
    popular_items: list[dict],
    *,
    preferred_genres: list[str] | None = None,
) -> tuple[list[dict], dict]:
    return _build_newly_found_section(
        library_keys,
        popular_items,
        preferred_genres=preferred_genres,
        limit=NEWLY_FOUND_LIMIT,
        source_path="initial",
    )


def _hardcover_discovery_diagnostics(selected: list[dict], query_diagnostics: list[dict], rejection_counts: Counter[str]) -> dict:
    rejections = {reason: int(rejection_counts.get(reason, 0)) for reason in NEWLY_FOUND_REJECTION_REASONS}
    query_count = len(query_diagnostics)
    return {
        "hardcover_query_count": query_count,
        "queries": query_diagnostics,
        "rejection_diagnostics": rejections,
        "provider_status": {
            "enabled": hardcover_enabled(),
            "available": hardcover_enabled() and query_count > 0,
            "cached": any(bool(item.get("cache_hit")) for item in selected),
            "request_count": query_count,
            "rejection_diagnostics": rejections,
        },
    }


def _candidate_dataframe_for_recommendations(
    db: Session,
    user_id: UUID,
    *,
    discovery_limit: int = 40,
) -> tuple[list, pd.DataFrame, object]:
    books = get_books_for_recommendation(db, user_id, MAX_RECOMMENDATION_BOOKS)
    df = books_to_dataframe(books, user_id)
    if not df.empty:
        df = df.astype(object).where(pd.notnull(df), None)
    discovery_diagnostics = DiscoveryDiagnostics(library_candidate_count=len(books))
    return books, df, discovery_diagnostics


def recommendation_facets(
    db: Session,
    user_id: UUID,
    *,
    kind: str,
    limit: int = 12,
) -> dict:
    _books, df, discovery_diagnostics = _candidate_dataframe_for_recommendations(
        db,
        user_id,
        discovery_limit=max(20, limit * 3),
    )
    if df.empty:
        return {"items": []}

    weights: Counter[str] = Counter()
    candidate_counts: defaultdict[str, int] = defaultdict(int)
    external_counts: defaultdict[str, int] = defaultdict(int)

    if kind == "authors":
        for _, row in df.iterrows():
            label = _display_author(row.get("Authors"))
            if not label:
                continue
            status = _candidate_status(row)
            if status == "completed":
                rating = float(row.get("Star Rating") or 0)
                weights[label] += 3 + (2 if rating >= 4 else 0)
            elif _is_eligible_candidate(row):
                candidate_counts[label] += 1
                weights[label] += 1
                if _source_type(row) == "external_discovery":
                    external_counts[label] += 1
            if bool(row.get("In Library")):
                weights[label] += 0.25
    else:
        for _, row in df.iterrows():
            status = _candidate_status(row)
            tags = list(row.get("Genres") or []) + list(row.get("Subjects") or [])
            for raw in tags:
                label = _facet_label(raw)
                if not label:
                    continue
                if status == "completed":
                    rating = float(row.get("Star Rating") or 0)
                    weights[label] += 3 + (2 if rating >= 4 else 0)
                elif _is_eligible_candidate(row):
                    candidate_counts[label] += 1
                    weights[label] += 1
                    if _source_type(row) == "external_discovery":
                        external_counts[label] += 1
                if bool(row.get("In Library")):
                    weights[label] += 0.25

    items = []
    seen: set[str] = set()
    for label, weight in weights.most_common():
        key = label.casefold()
        if key in seen or candidate_counts[label] <= 0:
            continue
        seen.add(key)
        items.append(
            {
                "label": label,
                "score": round(float(weight), 3),
                "candidate_count": candidate_counts[label],
                "external_candidate_count": external_counts[label],
            }
        )
        if len(items) >= limit:
            break

    logger.info(
        "recommendation_facet_diagnostics kind=%s item_count=%s external_candidate_count=%s "
        "external_provider_attempts=%s external_provider_successes=%s deduplicated_external_count=%s",
        kind,
        len(items),
        sum(item["external_candidate_count"] for item in items),
        discovery_diagnostics.external_provider_attempts,
        discovery_diagnostics.external_provider_successes,
        discovery_diagnostics.deduplicated_external_count,
    )
    return {"items": items}


def recommendation_sections_response(
    recommendations: list[dict],
    *,
    style: str = "balanced",
    popular_this_week: list[dict] | None = None,
    newly_found: list[dict] | None = None,
    provider_status: dict | None = None,
    discovery_diagnostics: dict | None = None,
    profile_id: UUID | str | None = None,
    library_count: int | None = None,
) -> dict:
    normalized_style = _normalize_style(style)
    items: list[dict] = []
    seen_work_ids: set[str] = set()

    for recommendation in recommendations:
        book = recommendation.get("recommended_book") or recommendation.get("book") or {}
        work_id = str(
            recommendation.get("work_id")
            or book.get("work_id")
            or recommendation.get("recommendation_id")
            or book.get("recommendation_id")
            or book.get("id")
            or ""
        ).strip()
        if not work_id or work_id in seen_work_ids:
            continue
        seen_work_ids.add(work_id)
        if not bool(recommendation.get("in_library", True)):
            continue
        score = recommendation.get("score")
        related_books = (recommendation.get("related_books") or recommendation.get("matched_liked_books") or [])[:3]
        genres = _display_tags(recommendation.get("matched_genres") or [], max_tags=5)
        traits = (
            _display_tags(recommendation.get("matched_subjects") or [], max_tags=5 - len(genres))
            if len(genres) < 5
            else []
        )
        in_library = bool(recommendation.get("in_library", True))
        library_status = recommendation.get("library_status")
        public_provider = _public_discovery_source(
            recommendation.get("provider") or recommendation.get("discovery_source"),
            in_library=in_library,
        )
        publication_year = recommendation.get("publication_year") or book.get("publication_year") or book.get("first_publish_year")
        page_count = recommendation.get("page_count") or recommendation.get("total_pages") or book.get("page_count") or book.get("total_pages")
        isbn_10 = recommendation.get("isbn_10") or book.get("isbn_10")
        isbn_13 = recommendation.get("isbn_13") or book.get("isbn_13")
        score_breakdown = recommendation.get("score_breakdown") or {}
        reader_likelihood_score = recommendation.get("reader_likelihood_score") or score_breakdown.get("reader_likelihood_score")
        match_label = recommendation_match_label(
            score,
            reader_likelihood_score=reader_likelihood_score,
            score_breakdown=score_breakdown,
        )
        items.append(
            {
                "recommendation_id": recommendation.get("recommendation_id") or work_id,
                "work_id": work_id,
                "external_id": recommendation.get("external_id") or book.get("external_id"),
                "edition_id": recommendation.get("edition_id") or book.get("edition_id"),
                "isbn": recommendation.get("isbn") or book.get("isbn"),
                "isbn_10": isbn_10,
                "isbn_13": isbn_13,
                "book_id": str(recommendation.get("book_id")) if recommendation.get("book_id") is not None else None,
                "canonical_identity": recommendation.get("recommendation_id") or work_id,
                "canonical_title": book.get("title") or "Untitled",
                "display_title": book.get("display_title") or book.get("title") or "Untitled",
                "original_title": recommendation.get("original_title") or book.get("original_title"),
                "canonical_author": book.get("author") or "Unknown author",
                "cover_url": book.get("cover_url"),
                "publication_year": publication_year,
                "first_publish_year": publication_year,
                "page_count": page_count,
                "total_pages": page_count,
                "publisher": recommendation.get("publisher") or book.get("publisher"),
                "source_url": recommendation.get("source_url") or book.get("source_url"),
                "source_urls": recommendation.get("source_urls") or book.get("source_urls") or [],
                "provider_source_id": recommendation.get("provider_source_id") or book.get("provider_source_id"),
                "provider_rating": recommendation.get("provider_rating") or book.get("provider_rating"),
                "rating": recommendation.get("rating") or book.get("rating"),
                "ratings_count": recommendation.get("ratings_count") or book.get("ratings_count"),
                "users_count": recommendation.get("users_count") or book.get("users_count"),
                "activities_count": recommendation.get("activities_count") or book.get("activities_count"),
                "language": recommendation.get("language") or book.get("language"),
                "series_name": recommendation.get("series_name") or book.get("series_name"),
                "series_position": recommendation.get("series_position") or book.get("series_position"),
                "series_position_label": recommendation.get("series_position_label") or book.get("series_position_label"),
                "series_type": recommendation.get("series_type") or book.get("series_type"),
                "series_source": recommendation.get("series_source") or book.get("series_source"),
                "series_confidence": recommendation.get("series_confidence") or book.get("series_confidence"),
                "primary_edition": {
                    "edition_id": recommendation.get("edition_id") or book.get("edition_id") or work_id,
                    "isbn_10": isbn_10,
                    "isbn_13": isbn_13 or (work_id if len(work_id) == 13 and work_id.isdigit() else None),
                    "page_count": page_count,
                    "publication_year": publication_year,
                    "edition_type": "unknown",
                },
                "edition_count": 1,
                "score": score,
                "final_score": recommendation.get("final_score", score),
                "reader_likelihood_score": reader_likelihood_score,
                "match_percentage": recommendation_match_percentage(score),
                "match_label": match_label,
                "qualitative_match_label": match_label,
                "genres": genres,
                "traits": traits,
                "explanation": {
                    "primary_reason": recommendation.get("reason") or recommendation.get("explanation") or "Recommended based on your reading history.",
                    "related_books": [
                        {
                            "id": str(book.get("id") or ""),
                            "title": str(book.get("title") or ""),
                        }
                        for book in related_books
                    ],
                    "shared_genres": genres,
                    "shared_traits": traits,
                    "style": normalized_style,
                },
                "library_state": {
                    "in_library": in_library,
                    "status": normalize_status(library_status) if library_status else None,
                    "selected_edition_id": work_id if in_library else None,
                },
                "in_library": in_library,
                "is_in_library": in_library,
                "source": "library" if in_library else "external",
                "external_discovery": bool(recommendation.get("external_discovery", not in_library)),
                "discovery_source": recommendation.get("discovery_source"),
                "discovery_query": recommendation.get("discovery_query"),
                "discovery_reason": recommendation.get("discovery_reason"),
                "discovery_cluster_id": recommendation.get("discovery_cluster_id"),
                "exploration_mode": recommendation.get("exploration_mode"),
                "exploration_source": recommendation.get("exploration_source"),
                "provider_rank": recommendation.get("provider_rank"),
                "novelty_score": recommendation.get("novelty_score"),
                "discovery_anchor_titles": recommendation.get("discovery_anchor_titles") or [],
                "provider_metadata_confidence": recommendation.get("provider_metadata_confidence"),
                "score_breakdown": score_breakdown,
                "diagnostics": {
                    "score_breakdown": score_breakdown,
                    "explanation_source": score_breakdown.get("explanation_source"),
                    "match_percentage_source": "legacy_percentage_not_rendered",
                    "qualitative_match_label_source": "final_score_reader_likelihood_continuity",
                    "final_admission_decision": recommendation.get("final_admission_decision"),
                    "final_admission_reason": recommendation.get("final_admission_reason"),
                    "final_admission_path": recommendation.get("final_admission_path"),
                },
                "provider": public_provider,
            }
        )

    shelf_items = items[:SHELF_RECOMMENDATION_LIMIT]
    popular_items = list(popular_this_week or [])
    newly_found_items = list(newly_found or [])
    sections = [
        {
            "id": "from-your-shelf",
            "type": "shelf_recommendations",
            "title": "From Your Shelf",
            "source_book": None,
            "items": shelf_items,
        },
        {
            "id": "popular-this-week",
            "type": "popular_this_week",
            "title": "Popular This Week",
            "source_book": None,
            "items": popular_items,
        },
        {
            "id": "newly-found",
            "type": "newly_found",
            "title": "Newly found",
            "source_book": None,
            "items": newly_found_items,
        },
    ]

    return {
        "schema_version": 3,
        "sections": sections,
        "legacy_sections_deprecated": True,
        "shelf_recommendations": shelf_items,
        "popular_this_week": popular_items,
        "newly_found": newly_found_items,
        "provider_status": provider_status or {},
        "discovery_diagnostics": discovery_diagnostics or {},
        "request_context": {
            "profile_id": str(profile_id) if profile_id is not None else None,
            "library_count": library_count,
        },
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "style": normalized_style,
    }


def get_recommendation_sections(
    db: Session,
    user_id: UUID,
    top_n: int = 10,
    style: str = "balanced",
    refresh: bool = False,
    exclude_ids: set[str] | None = None,
    genre: str | None = None,
    author: str | None = None,
    min_pages: int | None = None,
    max_pages: int | None = None,
) -> dict:
    books = get_books_for_recommendation(db, user_id, MAX_RECOMMENDATION_BOOKS)
    user_books = [book for book in books if book.user_id == user_id]
    library_keys = _library_identity_keys(user_books)
    recommendations = get_recommendation(
        db,
        user_id,
        top_n=top_n,
        style=style,
        refresh=refresh,
        exclude_ids=exclude_ids,
        genre=genre,
        author=author,
        min_pages=min_pages,
        max_pages=max_pages,
    )
    popular_items, popular_diagnostics = _popular_this_week_items(library_keys)
    newly_items, newly_diagnostics = _newly_found_items(
        library_keys,
        popular_items,
        preferred_genres=_strong_user_genres(user_books),
    )
    provider_status = {
        "nyt": popular_diagnostics.get("provider_status", {}),
        "hardcover": newly_diagnostics.get("provider_status", {}),
    }
    diagnostics = {
        "nyt_request_count": int(popular_diagnostics.get("nyt_request_count") or 0),
        "hardcover_query_count": int(newly_diagnostics.get("hardcover_query_count") or 0),
        "nyt_cache": "in-memory overview cache with 6 hour default TTL",
        "hardcover_cache": "provider in-memory cache keyed by search query and limit",
        "weekly_popularity_supported": True,
        "popular_label": "Popular This Week",
        "popularity_basis": popular_diagnostics.get("popularity_basis"),
        "nyt_raw_count": int(popular_diagnostics.get("raw_count") or 0),
        "nyt_normalized_count": int(popular_diagnostics.get("normalized_count") or 0),
        "nyt_final_count": int(popular_diagnostics.get("final_count") or 0),
        "newly_found_rejection_diagnostics": newly_diagnostics.get("rejection_diagnostics", {}),
        "newly_found_queries_run": int(newly_diagnostics.get("hardcover_query_count") or 0),
        "newly_found_source_path": newly_diagnostics.get("source_path"),
        "newly_found_cache_hit": bool(newly_diagnostics.get("cache_hit")),
        "newly_found_raw_count": int(newly_diagnostics.get("raw_count") or 0),
        "newly_found_normalized_count": int(newly_diagnostics.get("normalized_count") or 0),
        "newly_found_recent_count": int(newly_diagnostics.get("recent_count") or 0),
        "newly_found_deduped_count": int(newly_diagnostics.get("deduped_count") or 0),
        "newly_found_accepted_count": int(newly_diagnostics.get("accepted_count") or 0),
        "newly_found_final_count": int(newly_diagnostics.get("final_count") or 0),
        "newly_found_category_distribution": newly_diagnostics.get("category_distribution", {}),
    }
    response = recommendation_sections_response(
        recommendations,
        style=style,
        popular_this_week=popular_items,
        newly_found=newly_items,
        provider_status=provider_status,
        discovery_diagnostics=diagnostics,
        profile_id=user_id,
        library_count=len(user_books),
    )
    logger.info(
        "recommendation_sections_response profile_id=%s library_count=%s schema_version=%s "
        "shelf_titles=%s popular_titles=%s newly_found_titles=%s",
        user_id,
        len(user_books),
        response.get("schema_version"),
        [item.get("canonical_title") for item in response.get("shelf_recommendations", [])],
        [item.get("canonical_title") for item in response.get("popular_this_week", [])],
        [item.get("canonical_title") for item in response.get("newly_found", [])],
    )
    return response


def _external_excluded_ids(
    current_recommendation_ids: list[str] | None,
    excluded_recommendation_ids: list[str] | None,
) -> set[str]:
    return {
        str(value).strip()
        for value in [*(current_recommendation_ids or []), *(excluded_recommendation_ids or [])]
        if str(value or "").strip()
    }


def replace_popular_this_week_item(
    db: Session,
    user_id: UUID,
    *,
    current_recommendation_ids: list[str] | None = None,
    excluded_recommendation_ids: list[str] | None = None,
    replace_recommendation_id: str | None = None,
    category: str = "any",
) -> dict:
    books = get_books_for_recommendation(db, user_id, MAX_RECOMMENDATION_BOOKS)
    library_keys = _library_identity_keys([book for book in books if book.user_id == user_id])
    excluded_ids = _external_excluded_ids(current_recommendation_ids, excluded_recommendation_ids)
    if replace_recommendation_id:
        excluded_ids.add(replace_recommendation_id)
    full_pool, _full_diagnostics = _popular_candidate_pool(library_keys)
    current_visible = [
        item
        for item in full_pool
        if _recommendation_ids_for_item(item) & set(current_recommendation_ids or [])
        and not (replace_recommendation_id and replace_recommendation_id in _recommendation_ids_for_item(item))
    ]
    pool, diagnostics = _popular_candidate_pool(
        library_keys,
        excluded_ids=excluded_ids,
        category=category,
    )
    replacement = None
    selected, selection_rejections = _select_popular_items(pool, limit=1, current_items=current_visible)
    if selected:
        replacement = selected[0]
    rejection_counts = Counter(diagnostics.get("rejection_diagnostics") or {})
    rejection_counts.update(selection_rejections)
    diagnostics["rejection_diagnostics"] = dict(rejection_counts)
    remaining = max(0, len(pool) - (1 if replacement else 0))
    return {
        "replacement": replacement,
        "provider_status": diagnostics.get("provider_status", {}),
        "remaining_candidate_count": remaining,
        "reason": None if replacement else "no_matching_candidates",
        "diagnostics": diagnostics,
    }


def refresh_popular_this_week_section(
    db: Session,
    user_id: UUID,
    *,
    current_recommendation_ids: list[str] | None = None,
    excluded_recommendation_ids: list[str] | None = None,
    preference: str = "mixed",
    limit: int = POPULAR_NOW_LIMIT,
) -> dict:
    books = get_books_for_recommendation(db, user_id, MAX_RECOMMENDATION_BOOKS)
    library_keys = _library_identity_keys([book for book in books if book.user_id == user_id])
    excluded_ids = _external_excluded_ids(current_recommendation_ids, excluded_recommendation_ids)
    pool, diagnostics = _popular_candidate_pool(
        library_keys,
        excluded_ids=excluded_ids,
        preference=preference,
    )
    selected, selection_rejections = _select_popular_items(pool, limit=max(1, min(POPULAR_NOW_LIMIT, limit)), preference=preference)
    rejection_counts = Counter(diagnostics.get("rejection_diagnostics") or {})
    rejection_counts.update(selection_rejections)
    diagnostics["rejection_diagnostics"] = dict(rejection_counts)
    return {
        "popular_this_week": selected,
        "provider_status": diagnostics.get("provider_status", {}),
        "remaining_candidate_count": max(0, len(pool) - len(selected)),
        "diagnostics": diagnostics,
    }


def replace_newly_found_item(
    db: Session,
    user_id: UUID,
    *,
    current_recommendation_ids: list[str] | None = None,
    excluded_recommendation_ids: list[str] | None = None,
    replace_recommendation_id: str | None = None,
    category: str = "any",
) -> dict:
    books = get_books_for_recommendation(db, user_id, MAX_RECOMMENDATION_BOOKS)
    user_books = [book for book in books if book.user_id == user_id]
    library_keys = _library_identity_keys(user_books)
    excluded_ids = _external_excluded_ids(current_recommendation_ids, excluded_recommendation_ids)
    if replace_recommendation_id:
        excluded_ids.add(replace_recommendation_id)
    pool, diagnostics = _newly_found_pool(
        library_keys,
        [],
        excluded_ids=excluded_ids,
        category=category,
        preferred_genres=_strong_user_genres(user_books),
        source_path="replace",
    )
    selected = _select_newly_found_items(pool, limit=1)
    replacement = selected[0] if selected else None
    return {
        "replacement": replacement,
        "provider_status": diagnostics.get("provider_status", {}),
        "remaining_candidate_count": max(0, len(pool) - (1 if replacement else 0)),
        "reason": None if replacement else "no_matching_candidates",
        "diagnostics": diagnostics,
    }


def refresh_newly_found_section(
    db: Session,
    user_id: UUID,
    *,
    current_recommendation_ids: list[str] | None = None,
    excluded_recommendation_ids: list[str] | None = None,
    preference: str = "mixed",
    limit: int = NEWLY_FOUND_LIMIT,
) -> dict:
    books = get_books_for_recommendation(db, user_id, MAX_RECOMMENDATION_BOOKS)
    user_books = [book for book in books if book.user_id == user_id]
    library_keys = _library_identity_keys(user_books)
    excluded_ids = _external_excluded_ids(current_recommendation_ids, excluded_recommendation_ids)
    selected, diagnostics = _build_newly_found_section(
        library_keys,
        [],
        excluded_ids=excluded_ids,
        preference=preference,
        preferred_genres=_strong_user_genres(user_books),
        limit=limit,
        source_path="refresh",
    )
    return {
        "newly_found": selected,
        "provider_status": diagnostics.get("provider_status", {}),
        "remaining_candidate_count": diagnostics.get("remaining_candidate_count", 0),
        "diagnostics": diagnostics,
    }


def invalidate_recommendation_cache():
    _get_recommendation_cached.cache_clear()
