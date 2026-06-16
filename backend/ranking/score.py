import numpy as np
import pandas as pd

from backend.services.recommendation_signals import (
    infer_language,
    meaningful_similar_books,
    read_dataframe,
    row_author,
    row_genres,
    row_subjects,
    user_primary_language,
)

def _resolve_column(df, candidates):
    for col in candidates:
        if col in df.columns:
            return col
    return None


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
    read_df = df[status_series == "read"].copy()
    tbr_df = df[status_series == "to-read"].copy()

    # Remove duplicate books
    tbr_df = tbr_df.drop_duplicates(
        subset=[title_col, author_col]
    )

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

    global_avg = read_df["rating_norm"].mean() if not read_df.empty else 0.5

    tbr_df["author_score"] = tbr_df["author_score"].fillna(0.5)

    noise = np.random.uniform(
        -randomness_strength,
        randomness_strength,
        len(tbr_df)
    )

    completed_df = read_dataframe(df)
    primary_language = user_primary_language(completed_df)

    scores = []
    for idx, (_, row) in enumerate(tbr_df.iterrows()):
        similar = meaningful_similar_books(row, completed_df, limit=5)
        author = row_author(row)
        has_author = bool(author and author != "unknown")
        pages_value = row.get("Total Pages", row.get("total_pages"))
        has_pages = pages_value is not None and not pd.isna(pages_value)
        has_genre_metadata = bool(row_genres(row) or row_subjects(row))
        in_progress = float(row.get("Pages Read", row.get("pages_read", 0)) or 0) > 0

        same_author = any(similarity.same_author for _, similarity in similar)
        genre_hits = sum(len(similarity.shared_genres) for _, similarity in similar)
        subject_hits = sum(len(similarity.shared_subjects) for _, similarity in similar)
        keyword_hits = sum(len(similarity.keyword_overlap) for _, similarity in similar)
        high_rating_supported = any(
            float(similar_row.get("rating_norm", 0.0) or 0.0) >= 0.8
            for similar_row, _ in similar
        )

        score = 0.57
        if same_author:
            score += 0.4 * float(row.get("author_score", 0.5) or 0.5)
        elif similar:
            score += 0.08 * min(1.0, global_avg)

        score += min(0.18, 0.05 * genre_hits)
        score += min(0.14, 0.035 * subject_hits)
        score += min(0.08, 0.025 * keyword_hits)
        if high_rating_supported:
            score += 0.15
        if in_progress:
            score += 0.22

        metadata_confidence = 0
        metadata_confidence += 1 if has_author else 0
        metadata_confidence += 1 if has_pages else 0
        metadata_confidence += 1 if has_genre_metadata else 0
        score += 0.03 * metadata_confidence

        if not has_author:
            score -= 0.08
        if not has_pages:
            score -= 0.06
        if not has_genre_metadata:
            score -= 0.09
        if completed_df.shape[0] > 0 and not similar and not in_progress:
            score -= 0.12

        candidate_language = infer_language(row)
        if (
            primary_language
            and candidate_language
            and candidate_language != primary_language
            and not similar
        ):
            score -= 0.12

        scores.append(score + noise[idx])

    tbr_df["score"] = scores

    # Keep score in clean range
    tbr_df["score"] = tbr_df["score"].clip(0, 1)

    tbr_df = tbr_df.sort_values(
        by="score",
        ascending=False
    )

    # Optional diversity: only 1 book per author
    if diverse_authors:
        tbr_df = tbr_df.drop_duplicates(
            subset=[author_col]
        )

    return tbr_df

def recommend_one(tbr_ranked):

    if len(tbr_ranked) == 0:
        return None

    # Pick randomly from top 5
    top_slice = tbr_ranked.head(5)
    recommendation = top_slice.sample(1)

    return recommendation
