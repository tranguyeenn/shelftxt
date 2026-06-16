import pandas as pd

from backend.preprocess.normalize import normalize_rating, compute_recency
from backend.ranking.score import score_tbr_books, _resolve_column
from backend.services.book_api import series_to_api_book
from backend.services.recommendation_signals import meaningful_similar_books, read_dataframe


def _read_books(df: pd.DataFrame) -> pd.DataFrame:
    return read_dataframe(df)


def _similar_books(candidate: pd.Series, read_df: pd.DataFrame, title_col: str, author_col: str, limit: int = 3):
    similar = []
    for row, _ in meaningful_similar_books(candidate, read_df, limit=limit):
        similar.append(
            {
                "id": str(row.get("ISBN/UID", "")).strip(),
                "title": str(row.get(title_col, "")).strip(),
                "author": str(row.get(author_col, "Unknown")).strip(),
            }
        )
    return similar[:limit]


def _explanation(candidate: pd.Series, read_df: pd.DataFrame) -> str:
    pages_read = candidate.get("Pages Read", candidate.get("pages_read", 0)) or 0
    try:
        if float(pages_read) > 0:
            return "You already started this book."
    except (TypeError, ValueError):
        pass

    similar = meaningful_similar_books(candidate, read_df, limit=5)
    if any(similarity.same_author for _, similarity in similar):
        return "You’ve read books by this author."
    if any(similarity.shared_genres or similarity.shared_subjects for _, similarity in similar):
        return "This matches genres you’ve read before."
    if any(float(row.get("rating_norm", 0.0) or 0.0) >= 0.8 for row, _ in similar):
        return "You rated similar books highly."
    return "Recommended as a discovery pick from your unread books."


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
        score = float(row.get("score", row.get("author_score", 0.5)) or 0.5)

        book_api = series_to_api_book(row)

        results.append(
            {
                "book": {
                    "id": book_api["id"],
                    "title": book_api["title"],
                    "author": book_api["author"],
                },
                "score": round(min(1.0, max(0.0, score)), 4),
                "explanation": _explanation(row, read_df),
                "similar_books": _similar_books(
                    row, read_df, title_col, author_col, limit=3
                ),
            }
        )

    return results
