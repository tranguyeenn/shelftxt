# backend/services/recommendation.py

from collections import Counter, defaultdict
from functools import lru_cache
from uuid import UUID
import asyncio
import logging
import re
import time

import pandas as pd
from sqlalchemy.orm import Session

from backend.env import is_local_env, ollama_enabled
from backend.repository.postgres_books_repository import get_books_for_recommendation
from backend.services.metadata_normalization import clean_reader_tags, normalize_genre, normalize_subject
from backend.services.recommendation_debug import rec_debug
from backend.services.recommendation_builder import build_recommendations, _feedback_identity_keys
from backend.services.recommendation_discovery import DiscoveryDiagnostics, discovery_candidate_rows
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

    discovery_diagnostics = None

    def _dataframe_with_discovery(discovery_rows: list[dict]) -> pd.DataFrame:
        df = base_df.copy()
        if not discovery_rows:
            return df.astype(object).where(pd.notnull(df), None) if not df.empty else df
        discovery_df = pd.DataFrame(discovery_rows)
        for column in discovery_df.columns:
            if column not in df.columns:
                df[column] = None
        for column in df.columns:
            if column not in discovery_df.columns:
                discovery_df[column] = None
        df = pd.DataFrame([*df.to_dict("records"), *discovery_df[df.columns].to_dict("records")])
        return df.astype(object).where(pd.notnull(df), None) if not df.empty else df

    def _build_from_rows(discovery_rows: list[dict]) -> tuple[list[dict], pd.DataFrame, pd.DataFrame]:
        df = _dataframe_with_discovery(discovery_rows)
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
    recommendations, df, unfiltered_df = _build_from_rows([])

    discovery_rows: list[dict] = []
    candidate_limit = max(50, top_n * 5)
    if refresh or len(recommendations) < top_n:
        local_rows, local_diagnostics = discovery_candidate_rows(
            db,
            user_id,
            books,
            limit=candidate_limit,
            allow_external=False,
        )
        discovery_diagnostics = local_diagnostics
        discovery_diagnostics.library_candidate_count = library_candidate_count
        discovery_rows = local_rows
        recommendations, df, unfiltered_df = _build_from_rows(discovery_rows)

    external_rows, external_diagnostics = discovery_candidate_rows(
        db,
        user_id,
        books,
        limit=candidate_limit,
        allow_external=True,
        include_broad_exploration=normalized_style in {"discovery", "external_first"},
    )
    discovery_diagnostics = external_diagnostics
    discovery_diagnostics.library_candidate_count = library_candidate_count
    discovery_rows = external_rows
    recommendations, df, unfiltered_df = _build_from_rows(discovery_rows)

    if discovery_diagnostics is None:
        discovery_diagnostics = DiscoveryDiagnostics(library_candidate_count=library_candidate_count)

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
    final = list(recommendations)
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


def recommendation_match_label(score: float | int | None) -> str:
    try:
        normalized = float(score or 0)
    except (TypeError, ValueError):
        normalized = 0.0
    if normalized >= 0.85:
        return "Strong match"
    if normalized >= 0.65:
        return "Good match"
    if normalized >= 0.4:
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


def _candidate_dataframe_for_recommendations(
    db: Session,
    user_id: UUID,
    *,
    discovery_limit: int = 40,
) -> tuple[list, pd.DataFrame, object]:
    books = get_books_for_recommendation(db, user_id, MAX_RECOMMENDATION_BOOKS)
    df = books_to_dataframe(books, user_id)
    discovery_rows, discovery_diagnostics = discovery_candidate_rows(
        db,
        user_id,
        books,
        limit=discovery_limit,
    )
    if discovery_rows:
        discovery_df = pd.DataFrame(discovery_rows)
        for column in discovery_df.columns:
            if column not in df.columns:
                df[column] = None
        for column in df.columns:
            if column not in discovery_df.columns:
                discovery_df[column] = None
        df = pd.DataFrame([*df.to_dict("records"), *discovery_df[df.columns].to_dict("records")])
    if not df.empty:
        df = df.astype(object).where(pd.notnull(df), None)
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
) -> dict:
    from datetime import datetime, timezone

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
        items.append(
            {
                "recommendation_id": recommendation.get("recommendation_id") or work_id,
                "work_id": work_id,
                "book_id": str(recommendation.get("book_id")) if recommendation.get("book_id") is not None else None,
                "canonical_identity": recommendation.get("recommendation_id") or work_id,
                "canonical_title": book.get("title") or "Untitled",
                "display_title": book.get("display_title") or book.get("title") or "Untitled",
                "original_title": recommendation.get("original_title") or book.get("original_title"),
                "canonical_author": book.get("author") or "Unknown author",
                "cover_url": book.get("cover_url"),
                "series_name": recommendation.get("series_name") or book.get("series_name"),
                "series_position": recommendation.get("series_position") or book.get("series_position"),
                "series_position_label": recommendation.get("series_position_label") or book.get("series_position_label"),
                "series_type": recommendation.get("series_type") or book.get("series_type"),
                "series_source": recommendation.get("series_source") or book.get("series_source"),
                "series_confidence": recommendation.get("series_confidence") or book.get("series_confidence"),
                "primary_edition": {
                    "edition_id": work_id,
                    "isbn_10": None,
                    "isbn_13": work_id if len(work_id) == 13 and work_id.isdigit() else None,
                    "page_count": None,
                    "publication_year": None,
                    "edition_type": "unknown",
                },
                "edition_count": 1,
                "score": score,
                "final_score": recommendation.get("final_score", score),
                "match_percentage": recommendation_match_percentage(score),
                "match_label": recommendation_match_label(score),
                "qualitative_match_label": recommendation_match_label(score),
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
                "discovery_cluster_id": recommendation.get("discovery_cluster_id"),
                "exploration_mode": recommendation.get("exploration_mode"),
                "exploration_source": recommendation.get("exploration_source"),
                "provider_rank": recommendation.get("provider_rank"),
                "novelty_score": recommendation.get("novelty_score"),
                "discovery_anchor_titles": recommendation.get("discovery_anchor_titles") or [],
                "provider_metadata_confidence": recommendation.get("provider_metadata_confidence"),
                "score_breakdown": recommendation.get("score_breakdown") or {},
                "diagnostics": {
                    "score_breakdown": recommendation.get("score_breakdown") or {},
                    "explanation_source": (recommendation.get("score_breakdown") or {}).get("explanation_source"),
                    "match_percentage_source": "legacy_percentage_not_rendered",
                    "qualitative_match_label_source": "thresholds_on_final_score",
                },
                "provider": recommendation.get("provider") or recommendation.get("discovery_source"),
            }
        )

    sections = []
    if items:
        sections.append(
            {
                "id": "for-you",
                "type": "for_you",
                "title": "For You",
                "source_book": None,
                "items": items,
            }
        )
        sections.extend(_build_grouped_recommendation_sections(items))

    return {
        "sections": sections,
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
    return recommendation_sections_response(recommendations, style=style)


def invalidate_recommendation_cache():
    _get_recommendation_cached.cache_clear()
