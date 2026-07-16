from __future__ import annotations

from collections import Counter
from functools import cmp_to_key
import os

import pandas as pd

LIBRARY_CLOSE_CALL_MARGIN = 0.04
MIN_EXTERNAL_RESULTS_FOR_TEN = 3
MAX_EXTERNAL_RESULTS_FOR_TEN = 7
EXTERNAL_RELATIVE_SCORE_MARGIN = 0.15
DEFAULT_MAX_SAME_AUTHOR_RESULTS = 1
MAX_SAME_AUTHOR_RESULTS = 2
DEFAULT_SECOND_AUTHOR_TITLE_SCORE_THRESHOLD = 0.6
MAX_SAME_NARROW_GENRE_RESULTS = 3
MAX_SAME_SERIES_RESULTS = 1
DEFAULT_RECOMMENDATION_LIBRARY_SHARE = 0.35
DEFAULT_RECOMMENDATION_EXTERNAL_SHARE = 0.65


def _safe_score(value: object, default: float = 0.0) -> float:
    try:
        score = float(value)
    except (TypeError, ValueError):
        score = default
    if pd.isna(score):
        score = default
    return min(1.0, max(0.0, score))


def second_author_title_score_threshold() -> float:
    raw = os.getenv("SECOND_AUTHOR_TITLE_SCORE_THRESHOLD")
    if raw is None:
        return DEFAULT_SECOND_AUTHOR_TITLE_SCORE_THRESHOLD
    return _safe_score(raw, DEFAULT_SECOND_AUTHOR_TITLE_SCORE_THRESHOLD)


def recommendation_library_share() -> float:
    raw = os.getenv("RECOMMENDATION_LIBRARY_SHARE")
    return _safe_score(raw, DEFAULT_RECOMMENDATION_LIBRARY_SHARE) if raw is not None else DEFAULT_RECOMMENDATION_LIBRARY_SHARE


def recommendation_external_share() -> float:
    raw = os.getenv("RECOMMENDATION_EXTERNAL_SHARE")
    return _safe_score(raw, DEFAULT_RECOMMENDATION_EXTERNAL_SHARE) if raw is not None else DEFAULT_RECOMMENDATION_EXTERNAL_SHARE


def _row_list(value: object) -> list:
    if value is None:
        return []
    if isinstance(value, float) and pd.isna(value):
        return []
    if isinstance(value, list):
        return value
    if isinstance(value, tuple):
        return list(value)
    return []


def _series_key(value: object) -> str:
    import re

    return re.sub(r"[^a-z0-9]+", " ", str(value or "").casefold()).strip()


def is_in_library_row(row: pd.Series) -> bool:
    return True if pd.isna(row.get("In Library")) else bool(row.get("In Library"))


def close_call_compare(left: tuple[object, pd.Series], right: tuple[object, pd.Series]) -> int:
    _left_index, left_row = left
    _right_index, right_row = right
    left_score = _safe_score(left_row.get("score"))
    right_score = _safe_score(right_row.get("score"))
    if abs(left_score - right_score) <= LIBRARY_CLOSE_CALL_MARGIN:
        left_library = is_in_library_row(left_row)
        right_library = is_in_library_row(right_row)
        if left_library != right_library:
            return -1 if left_library else 1
    if left_score != right_score:
        return -1 if left_score > right_score else 1
    return 0


def sort_library_close_calls(ranked: pd.DataFrame) -> pd.DataFrame:
    if ranked.empty:
        return ranked
    ordered = sorted(list(ranked.iterrows()), key=cmp_to_key(close_call_compare))
    return ranked.loc[[index for index, _row in ordered]].copy()


def primary_genre_key(row: pd.Series) -> str | None:
    for value in [*_row_list(row.get("Genres")), *_row_list(row.get("Subjects"))]:
        key = str(value or "").strip().casefold()
        if key:
            return key
    return None


def series_limit_key(row: pd.Series) -> str | None:
    canonical = _series_key(row.get("Canonical Series Identity"))
    if canonical:
        return canonical
    key = _series_key(row.get("Series Name"))
    return key or None


def cluster_limit_key(row: pd.Series) -> str | None:
    for key in ("Discovery Cluster ID", "discovery_cluster_id"):
        value = str(row.get(key) or "").strip().casefold()
        if value:
            return value
    return primary_genre_key(row)


