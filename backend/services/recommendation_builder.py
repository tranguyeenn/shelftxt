import pandas as pd

from backend.preprocess.normalize import normalize_rating, compute_recency
from backend.ranking.score import score_tbr_books, _resolve_column
from backend.services.book_api import series_to_api_book


def _read_books(df: pd.DataFrame) -> pd.DataFrame:
    status_col = _resolve_column(df, ["read_status", "Read Status"])
    if status_col is None:
        return df.iloc[0:0].copy()
    return df[df[status_col].astype(str).str.strip().str.lower() == "read"].copy()


def _similar_books(read_df: pd.DataFrame, author: str, title_col: str, author_col: str, limit: int = 3):
    if read_df.empty:
        return []

    author_norm = author.strip().lower()
    same_author = read_df[
        read_df[author_col].astype(str).str.strip().str.lower() == author_norm
    ].copy()

    if "rating_norm" in same_author.columns:
        same_author = same_author.sort_values("rating_norm", ascending=False)
    elif "Star Rating" in same_author.columns:
        same_author = same_author.sort_values("Star Rating", ascending=False)

    picks = same_author.head(limit)
    if len(picks) < limit:
        remaining = limit - len(picks)
        others = read_df[~read_df.index.isin(picks.index)].copy()
        if "rating_norm" in others.columns:
            others = others.sort_values("rating_norm", ascending=False)
        elif "Star Rating" in others.columns:
            others = others.sort_values("Star Rating", ascending=False)
        picks = pd.concat([picks, others.head(remaining)], ignore_index=False)

    similar = []
    for _, row in picks.iterrows():
        similar.append(
            {
                "id": str(row.get("ISBN/UID", "")).strip(),
                "title": str(row.get(title_col, "")).strip(),
                "author": str(row.get(author_col, "Unknown")).strip(),
            }
        )
    return similar[:limit]


def _explanation(
    author: str, author_read_count: int, author_score: float, style: str = "balanced"
) -> str:
    style = (style or "balanced").strip().lower()
    if style == "popular" and author_read_count > 0:
        return (
            f"Recommended because {author} is among your highest-rated authors "
            f"({author_read_count} finished book{'s' if author_read_count != 1 else ''})."
        )
    if style == "discovery" and author_read_count == 0:
        return (
            f"Recommended as a discovery pick — {author} is new to your finished reads "
            "but fits your broader rating patterns."
        )
    if author_read_count > 0:
        return (
            f"Recommended because you have finished {author_read_count} book(s) by {author} "
            f"and rated them highly (preference score {author_score:.2f})."
        )
    if author_score >= 0.6:
        return (
            "Recommended because it aligns with authors and rating patterns "
            "from books you have already read."
        )
    return (
        "Recommended because it shares similar reading patterns with books you have "
        "already completed, based on your library ratings."
    )


def _rank_tbr_for_style(df: pd.DataFrame, style: str) -> pd.DataFrame:
    style = (style or "balanced").strip().lower()
    if style == "popular":
        return score_tbr_books(df, randomness_strength=0.0, diverse_authors=False)
    if style == "discovery":
        return score_tbr_books(df, randomness_strength=0.12, diverse_authors=True)
    return score_tbr_books(df, randomness_strength=0.05, diverse_authors=False)


def build_recommendations(df: pd.DataFrame, top_n: int = 10, style: str = "balanced") -> list[dict]:
    if df.empty:
        return []

    df = normalize_rating(df)
    df = compute_recency(df)
    tbr_ranked = _rank_tbr_for_style(df, style)

    if tbr_ranked.empty:
        return []

    read_df = _read_books(df)
    author_col = _resolve_column(df, ["author", "Authors"]) or "Authors"
    title_col = _resolve_column(df, ["title", "Title"]) or "Title"

    if author_col not in read_df.columns and not read_df.empty:
        read_df = read_df.copy()
        read_df[author_col] = "unknown"

    top = tbr_ranked.head(top_n)
    results = []

    for _, row in top.iterrows():
        author = str(row.get(author_col, "Unknown")).strip()
        author_read_count = int(
            (
                read_df[author_col].astype(str).str.strip().str.lower()
                == author.lower()
            ).sum()
        )
        score = float(row.get("score", row.get("author_score", 0.5)) or 0.5)
        author_score = float(row.get("author_score", score) or score)

        book_api = series_to_api_book(row)

        results.append(
            {
                "book": {
                    "id": book_api["id"],
                    "title": book_api["title"],
                    "author": book_api["author"],
                },
                "score": round(min(1.0, max(0.0, score)), 4),
                "explanation": _explanation(
                    author, author_read_count, author_score, style=style
                ),
                "similar_books": _similar_books(
                    read_df, author, title_col, author_col, limit=3
                ),
            }
        )

    return results
