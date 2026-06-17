import logging
import random
import time

import pandas as pd

from backend.preprocess.normalize import normalize_rating, compute_recency
from backend.ranking.score import score_tbr_books, _resolve_column
from backend.services.book_api import series_to_api_book
from backend.services.recommendation_signals import meaningful_similar_books, read_dataframe

logger = logging.getLogger(__name__)


def _read_books(df: pd.DataFrame) -> pd.DataFrame:
    return read_dataframe(df)


def _similar_books(
    candidate: pd.Series,
    read_df: pd.DataFrame,
    title_col: str,
    author_col: str,
    limit: int = 3,
    precomputed_matches: list | None = None,
):
    similar = []
    if precomputed_matches is not None:
        matches = []
        for index, similarity, _rating in precomputed_matches[:limit]:
            if index in read_df.index:
                matches.append((read_df.loc[index], similarity))
    else:
        matches = meaningful_similar_books(candidate, read_df, limit=limit)

    for row, _ in matches:
        similar.append(
            {
                "id": str(row.get("ISBN/UID", "")).strip(),
                "title": str(row.get(title_col, "")).strip(),
                "author": str(row.get(author_col, "Unknown")).strip(),
            }
        )
    return similar[:limit]


def _match_details(
    candidate: pd.Series,
    read_df: pd.DataFrame,
    precomputed_matches: list | None = None,
) -> dict:
    if precomputed_matches is not None:
        similar = []
        for index, similarity, rating in precomputed_matches[:5]:
            if index in read_df.index:
                similar.append((read_df.loc[index], similarity, rating))
    else:
        similar = [
            (row, similarity, float(row.get("rating_norm", 0.0) or 0.0))
            for row, similarity in meaningful_similar_books(candidate, read_df, limit=5)
        ]

    genres: list[str] = []
    subjects: list[str] = []
    authors: list[str] = []
    liked_books: list[dict] = []

    for row, similarity, rating in similar:
        for genre in similarity.shared_genres:
            if genre not in genres:
                genres.append(genre)
        for subject in similarity.shared_subjects:
            if subject not in subjects:
                subjects.append(subject)
        author = str(row.get("Authors", row.get("author", "Unknown")) or "Unknown").strip()
        if similarity.same_author and author and author not in authors:
            authors.append(author)
        title = str(row.get("Title", row.get("title", "a book you rated highly")) or "").strip()
        if title:
            raw_rating = row.get("Star Rating", row.get("star_rating"))
            try:
                display_rating = float(raw_rating)
            except (TypeError, ValueError):
                display_rating = None
            liked_books.append(
                {
                    "id": str(row.get("ISBN/UID", row.get("isbn_uid", "")) or "").strip(),
                    "title": title,
                    "author": author,
                    "rating": display_rating,
                }
            )

    return {
        "matched_genres": genres[:4],
        "matched_subjects": subjects[:4],
        "matched_authors": authors[:3],
        "matched_liked_books": liked_books[:3],
    }


def _format_rating(value) -> str | None:
    try:
        rating = float(value)
    except (TypeError, ValueError):
        return None
    return f"{rating:g}★"


def _reason_from_details(details: dict, read_df: pd.DataFrame) -> str:
    liked_books = details["matched_liked_books"]
    genres = details["matched_genres"]
    subjects = details["matched_subjects"]
    authors = details["matched_authors"]

    if genres and liked_books:
        book = liked_books[0]
        rating = _format_rating(book.get("rating"))
        suffix = f", which you rated {rating}" if rating else ", from your completed books"
        signals = genres[:2] + subjects[:2]
        return f"Shares {', '.join(signals[:4])} with {book['title']}{suffix}."

    if subjects and liked_books:
        titles = " and ".join(book["title"] for book in liked_books[:2])
        return f"Matches your interest in {', '.join(subjects[:2])} from {titles}."

    if authors and liked_books:
        examples = " and ".join(book["title"] for book in liked_books[:2])
        return f"You rated books by {', '.join(authors[:2])} highly, including {examples}."

    has_metadata = False
    for _, row in read_df.iterrows():
        if row.get("Genres") or row.get("genres") or row.get("Subjects") or row.get("subjects"):
            has_metadata = True
            break

    if not has_metadata:
        return "Genre metadata has not been generated yet, so this uses rating and author signals only."

    liked_titles: list[str] = []
    for _, row in read_df.iterrows():
        title = str(row.get("Title", row.get("title", "")) or "").strip()
        if title:
            liked_titles.append(title)
        if len(liked_titles) >= 2:
            break
    if liked_titles:
        return f"You rated completed books highly, including {' and '.join(liked_titles)}."
    return "Recommended from your completed books and stored ratings."