def author_limit_key(row: pd.Series) -> str:
    return str(row.get("Authors", row.get("author", "")) or "").strip().casefold()


def _distinct_author_capacity(
    rows: list[tuple[object, pd.Series]],
    selected_set: set[object],
    *,
    score_threshold: float,
    existing_authors: set[str],
) -> int:
    authors: set[str] = set()
    for index, row in rows:
        if index in selected_set:
            continue
        if _safe_score(row.get("score")) < score_threshold:
            continue
        author = author_limit_key(row)
        if author and author not in existing_authors:
            authors.add(author)
    return len(authors)


def passes_diversity_caps(
    row: pd.Series,
    *,
    author_counts: Counter[str],
    author_clusters: dict[str, set[str]],
    genre_counts: Counter[str],
    series_counts: Counter[str],
    allow_second_author_title: bool = False,
    score_threshold: float | None = None,
    enforce_genre_cap: bool = True,
    enforce_series_cap: bool = True,
) -> bool:
    author = author_limit_key(row)
    if author and author_counts[author] >= MAX_SAME_AUTHOR_RESULTS:
        return False
    if author and author_counts[author] >= DEFAULT_MAX_SAME_AUTHOR_RESULTS:
        threshold = second_author_title_score_threshold() if score_threshold is None else score_threshold
        different_cluster = bool(cluster_limit_key(row) and cluster_limit_key(row) not in author_clusters.get(author, set()))
        if not (_safe_score(row.get("score")) >= threshold and (allow_second_author_title or different_cluster)):
            return False
    if enforce_genre_cap:
        genre = primary_genre_key(row)
        if genre and genre_counts[genre] >= MAX_SAME_NARROW_GENRE_RESULTS:
            return False
    if enforce_series_cap:
        series = series_limit_key(row)
        if series and series_counts[series] >= MAX_SAME_SERIES_RESULTS:
            return False
    return True


def record_diversity(
    row: pd.Series,
    *,
    author_counts: Counter[str],
    author_clusters: dict[str, set[str]],
    genre_counts: Counter[str],
    series_counts: Counter[str],
) -> None:
    author = author_limit_key(row)
    if author:
        author_counts[author] += 1
        cluster = cluster_limit_key(row)
        if cluster:
            author_clusters.setdefault(author, set()).add(cluster)
    genre = primary_genre_key(row)
    if genre:
        genre_counts[genre] += 1
    series = series_limit_key(row)
    if series:
        series_counts[series] += 1


def strong_external_mask(ranked: pd.DataFrame) -> pd.Series:
    if ranked.empty or "In Library" not in ranked.columns:
        return pd.Series(False, index=ranked.index)
    best_score = float(ranked["score"].max()) if "score" in ranked.columns else 0.0
    threshold = max(0.0, best_score - EXTERNAL_RELATIVE_SCORE_MARGIN)
    in_library = ranked["In Library"].map(lambda value: True if pd.isna(value) else bool(value))
    score = pd.to_numeric(ranked["score"], errors="coerce").fillna(0.0)
    return (~in_library) & ((score >= 0.55) | (score >= threshold))


def broad_external_mask(ranked: pd.DataFrame) -> pd.Series:
    if ranked.empty or "In Library" not in ranked.columns or "Exploration Mode" not in ranked.columns:
        return pd.Series(False, index=ranked.index)
    in_library = ranked["In Library"].map(lambda value: True if pd.isna(value) else bool(value))
    has_exploration_mode = ranked["Exploration Mode"].map(lambda value: bool(str(value or "").strip()))
    return (~in_library) & has_exploration_mode


