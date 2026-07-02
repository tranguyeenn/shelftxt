import numpy as np
import pandas as pd
import logging
import time

from backend.services.recommendation_signals import (
    build_feature_cache,
    meaningful_similar_feature_matches,
    primary_language_from_features,
    read_dataframe,
)

logger = logging.getLogger(__name__)

def _resolve_column(df, candidates):
    for col in candidates:
        if col in df.columns:
            return col
    return None


def _numeric_series(df: pd.DataFrame, names: list[str], default: float = 0.0) -> pd.Series:
    for name in names:
        if name in df.columns:
            return pd.to_numeric(df[name], errors="coerce").fillna(default)
    return pd.Series(default, index=df.index, dtype=float)


def score_read_books(df, rating_weight=0.7, recency_weight=0.3):
    status_col = _resolve_column(df, ["read_status", "Read Status"])
    if status_col is None:
        return df.iloc[0:0].copy()

    read_df = df[df[status_col].astype(str).str.strip().str.lower() == "read"].copy()
    if "rating_norm" not in read_df.columns:
        read_df["rating_norm"] = 0.5
    if "recency_norm" not in read_df.columns:
        read_df["recency_norm"] = 0.5

    read_df["score"] = (
        rating_weight * read_df["rating_norm"] +
        recency_weight * read_df["recency_norm"]
    )

    read_df["score"] = read_df["score"].clip(0, 1)

    read_df = read_df.sort_values(
        by="score",
        ascending=False
    )

    return read_df

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
    completed_mask = status_series.isin(["read", "completed"])
    pages_series = _numeric_series(df, ["Pages Read", "pages_read"], 0)
    progress_series = _numeric_series(df, ["Progress (%)", "progress_percent"], 0)
    title_series = df[title_col].astype(str).str.strip()
    tbr_mask = status_series.isin(["to-read", "not_started"]) & (pages_series <= 0) & (progress_series <= 0) & (title_series != "")
    completed_all_df = df[completed_mask].copy()
    rating_values = completed_all_df.get("Star Rating", completed_all_df.get("star_rating"))
    if rating_values is None:
        rating_values = pd.Series(index=completed_all_df.index, dtype=float)
    raw_ratings = pd.to_numeric(rating_values, errors="coerce")
    liked_df = completed_all_df[raw_ratings >= 4].copy()
    if len(liked_df) < 3:
        liked_df = completed_all_df[raw_ratings >= 3.5].copy()
    read_df = liked_df
    tbr_df = df[tbr_mask].copy()
    tbr_df["_source_index"] = tbr_df.index
    timings["candidate_selection"] = (time.perf_counter() - phase_started) * 1000

    if tbr_df.empty:
        empty = tbr_df.iloc[0:0].copy()
        empty["score"] = pd.Series(dtype=float)
        return empty

    # Remove duplicate books
    tbr_df = tbr_df.drop_duplicates(
        subset=[title_col, author_col]
    )

    if read_df.empty:
        tbr_df["author_score"] = 0.5
        tbr_df["score"] = 0.5
        tbr_df["_similar_matches"] = [[] for _ in range(len(tbr_df))]
        tbr_df["_signal_scores"] = [{} for _ in range(len(tbr_df))]
        return tbr_df

    phase_started = time.perf_counter()
    author_pref = (
        read_df
        .groupby(author_col)["rating_norm"]
        .mean()
        .reset_index()
    )

    author_pref.rename(
        columns={"rating_norm": "author_score"},
        inplace=True
    )

    tbr_df = tbr_df.merge(
        author_pref,
        on=author_col,
        how="left"
    )

    tbr_df["author_score"] = tbr_df["author_score"].fillna(0.5)
    timings["author_affinity"] = (time.perf_counter() - phase_started) * 1000

    noise = np.random.uniform(
        -randomness_strength,
        randomness_strength,
        len(tbr_df)
    )

    completed_df = read_df

    phase_started = time.perf_counter()
    feature_cache = build_feature_cache(pd.concat([completed_df, df.loc[tbr_df["_source_index"]]], axis=0))
    read_features = [feature_cache[index] for index in completed_df.index if index in feature_cache]
    primary_language = primary_language_from_features(read_features)
    timings["metadata_precompute"] = (time.perf_counter() - phase_started) * 1000

    scores_by_index = {}
    similar_matches_by_index = {}
    genre_ms = 0.0
    subject_ms = 0.0
    ranking_started = time.perf_counter()
    liked_genres: set[str] = set()
    liked_subjects: set[str] = set()
    liked_authors: set[str] = set()
    liked_keywords: set[str] = set()
    liked_pages = []
    for features in read_features:
        liked_genres.update(features.genres)
        liked_subjects.update(features.subjects)
        if features.author and features.author != "unknown":
            liked_authors.add(features.author)
        liked_keywords.update(features.keywords)
    for _, row in read_df.iterrows():
        pages = pd.to_numeric(row.get("Total Pages", row.get("total_pages")), errors="coerce")
        if not pd.isna(pages) and float(pages) > 0:
            liked_pages.append(float(pages))

    for _, row in tbr_df.iterrows():
        row_index = row.get("_source_index", row.name)
        candidate_features = feature_cache.get(row_index)
        if candidate_features is None:
            continue
        match_started = time.perf_counter()
        similar = meaningful_similar_feature_matches(candidate_features, read_features, limit=5)
        match_elapsed = (time.perf_counter() - match_started) * 1000
        genre_ms += match_elapsed * 0.5
        subject_ms += match_elapsed * 0.5
        similar_matches_by_index[row.name] = similar
        pages_value = row.get("Total Pages", row.get("total_pages"))
        candidate_pages = pd.to_numeric(pages_value, errors="coerce")

        genre_overlap = candidate_features.genres & liked_genres
        subject_overlap = candidate_features.subjects & liked_subjects
        keyword_overlap = candidate_features.keywords & liked_keywords
        same_author = candidate_features.author in liked_authors

        genre_score = min(1.0, len(genre_overlap) / 2) if genre_overlap else 0.0
        subject_score = min(1.0, len(subject_overlap) / 3) if subject_overlap else 0.0
        author_score = 1.0 if same_author else 0.0
        description_score = min(1.0, len(keyword_overlap) / 5) if keyword_overlap else 0.0

        length_score = 0.0
        if liked_pages and not pd.isna(candidate_pages) and float(candidate_pages) > 0:
            median_pages = float(np.median(liked_pages))
            distance = abs(float(candidate_pages) - median_pages)
            length_score = max(0.0, 1.0 - (distance / max(median_pages, 1.0)))

        candidate_language = candidate_features.language
        if (
            primary_language
            and candidate_language
            and candidate_language != primary_language
            and not similar
        ):
            length_score *= 0.5

        score = (
            genre_score * 0.40
            + subject_score * 0.25
            + author_score * 0.15
            + description_score * 0.10
            + length_score * 0.10
        )

        position = len(scores_by_index)
        noise_value = noise[position] if position < len(noise) else 0.0
        scores_by_index[row.name] = score + noise_value
        similar_strength = min(1.0, len(similar) / 3) if similar else 0.0
        similar_matches_by_index[(row.name, "_signals")] = {
            "genre_fit": max(genre_score, subject_score),
            "mood_match": max(subject_score, description_score),
            "reader_similarity": similar_strength,
            "author_affinity": author_score,
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
        return fallback

    tbr_df = tbr_df.loc[list(scores_by_index.keys())].copy()
    tbr_df["score"] = tbr_df.index.map(scores_by_index)
    tbr_df["_similar_matches"] = tbr_df.index.map(lambda index: similar_matches_by_index.get(index, []))
    tbr_df["_signal_scores"] = tbr_df.index.map(
        lambda index: similar_matches_by_index.get((index, "_signals"), {})
    )
    timings["genre_matching"] = genre_ms
    timings["subject_matching"] = subject_ms

    # Keep score in clean range
    tbr_df["score"] = tbr_df["score"].clip(0, 1)

    tbr_df = tbr_df.sort_values(
        by="score",
        ascending=False
    )

    # Optional diversity: only 1 book per author
    if diverse_authors:
        diverse = tbr_df.drop_duplicates(subset=[author_col])
        remaining = tbr_df.loc[~tbr_df.index.isin(diverse.index)]
        tbr_df = pd.concat([diverse, remaining])

    timings["sorting_ranking"] = (time.perf_counter() - ranking_started) * 1000
    timings["total"] = (time.perf_counter() - total_started) * 1000
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

    # Pick randomly from top 5
    top_slice = tbr_ranked.head(5)
    recommendation = top_slice.sample(1)

    return recommendation