def _explanation(
    candidate: pd.Series,
    read_df: pd.DataFrame,
    precomputed_matches: list | None = None,
) -> str:
    pages_read = candidate.get("Pages Read", candidate.get("pages_read", 0)) or 0
    try:
        if float(pages_read) > 0:
            return "You already started this book."
    except (TypeError, ValueError):
        pass

    return _reason_from_details(_match_details(candidate, read_df, precomputed_matches), read_df)


def _rank_tbr_for_style(df: pd.DataFrame, style: str, refresh: bool = False) -> pd.DataFrame:
    style = (style or "balanced").strip().lower()
    if style == "popular":
        return score_tbr_books(df, randomness_strength=0.0, diverse_authors=False)
    if style == "discovery":
        return score_tbr_books(df, randomness_strength=0.0, diverse_authors=True)
    return score_tbr_books(df, randomness_strength=0.0, diverse_authors=False)


def _refresh_ranked_candidates(
    ranked: pd.DataFrame,
    *,
    exclude_ids: set[str],
    top_n: int,
) -> pd.DataFrame:
    if ranked.empty or "score" not in ranked.columns:
        return ranked

    max_score = float(ranked["score"].max())
    strong = ranked[ranked["score"] >= max(0.35, max_score - 0.15)].copy()
    if strong.empty:
        return ranked

    id_col = _resolve_column(strong, ["ISBN/UID", "isbn_uid"])
    if id_col is None:
        return strong

    excluded_mask = strong[id_col].astype(str).isin(exclude_ids)
    fresh = strong[~excluded_mask].copy()
    fallback = strong[excluded_mask].copy()

    fresh_rows = list(fresh.index)
    random.shuffle(fresh_rows)
    fallback_rows = list(fallback.index)
    random.shuffle(fallback_rows)
    ordered_index = fresh_rows + fallback_rows

    return ranked.loc[ordered_index]


def build_recommendations(
    df: pd.DataFrame,
    top_n: int = 10,
    style: str = "balanced",
    refresh: bool = False,
    exclude_ids: set[str] | None = None,
) -> list[dict]:
    total_started = time.perf_counter()
    timings: dict[str, float] = {}
    if df.empty:
        return []

    phase_started = time.perf_counter()
    df = normalize_rating(df)
    df = compute_recency(df)
    timings["metadata_normalization"] = (time.perf_counter() - phase_started) * 1000

    phase_started = time.perf_counter()
    tbr_ranked = _rank_tbr_for_style(df, style, refresh=refresh)
    if refresh:
        tbr_ranked = _refresh_ranked_candidates(
            tbr_ranked,
            exclude_ids=exclude_ids or set(),
            top_n=top_n,
        )
    timings["candidate_selection_ranking"] = (time.perf_counter() - phase_started) * 1000

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

    explanation_started = time.perf_counter()
    for _, row in top.iterrows():
        score = float(row.get("score", row.get("author_score", 0.5)) or 0.5)
        precomputed_matches = row.get("_similar_matches")
        if not isinstance(precomputed_matches, list):
            precomputed_matches = None

        book_api = series_to_api_book(row)
        details = _match_details(row, read_df, precomputed_matches)
        reason = _explanation(row, read_df, precomputed_matches)
        recommended_book = {
            "id": book_api["id"],
            "title": book_api["title"],
            "author": book_api["author"],
        }

        results.append(
            {
                "recommended_book": recommended_book,
                "book": recommended_book,
                "score": round(min(1.0, max(0.0, score)), 4),
                "reason": reason,
                "explanation": reason,
                "matched_genres": details["matched_genres"],
                "matched_subjects": details["matched_subjects"],
                "matched_authors": details["matched_authors"],
                "matched_liked_books": details["matched_liked_books"],
                "score_breakdown": {
                    "overall": round(min(1.0, max(0.0, score)), 4),
                    "metadata": bool(details["matched_genres"] or details["matched_subjects"]),
                    "author": bool(details["matched_authors"]),
                    "fallback": not bool(details["matched_genres"] or details["matched_subjects"] or details["matched_authors"]),
                },
                "similar_books": _similar_books(
                    row,
                    read_df,
                    title_col,
                    author_col,
                    limit=3,
                    precomputed_matches=precomputed_matches,
                ),
            }
        )

    timings["explanation_generation"] = (time.perf_counter() - explanation_started) * 1000
    timings["final_serialization"] = timings["explanation_generation"]
    timings["total"] = (time.perf_counter() - total_started) * 1000
    logger.info(
        "recommendation_builder_timing metadata_normalization=%.2fms "
        "candidate_selection=%.2fms explanation_generation=%.2fms "
        "final_serialization=%.2fms total=%.2fms",
        timings.get("metadata_normalization", 0.0),
        timings.get("candidate_selection_ranking", 0.0),
        timings.get("explanation_generation", 0.0),
        timings.get("final_serialization", 0.0),
        timings.get("total", 0.0),
    )
    return results