def select_with_diversity(
    rows: list[tuple[object, pd.Series]],
    *,
    top_n: int,
    selected_indexes: list[object] | None = None,
) -> list[object]:
    selected = list(selected_indexes or [])
    selected_set = set(selected)
    author_counts: Counter[str] = Counter()
    author_clusters: dict[str, set[str]] = {}
    genre_counts: Counter[str] = Counter()
    series_counts: Counter[str] = Counter()
    for index, row in rows:
        if index in selected_set:
            record_diversity(row, author_counts=author_counts, author_clusters=author_clusters, genre_counts=genre_counts, series_counts=series_counts)
    for index, row in rows:
        if len(selected) >= top_n:
            break
        if index in selected_set:
            continue
        threshold = second_author_title_score_threshold()
        distinct_author_capacity = _distinct_author_capacity(
            rows,
            selected_set,
            score_threshold=threshold,
            existing_authors=set(author_counts),
        )
        allow_second_for_shortfall = len(selected) + distinct_author_capacity < top_n
        if not passes_diversity_caps(
            row,
            author_counts=author_counts,
            author_clusters=author_clusters,
            genre_counts=genre_counts,
            series_counts=series_counts,
            allow_second_author_title=allow_second_for_shortfall,
        ):
            continue
        selected.append(index)
        selected_set.add(index)
        record_diversity(row, author_counts=author_counts, author_clusters=author_clusters, genre_counts=genre_counts, series_counts=series_counts)
    if len(selected) < top_n:
        for index, row in rows:
            if len(selected) >= top_n:
                break
            if index in selected_set:
                continue
            threshold = second_author_title_score_threshold()
            distinct_author_capacity = _distinct_author_capacity(
                rows,
                selected_set,
                score_threshold=threshold,
                existing_authors=set(author_counts),
            )
            allow_second_for_shortfall = len(selected) + distinct_author_capacity < top_n
            if not passes_diversity_caps(
                row,
                author_counts=author_counts,
                author_clusters=author_clusters,
                genre_counts=genre_counts,
                series_counts=series_counts,
                allow_second_author_title=allow_second_for_shortfall,
                enforce_genre_cap=False,
                enforce_series_cap=True,
            ):
                continue
            selected.append(index)
            selected_set.add(index)
            record_diversity(row, author_counts=author_counts, author_clusters=author_clusters, genre_counts=genre_counts, series_counts=series_counts)
    return selected


def blend_library_and_discovery(ranked: pd.DataFrame, top_n: int, style: str) -> pd.DataFrame:
    if ranked.empty or "In Library" not in ranked.columns:
        return ranked.head(top_n)
    ranked = sort_library_close_calls(ranked)
    rows = list(ranked.iterrows())
    strong_external = ranked[strong_external_mask(ranked)]
    if style == "external_first":
        target_min_external = max(1, round(top_n * recommendation_external_share()))
    elif top_n >= 10:
        target_min_external = 5 if style == "discovery" else MIN_EXTERNAL_RESULTS_FOR_TEN if style == "popular" else 4
    else:
        target_min_external = max(1, round(top_n * 0.3)) if style == "discovery" else 0
    target_max_external = top_n if style == "external_first" else MAX_EXTERNAL_RESULTS_FOR_TEN if top_n >= 10 else max(1, round(top_n * 0.7))
    selected: list[object] = []

    if style == "external_first":
        broad_external = ranked[strong_external_mask(ranked) & broad_external_mask(ranked)]
        if not broad_external.empty:
            broad_rows = [(index, ranked.loc[index]) for index in broad_external.index]
            selected = select_with_diversity(
                broad_rows,
                top_n=min(max(1, round(target_min_external * 0.35)), top_n, len(broad_rows)),
            )

    if len(strong_external) >= target_min_external:
        external_rows = [(index, ranked.loc[index]) for index in strong_external.index]
        selected = select_with_diversity(
            external_rows,
            top_n=min(target_min_external, top_n, target_max_external),
            selected_indexes=selected,
        )

    selected = select_with_diversity(rows, top_n=top_n, selected_indexes=selected)
    selected_df = ranked.loc[selected].copy()

    if len(selected_df) > top_n:
        selected_df = selected_df.head(top_n)
    if not selected_df.empty:
        selected_df = sort_library_close_calls(selected_df)
    external_count = int((~selected_df["In Library"].map(lambda value: True if pd.isna(value) else bool(value))).sum())
    if external_count > target_max_external:
        external_indexes = [
            index
            for index, row in selected_df.iterrows()
            if not is_in_library_row(row)
        ]
        drop_indexes = external_indexes[target_max_external:]
        selected_df = selected_df.drop(index=drop_indexes)
        selected_df = ranked.loc[select_with_diversity(rows, top_n=top_n, selected_indexes=list(selected_df.index))]
    return selected_df.head(top_n)
