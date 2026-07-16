import logging
import time
from typing import Any, cast

import numpy as np
import pandas as pd

from backend.services.recommendation_signals import (
    build_feature_cache,
    meaningful_similar_feature_matches,
    primary_language_from_features,
)
from backend.services.metadata_specificity import metadata_specificity
from backend.services.recommendation_debug import rec_debug
from backend.services.status import normalize_status

logger = logging.getLogger(__name__)
DEBUG_ANNA_TITLE = "anna karenina"
SCORE_ANCHOR_LIMIT = 5


def _resolve_column(df, candidates):
    for col in candidates:
        if col in df.columns:
            return col
    return None


def _numeric_series(df: pd.DataFrame, names: list[str], default: float = 0.0) -> pd.Series:
    for name in names:
        if name in df.columns:
            values = cast(pd.Series, pd.to_numeric(df[name], errors="coerce"))
            return values.fillna(default)
    return pd.Series(default, index=df.index, dtype=float)


def _numeric_scalar(value: Any) -> float | None:
    parsed = pd.to_numeric(value, errors="coerce")
    if isinstance(parsed, pd.Series | pd.Index | np.ndarray):
        return None
    if bool(pd.isna(parsed)):
        return None
    return float(cast(Any, parsed))


def _date_series(df: pd.DataFrame, names: list[str]) -> pd.Series:
    for name in names:
        if name in df.columns:
            return pd.to_datetime(df[name], errors="coerce")
    return pd.Series(pd.NaT, index=df.index)


def _recency_weight_from_date(value) -> float:
    parsed = pd.to_datetime(value, errors="coerce")
    if pd.isna(parsed):
        return 0.75

    today = pd.Timestamp.utcnow().tz_localize(None)
    parsed = parsed.tz_localize(None) if getattr(parsed, "tzinfo", None) else parsed
    days = max(0, (today - parsed).days)

    # Today/recent reads matter more, then decay slowly over ~1 year.
    return float(max(0.35, 1.0 - (days / 365)))


def _rating_influence(value) -> float:
    rating = pd.to_numeric(value, errors="coerce")

    if isinstance(rating, pd.Series | pd.Index | np.ndarray):
        return 1.0
    if bool(pd.isna(rating)):
        return 1.0

    rating = float(cast(Any, rating))

    if rating >= 4:
        return 1.0
    if rating >= 3:
        return 0.85
    if rating >= 2:
        return 0.55
    return 0.35


def _explicit_preference_weight(row: pd.Series, status_col: str) -> float:
    status = normalize_status(row.get(status_col))
    raw_rating = row.get("Star Rating", row.get("star_rating", row.get("rating")))
    rating = _numeric_scalar(raw_rating)

    if status == "completed":
        if rating is None:
            return 0.18
        if rating >= 5.0:
            return 1.35
        if rating >= 4.5:
            return 1.15
        if rating >= 4.0:
            return 0.95
        if rating >= 3.5:
            return 0.45
        if rating >= 3.0:
            return 0.05
        if rating >= 2.0:
            return -0.55
        return -0.9

    if status == "reading":
        if rating is not None and rating < 3.0:
            return -0.25
        return 0.55 if rating is None else min(0.8, max(0.2, rating / 5))

    if status == "not_started":
        return 0.22

    if status == "dnf":
        if rating is not None and rating < 2.0:
            return -0.75
        if rating is not None and rating < 3.0:
            return -0.55
        return -0.35

    return 0.0


def score_read_books(df, rating_weight=0.7, recency_weight=0.3):
    status_col = _resolve_column(df, ["read_status", "Read Status"])
    if status_col is None:
        return df.iloc[0:0].copy()

    read_df = df[df[status_col].apply(lambda value: normalize_status(value) == "completed")].copy()

    if "rating_norm" not in read_df.columns:
        read_df["rating_norm"] = 0.5
    if "recency_norm" not in read_df.columns:
        read_df["recency_norm"] = 0.5

    read_df["score"] = (
        rating_weight * read_df["rating_norm"]
        + recency_weight * read_df["recency_norm"]
    ).clip(0, 1)

    return read_df.sort_values(by="score", ascending=False)


def score_tbr_books(df, randomness_strength=0.05, diverse_authors=True):
    total_started = time.perf_counter()
    timings: dict[str, float] = {}
    phase_started = time.perf_counter()

    status_col = _resolve_column(df, ["read_status", "Read Status"])
    author_col = _resolve_column(df, ["author", "Authors"])
    title_col = _resolve_column(df, ["title", "Title"])

    if status_col is None:
        return df.iloc[0:0].copy()

    if author_col is None:
        author_col = "author"
        df = df.copy()
        df[author_col] = "unknown"

    if title_col is None:
        title_col = "title"
        df = df.copy()
        df[title_col] = ""

    if "rating_norm" not in df.columns:
        df = df.copy()
        df["rating_norm"] = 0.5

    status_series = df[status_col].astype(str).str.strip().str.lower()
    completed_mask = df[status_col].apply(lambda value: normalize_status(value) == "completed")

    pages_series = _numeric_series(df, ["Pages Read", "pages_read"], 0)
    progress_series = _numeric_series(df, ["Progress (%)", "progress_percent"], 0)
    title_series = df[title_col].astype(str).str.strip()

    tbr_mask = (
        status_series.isin(["to-read", "not_started"])
        & (pages_series <= 0)
        & (progress_series <= 0)
        & (title_series != "")
    )

    evidence_mask = df[status_col].apply(
        lambda value: normalize_status(value) in {"completed", "reading", "dnf"}
    )
    read_df = df[evidence_mask].copy()
    tbr_df = df[tbr_mask].copy()
    tbr_df["_source_index"] = tbr_df.index
    if not read_df.empty:
        read_df["_preference_weight"] = read_df.apply(
            lambda row: _explicit_preference_weight(row, status_col),
            axis=1,
        )
        read_df = read_df[read_df["_preference_weight"] != 0].copy()

    timings["candidate_selection"] = (time.perf_counter() - phase_started) * 1000

    if tbr_df.empty:
        empty = tbr_df.iloc[0:0].copy()
        empty["score"] = pd.Series(dtype=float)
        rec_debug("tbr_candidates_scored=0")
        return empty

    tbr_df = tbr_df.drop_duplicates(subset=[title_col, author_col])

    if read_df.empty:
        tbr_df["author_score"] = 0.5
        tbr_df["score"] = 0.5
        tbr_df["_similar_matches"] = [[] for _ in range(len(tbr_df))]
        tbr_df["_signal_scores"] = [{} for _ in range(len(tbr_df))]
        tbr_df["_score_anchors"] = [[] for _ in range(len(tbr_df))]
        rec_debug("tbr_candidates_scored=%s", len(tbr_df))
        return tbr_df

    phase_started = time.perf_counter()

    weighted_authors = read_df.copy()
    weighted_authors["_author_component"] = weighted_authors["_preference_weight"].clip(-1.0, 1.35)
    author_pref = weighted_authors.groupby(author_col)["_author_component"].mean().reset_index()
    author_pref["_author_component"] = ((author_pref["_author_component"] + 1.0) / 2.35).clip(0, 1)
    author_pref.rename(columns={"_author_component": "author_score"}, inplace=True)

    tbr_df = tbr_df.merge(author_pref, on=author_col, how="left")
    tbr_df["author_score"] = tbr_df["author_score"].fillna(0.5)

    timings["author_affinity"] = (time.perf_counter() - phase_started) * 1000

    noise = np.random.uniform(
        -randomness_strength,
        randomness_strength,
        len(tbr_df),
    )

    phase_started = time.perf_counter()

    feature_cache = build_feature_cache(
        pd.concat([read_df, df.loc[tbr_df["_source_index"]]], axis=0)
    )
    read_features = [
        feature_cache[index]
        for index in read_df.index
        if index in feature_cache
    ]

    primary_language = primary_language_from_features(read_features)

    rec_debug(
        "read_books_for_scoring=%s anna_in_anchor_set=%s read_titles=%s",
        len(read_features),
        any(feature.title.strip().lower() == DEBUG_ANNA_TITLE for feature in read_features),
        [feature.title for feature in read_features],
    )

    timings["metadata_precompute"] = (time.perf_counter() - phase_started) * 1000

    scores_by_index = {}
    similar_matches_by_index = {}
    score_anchors_by_index: dict[object, list] = {}

    genre_ms = 0.0
    subject_ms = 0.0
    ranking_started = time.perf_counter()

    positive_read_genres: set[str] = set()
    positive_read_subjects: set[str] = set()
    positive_read_authors: set[str] = set()
    positive_read_keywords: set[str] = set()
    negative_read_genres: set[str] = set()
    negative_read_subjects: set[str] = set()
    negative_read_authors: set[str] = set()
    negative_read_keywords: set[str] = set()
    read_pages = []

    preference_weight_by_index = {
        index: float(read_df.at[index, "_preference_weight"])
        for index in read_df.index
        if "_preference_weight" in read_df.columns
    }

    for features in read_features:
        weight = preference_weight_by_index.get(features.index, 0.0)
        if weight >= 0:
            positive_read_genres.update(features.genres)
            positive_read_subjects.update(features.subjects)
            if features.author and features.author != "unknown":
                positive_read_authors.add(features.author)
            positive_read_keywords.update(features.keywords)
        else:
            negative_read_genres.update(features.genres)
            negative_read_subjects.update(features.subjects)
            if features.author and features.author != "unknown":
                negative_read_authors.add(features.author)
            negative_read_keywords.update(features.keywords)

    for _, row in read_df.iterrows():
        pages = _numeric_scalar(row.get("Total Pages", row.get("total_pages")))
        if pages is not None and pages > 0:
            read_pages.append(pages)

    for _, row in tbr_df.iterrows():
        row_index = row.get("_source_index", row.name)
        candidate_features = feature_cache.get(row_index)

        if candidate_features is None:
            continue

        match_started = time.perf_counter()

        similar = meaningful_similar_feature_matches(
            candidate_features,
            read_features,
            limit=max(25, len(read_features)),
        )

        match_elapsed = (time.perf_counter() - match_started) * 1000
        genre_ms += match_elapsed * 0.5
        subject_ms += match_elapsed * 0.5

        similar_matches_by_index[row.name] = similar

        pages_value = row.get("Total Pages", row.get("total_pages"))
        candidate_pages = _numeric_scalar(pages_value)

        genre_overlap = candidate_features.genres & positive_read_genres
        subject_overlap = candidate_features.subjects & positive_read_subjects
        keyword_overlap = candidate_features.keywords & positive_read_keywords
        same_author = candidate_features.author in positive_read_authors
        negative_genre_overlap = candidate_features.genres & negative_read_genres
        negative_subject_overlap = candidate_features.subjects & negative_read_subjects
        negative_keyword_overlap = candidate_features.keywords & negative_read_keywords
        negative_same_author = candidate_features.author in negative_read_authors

        genre_score = min(1.0, sum(metadata_specificity(value) for value in genre_overlap)) if genre_overlap else 0.0
        subject_score = min(1.0, sum(metadata_specificity(value) for value in subject_overlap)) if subject_overlap else 0.0
        author_score = 1.0 if same_author else 0.0
        description_score = min(1.0, len(keyword_overlap) / 5) if keyword_overlap else 0.0

        length_score = 0.0
        if read_pages and candidate_pages is not None and candidate_pages > 0:
            median_pages = float(np.median(read_pages))
            distance = abs(candidate_pages - median_pages)
            length_score = max(0.0, 1.0 - (distance / max(median_pages, 1.0)))

        candidate_language = candidate_features.language
        if (
            primary_language
            and candidate_language
            and candidate_language != primary_language
            and not similar
        ):
            length_score *= 0.5

        long_term_preference_score = (
            genre_score * 0.35
            + subject_score * 0.22
            + author_score * 0.13
            + description_score * 0.10
            + length_score * 0.08
        )
        negative_preference_penalty = min(
            0.35,
            (0.08 * len(negative_genre_overlap))
            + (0.06 * len(negative_subject_overlap))
            + (0.12 if negative_same_author else 0.0)
            + (0.03 * min(3, len(negative_keyword_overlap)))
        )

        similar_preference_score = 0.0
        rating_affinity_score = 0.0
        current_mood_score = 0.0
        status_pattern_score = 0.0
        score_contributors: list[tuple[float, object, object]] = []

        for index, similarity, rating_norm in similar:
            if index not in read_df.index:
                continue
            if index == row_index:
                continue

            source_row = read_df.loc[index]
            raw_rating = source_row.get("Star Rating", source_row.get("star_rating"))
            preference_weight = float(source_row.get("_preference_weight") or 0.0)
            if preference_weight <= 0:
                continue
            rating_weight = max(0.0, preference_weight)

            finished_at = source_row.get(
                "End Date",
                source_row.get("end_date", source_row.get("Last Date Read", None)),
            )
            recency_weight = _recency_weight_from_date(finished_at)
            source_status = normalize_status(source_row.get(status_col))

            overlap_strength = (
                min(1.0, sum(metadata_specificity(value) for value in similarity.shared_genres)) * 0.40
                + min(1.0, sum(metadata_specificity(value) for value in similarity.shared_subjects)) * 0.30
                + (0.20 if similarity.same_author else 0.0)
                + (0.10 if similarity.keyword_overlap else 0.0)
            )

            recency_component = 0.7 + (0.3 * recency_weight)
            contribution = overlap_strength * rating_weight * recency_component
            similar_preference_score = max(similar_preference_score, contribution)
            rating_affinity_score = max(rating_affinity_score, min(1.0, contribution))
            if source_status == "reading":
                current_mood_score = max(current_mood_score, overlap_strength * 0.45)
            elif source_status == "not_started":
                status_pattern_score = max(status_pattern_score, overlap_strength * 0.25)
            if contribution > 0:
                score_contributors.append((contribution, index, similarity))

        score_contributors.sort(key=lambda item: item[0], reverse=True)
        score_anchors_by_index[row.name] = [
            (index, contribution, similarity)
            for contribution, index, similarity in score_contributors[:SCORE_ANCHOR_LIMIT]
        ]

        diversity_bonus = 0.02 if not same_author and len(genre_overlap) <= 1 else 0.0
        candidate_similarity = min(1.0, similar_preference_score)
        score = (
            candidate_similarity * 0.35
            + long_term_preference_score * 0.35
            + rating_affinity_score * 0.25
            + current_mood_score * 0.12
            + status_pattern_score * 0.08
            + diversity_bonus
            - negative_preference_penalty
        )

        position = len(scores_by_index)
        noise_value = noise[position] if position < len(noise) else 0.0

        scores_by_index[row.name] = score + noise_value

        similar_strength = min(1.0, len(similar) / 3) if similar else 0.0
        similar_matches_by_index[(row.name, "_signals")] = {
            "genre_fit": max(genre_score, subject_score),
            "mood_match": max(current_mood_score, subject_score, description_score),
            "reader_similarity": max(similar_strength, similar_preference_score),
            "author_affinity": author_score,
            "candidate_similarity": candidate_similarity,
            "long_term_preference_score": long_term_preference_score,
            "rating_affinity_score": rating_affinity_score,
            "current_mood_score": current_mood_score,
            "status_pattern_score": status_pattern_score,
            "diversity_bonus": diversity_bonus,
            "negative_preference_penalty": negative_preference_penalty,
        }

    if not scores_by_index:
        fallback = tbr_df.copy()

        if "recency_norm" not in fallback.columns:
            fallback["recency_norm"] = 0.5

        fallback["score"] = (
            0.55 * fallback["author_score"].fillna(0.5)
            + 0.25 * fallback["recency_norm"].fillna(0.5)
            + 0.20 * fallback.get("rating_norm", 0.5)
        ).clip(0, 1)

        fallback["_similar_matches"] = [[] for _ in range(len(fallback))]
        fallback["_score_anchors"] = [[] for _ in range(len(fallback))]
        fallback["_signal_scores"] = [
            {
                "genre_fit": None,
                "mood_match": None,
                "reader_similarity": None,
                "author_affinity": float(max(0.0, min(1.0, value))) if value > 0.5 else None,
            }
            for value in fallback["author_score"].fillna(0.5)
        ]

        fallback = fallback.sort_values(by="score", ascending=False)

        if diverse_authors:
            diverse = fallback.drop_duplicates(subset=[author_col])
            remaining = fallback.loc[~fallback.index.isin(diverse.index)]
            fallback = pd.concat([diverse, remaining])

        rec_debug("tbr_candidates_scored=%s", len(fallback))
        return fallback

    tbr_df = tbr_df.loc[list(scores_by_index.keys())].copy()
    tbr_df["score"] = tbr_df.index.map(scores_by_index)
    tbr_df["_score_anchors"] = tbr_df.index.map(
        lambda index: score_anchors_by_index.get(index, [])
    )
    tbr_df["_similar_matches"] = tbr_df.index.map(
        lambda index: similar_matches_by_index.get(index, [])
    )
    tbr_df["_signal_scores"] = tbr_df.index.map(
        lambda index: similar_matches_by_index.get((index, "_signals"), {})
    )

    timings["genre_matching"] = genre_ms
    timings["subject_matching"] = subject_ms

    tbr_df["score"] = tbr_df["score"].clip(0.001, 1)
    tbr_df = tbr_df.sort_values(by="score", ascending=False)

    if diverse_authors:
        diverse = tbr_df.drop_duplicates(subset=[author_col])
        remaining = tbr_df.loc[~tbr_df.index.isin(diverse.index)]
        tbr_df = pd.concat([diverse, remaining])

    timings["sorting_ranking"] = (time.perf_counter() - ranking_started) * 1000
    timings["total"] = (time.perf_counter() - total_started) * 1000

    rec_debug("tbr_candidates_scored=%s", len(tbr_df))
    logger.info(
        "recommendation_score_timing candidate_selection=%.2fms author_affinity=%.2fms "
        "metadata_precompute=%.2fms genre_matching=%.2fms subject_matching=%.2fms "
        "sorting_ranking=%.2fms total=%.2fms external_requests=0 metadata_enrichment=0 background_backfill=0",
        timings.get("candidate_selection", 0.0),
        timings.get("author_affinity", 0.0),
        timings.get("metadata_precompute", 0.0),
        timings.get("genre_matching", 0.0),
        timings.get("subject_matching", 0.0),
        timings.get("sorting_ranking", 0.0),
        timings.get("total", 0.0),
    )

    return tbr_df


def recommend_one(tbr_ranked):
    if len(tbr_ranked) == 0:
        return None

    top_slice = tbr_ranked.head(10)

    if "score" not in top_slice.columns:
        return top_slice.sample(1)

    weights = top_slice["score"].clip(lower=0.01)
    return top_slice.sample(1, weights=weights)
