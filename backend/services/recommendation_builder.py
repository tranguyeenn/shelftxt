import logging
import math
import re
import time
from numbers import Real

import pandas as pd

from backend.preprocess.normalize import normalize_rating, compute_recency
from backend.ranking.score import score_tbr_books, _resolve_column
from backend.services.book_api import series_to_api_book
from backend.services.recommendation_composition import (
    blend_library_and_discovery as _blend_library_and_discovery,
    is_in_library_row as _is_in_library_row,
)
from backend.services.recommendation_debug import rec_debug
from backend.services.metadata_specificity import metadata_specificity, normalize_specificity_term
from backend.services.recommendation_evidence import (
    MIN_ANCHOR_SIMILARITY,
    apply_minimum_evidence_filter as _apply_minimum_evidence_filter,
)
from backend.services.recommendation_identity import recommendation_identity, recommendation_identity_aliases
from backend.services.recommendation_signals import meaningful_similar_books, read_dataframe
from backend.services.status import normalize_status

logger = logging.getLogger(__name__)
DEBUG_ANNA_TITLE = "anna karenina"
DEBUG_TITLES = {"killer instinct", "all in", "bad blood"}
HIGH_RATING_THRESHOLD = 4.0
REASON_CLOSE_CONTRIBUTION_MARGIN = 0.35
MAIN_SERIES_TYPES = {None, "", "main", "main series", "main_series", "main-series", "main novel"}


def _debug_title(row: pd.Series) -> str:
    return str(row.get("Title", row.get("title", "")) or "").strip()


def _is_debug_title(value: object) -> bool:
    return str(value or "").strip().casefold() in DEBUG_TITLES


def _log_debug_title(stage: str, row: pd.Series, **fields) -> None:
    title = _debug_title(row)
    if not _is_debug_title(title):
        return
    logger.info(
        "recommendation_title_trace stage=%s title=%s %s",
        stage,
        title,
        " ".join(f"{key}={value}" for key, value in fields.items()),
    )


def _normalized_isbn(value: object) -> str | None:
    cleaned = re.sub(r"[^0-9Xx]", "", str(value or "")).upper()
    return cleaned if len(cleaned) in {10, 13} else None


def _librarything_isbns(row: pd.Series) -> set[str]:
    metadata = row.get("metadata")
    if not isinstance(metadata, dict):
        return set()
    librarything_data = metadata.get("librarything")
    if not isinstance(librarything_data, dict):
        return set()
    related = librarything_data.get("related_isbns")
    if not isinstance(related, list):
        return set()
    return {isbn for value in related if (isbn := _normalized_isbn(value))}


def _apply_librarything_signals(ranked: pd.DataFrame, source: pd.DataFrame) -> pd.DataFrame:
    """Drop known duplicate editions and lightly boost related-work matches."""
    if ranked.empty or "score" not in ranked.columns or "ISBN/UID" not in source.columns:
        return ranked

    read_isbns: set[str] = set()
    read_related: set[str] = set()
    primary_by_index: dict[object, str | None] = {}
    position_by_index = {index: position for position, index in enumerate(source.index)}
    status_col = "Read Status" if "Read Status" in source.columns else "read_status"
    for index, row in source.iterrows():
        primary = _normalized_isbn(row.get("ISBN/UID"))
        primary_by_index[index] = primary
        if normalize_status(row.get(status_col)) == "completed":
            if primary:
                read_isbns.add(primary)
            read_related.update(_librarything_isbns(row))

    keep: list[object] = []
    boosts: dict[object, float] = {}
    for index, row in ranked.iterrows():
        source_index = row.get("_source_index", index)
        primary = _normalized_isbn(row.get("ISBN/UID"))
        related = _librarything_isbns(row)
        candidate_editions = related | ({primary} if primary else set())
        duplicate = False
        for other_index, other_primary in primary_by_index.items():
            if other_index == source_index or not other_primary or other_primary not in candidate_editions:
                continue
            other_status = (
                source.at[other_index, status_col]
                if status_col in source.columns and other_index in source.index
                else ""
            )
            if normalize_status(other_status) == "completed" or position_by_index[other_index] < position_by_index.get(source_index, 0):
                duplicate = True
                break
        if duplicate:
            continue
        keep.append(index)
        if related and related.intersection(read_related | read_isbns):
            boosts[index] = 0.03

    result = ranked.loc[keep].copy()
    if boosts:
        result["score"] = [min(1.0, float(score) + boosts.get(index, 0.0)) for index, score in result["score"].items()]
        result = result.sort_values("score", ascending=False)
    return result


def _reason_anchor_rank_key(book: dict) -> tuple[float, float, int]:
    return (
        float(book.get("_score_weight", 0.0) or 0.0),
        float(book.get("rating") or 0.0),
        int(book.get("_match_score", 0) or 0),
    )


def _select_reason_anchor(candidates: list[dict]) -> dict | None:
    if not candidates:
        return None

    ranked = sorted(candidates, key=_reason_anchor_rank_key, reverse=True)
    best = ranked[0]
    top_contribution = float(best.get("_score_weight", 0.0) or 0.0)
    best_rating = float(best.get("rating") or 0.0)

    if best_rating >= HIGH_RATING_THRESHOLD or top_contribution <= 0:
        return best

    close_margin = max(0.15, top_contribution * REASON_CLOSE_CONTRIBUTION_MARGIN)
    preferred = [
        book
        for book in ranked
        if float(book.get("rating") or 0.0) >= HIGH_RATING_THRESHOLD
        and top_contribution - float(book.get("_score_weight", 0.0) or 0.0) <= close_margin
    ]
    if preferred:
        return max(preferred, key=_reason_anchor_rank_key)
    return best


def _public_reason_anchor(book: dict | None) -> dict | None:
    if not book:
        return None
    return {
        "id": book.get("id", ""),
        "title": book.get("title", ""),
        "author": book.get("author", ""),
        "rating": book.get("rating"),
        "shared_genres": list(book.get("_shared_genres", [])),
        "shared_subjects": list(book.get("_shared_subjects", [])),
    }


def _unique_tags(tags: list[str]) -> list[str]:
    unique: list[str] = []
    seen: set[str] = set()
    for tag in tags:
        key = str(tag).strip().lower()
        if not key or key in seen:
            continue
        seen.add(key)
        unique.append(str(tag).strip())
    return unique


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


def _is_missing_value(value: object) -> bool:
    if value is None:
        return True
    if isinstance(value, Real) and not isinstance(value, bool):
        return not math.isfinite(float(value))
    if isinstance(value, (list, tuple, dict, set)):
        return False
    try:
        return bool(pd.isna(value))
    except (TypeError, ValueError):
        return False


def _safe_value(value: object) -> object:
    if _is_missing_value(value):
        return None
    if isinstance(value, dict):
        return {key: _safe_value(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_safe_value(item) for item in value]
    if isinstance(value, tuple):
        return [_safe_value(item) for item in value]
    return value


def _safe_text(value: object, default: str | None = None) -> str | None:
    safe = _safe_value(value)
    if safe is None:
        return default
    text = str(safe).strip()
    return text or default


def _safe_bool(value: object, default: bool = False) -> bool:
    if _is_missing_value(value):
        return default
    return bool(value)


def _safe_score(value: object, default: float = 0.5) -> float:
    try:
        score = float(value)
    except (TypeError, ValueError):
        score = default
    if not math.isfinite(score):
        score = default
    return round(min(1.0, max(0.0, score)), 4)


def _safe_int(value: object) -> int | None:
    if _is_missing_value(value):
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _first_present(*values: object) -> object:
    for value in values:
        safe = _safe_value(value)
        if safe is not None and str(safe).strip():
            return safe
    return None


def _numeric_fields(value: object, prefix: str = "") -> dict[str, object]:
    fields: dict[str, object] = {}
    if isinstance(value, dict):
        for key, item in value.items():
            child_prefix = f"{prefix}.{key}" if prefix else str(key)
            fields.update(_numeric_fields(item, child_prefix))
    elif isinstance(value, list):
        for index, item in enumerate(value):
            fields.update(_numeric_fields(item, f"{prefix}[{index}]"))
    elif isinstance(value, Real) and not isinstance(value, bool):
        fields[prefix] = value
    return fields


def _unsafe_json_paths(value: object, prefix: str = "") -> list[str]:
    paths: list[str] = []
    if isinstance(value, dict):
        for key, item in value.items():
            child_prefix = f"{prefix}.{key}" if prefix else str(key)
            paths.extend(_unsafe_json_paths(item, child_prefix))
    elif isinstance(value, list):
        for index, item in enumerate(value):
            paths.extend(_unsafe_json_paths(item, f"{prefix}[{index}]"))
    elif isinstance(value, Real) and not isinstance(value, bool) and not math.isfinite(float(value)):
        paths.append(prefix)
    return paths


def _log_recommendation_serialization_probe(item: dict) -> None:
    unsafe_paths = _unsafe_json_paths(item)
    book = item.get("recommended_book") or item.get("book") or {}
    numeric_fields = _numeric_fields(item)
    logger.debug(
        "recommendation_serialization_probe title=%r author=%r source_type=%r "
        "external_id=%r work_id=%r isbn=%r match_score=%r numeric_fields=%s",
        item.get("title") or book.get("title"),
        item.get("author") or book.get("author"),
        item.get("source_type"),
        item.get("external_id") or book.get("external_id"),
        item.get("work_id") or book.get("work_id"),
        item.get("isbn") or book.get("isbn"),
        item.get("match_score"),
        numeric_fields,
    )
    if not unsafe_paths:
        return
    logger.warning(
        "recommendation_serialization_unsafe title=%r author=%r source_type=%r "
        "external_id=%r work_id=%r isbn=%r match_score=%r numeric_fields=%s unsafe_paths=%s",
        item.get("title") or book.get("title"),
        item.get("author") or book.get("author"),
        item.get("source_type"),
        item.get("external_id") or book.get("external_id"),
        item.get("work_id") or book.get("work_id"),
        item.get("isbn") or book.get("isbn"),
        item.get("match_score"),
        numeric_fields,
        unsafe_paths,
    )


def _read_books(df: pd.DataFrame) -> pd.DataFrame:
    return read_dataframe(df)


def _log_anchor_debug(read_df: pd.DataFrame) -> None:
    title_col = _resolve_column(read_df, ["Title", "title"])
    rating_col = _resolve_column(read_df, ["Star Rating", "star_rating", "rating"])
    anna_in_read_df = bool(
        title_col
        and any(str(title).strip().lower() == DEBUG_ANNA_TITLE for title in read_df[title_col])
    )

    rec_debug(
        "anchors_used=%s anna_in_read_df=%s",
        len(read_df),
        anna_in_read_df,
    )

    if title_col is None:
        return

    for _, row in read_df.iterrows():
        rec_debug(
            "anchor title=%s star_rating=%s rating_norm=%s",
            str(row.get(title_col, "") or "").strip(),
            row.get(rating_col) if rating_col else None,
            row.get("rating_norm"),
        )


def _log_final_recommendations(results: list[dict]) -> None:
    for index, item in enumerate(results[:10], start=1):
        book = item.get("recommended_book") or item.get("book") or {}
        rec_debug(
            "final_recommendation rank=%s title=%s score=%s reason=%s recommendation_reasons=%s",
            index,
            book.get("title"),
            item.get("score"),
            item.get("reason"),
            item.get("recommendation_reasons", []),
        )


def _similar_books(
    candidate: pd.Series,
    read_df: pd.DataFrame,
    title_col: str,
    author_col: str,
    limit: int = 3,
    precomputed_matches: list | None = None,
    score_anchors: list | None = None,
):
    similar = []
    seen: set[str] = set()

    if score_anchors:
        for index, _contribution, _similarity in score_anchors:
            if float(_contribution or 0.0) < MIN_ANCHOR_SIMILARITY:
                continue
            if index not in read_df.index:
                continue
            row = read_df.loc[index]
            title = str(row.get(title_col, "")).strip()
            key = title.lower()
            if not title or key in seen:
                continue
            seen.add(key)
            similar.append((row, 0.0))

    if precomputed_matches is not None:
        matches = []
        for index, similarity, _rating in precomputed_matches:
            if index in read_df.index:
                matches.append((read_df.loc[index], similarity))
    else:
        matches = meaningful_similar_books(candidate, read_df, limit=limit)

    for row, _ in matches:
        title = str(row.get(title_col, "")).strip()
        key = title.lower()
        if not title or key in seen:
            continue
        seen.add(key)
        similar.append(
            (
                row,
                0.0,
            )
        )

    result = []
    for row, _ in similar[:limit]:
        result.append(
            {
                "id": str(row.get("ISBN/UID", "")).strip(),
                "title": str(row.get(title_col, "")).strip(),
                "author": str(row.get(author_col, "Unknown")).strip(),
            }
        )
    return result


def _liked_book_entry(row: pd.Series, similarity, *, score_weight: float = 0.0) -> dict:
    author = str(row.get("Authors", row.get("author", "Unknown")) or "Unknown").strip()
    title = str(row.get("Title", row.get("title", "a book you rated highly")) or "").strip()
    raw_rating = row.get("Star Rating", row.get("star_rating"))

    if raw_rating is None or pd.isna(raw_rating):
        display_rating = None
    else:
        try:
            display_rating = float(raw_rating)
        except (TypeError, ValueError):
            display_rating = None

    overlap_count = (
        len(similarity.shared_genres)
        + len(similarity.shared_subjects)
        + (1 if similarity.same_author else 0)
        + (1 if similarity.keyword_overlap else 0)
    )

    return {
        "id": str(row.get("ISBN/UID", row.get("isbn_uid", "")) or "").strip(),
        "title": title,
        "author": author,
        "rating": display_rating,
        "_match_score": overlap_count,
        "_score_weight": score_weight,
        "_shared_genres": list(similarity.shared_genres),
        "_shared_subjects": list(similarity.shared_subjects),
    }


def _match_details(
    candidate: pd.Series,
    read_df: pd.DataFrame,
    precomputed_matches: list | None = None,
    score_anchors: list | None = None,
) -> dict:
    anchor_entries: list[tuple[pd.Series, object, float]] = []
    seen_titles: set[str] = set()

    if score_anchors:
        for index, contribution, similarity in score_anchors:
            if float(contribution or 0.0) < MIN_ANCHOR_SIMILARITY:
                continue
            if index not in read_df.index:
                continue
            row = read_df.loc[index]
            title_key = str(row.get("Title", row.get("title", "")) or "").strip().lower()
            if not title_key or title_key in seen_titles:
                continue
            seen_titles.add(title_key)
            anchor_entries.append((row, similarity, float(contribution or 0.0)))

    supplemental = []
    if precomputed_matches is not None:
        for index, similarity, _rating in precomputed_matches:
            if index not in read_df.index:
                continue
            row = read_df.loc[index]
            title_key = str(row.get("Title", row.get("title", "")) or "").strip().lower()
            if not title_key or title_key in seen_titles:
                continue
            supplemental.append((row, similarity, 0.0))
    else:
        for row, similarity in meaningful_similar_books(candidate, read_df, limit=10):
            title_key = str(row.get("Title", row.get("title", "")) or "").strip().lower()
            if not title_key or title_key in seen_titles:
                continue
            supplemental.append((row, similarity, 0.0))

    similar = anchor_entries + supplemental

    genres: list[str] = []
    subjects: list[str] = []
    authors: list[str] = []
    liked_books: list[dict] = []
    same_author = False
    keyword_match = False

    for row, similarity, score_weight in similar:
        for genre in similarity.shared_genres:
            if genre not in genres:
                genres.append(genre)

        for subject in similarity.shared_subjects:
            if subject not in subjects:
                subjects.append(subject)

        author = str(row.get("Authors", row.get("author", "Unknown")) or "Unknown").strip()

        if similarity.same_author and author and author not in authors:
            authors.append(author)
            same_author = True

        if similarity.keyword_overlap:
            keyword_match = True

        title = str(row.get("Title", row.get("title", "a book you rated highly")) or "").strip()
        if not title:
            continue

        liked_books.append(_liked_book_entry(row, similarity, score_weight=score_weight))

    liked_books = sorted(
        liked_books,
        key=lambda book: (
            float(book.get("_score_weight", 0.0) or 0.0),
            int(book.get("_match_score", 0) or 0),
            float(book.get("rating") or 0),
        ),
        reverse=True,
    )

    reason_anchor = _public_reason_anchor(_select_reason_anchor(liked_books))

    liked_books = [
        {key: value for key, value in book.items() if not key.startswith("_")}
        for book in liked_books
    ]

    matched_genres = _unique_tags(genres)[:5]
    genre_keys = {genre.lower() for genre in matched_genres}
    matched_subjects = [
        subject for subject in _unique_tags(subjects) if subject.lower() not in genre_keys
    ][: max(0, 5 - len(matched_genres))]

    return {
        "matched_genres": matched_genres,
        "matched_subjects": matched_subjects,
        "matched_authors": authors[:3],
        "matched_liked_books": liked_books[:3],
        "reason_anchor": reason_anchor,
        "has_same_author": same_author,
        "has_keyword_match": keyword_match,
    }


def _format_rating(value) -> str | None:
    try:
        rating = float(value)
    except (TypeError, ValueError):
        return None
    return f"{rating:g}★"


def _reader_theme_label(genres: list[str], subjects: list[str]) -> str:
    terms = [
        term
        for term in _unique_tags(subjects + genres)
        if metadata_specificity(term) >= 0.5
    ]
    if terms:
        return ", ".join(terms[:3])
    normalized = " ".join(genres + subjects).casefold()
    if "dystopian" in normalized or "rebellion" in normalized:
        return "control, survival, and resistance"
    if "romance" in normalized or "relationship" in normalized:
        return "relationships and romantic tension"
    if "mystery" in normalized or "thriller" in normalized:
        return "mystery, suspense, and investigation"
    if "fantasy" in normalized or "magic" in normalized:
        return "magic and adventure"
    return "related themes"


def _reason_from_details(details: dict, read_df: pd.DataFrame, candidate: pd.Series | None = None) -> str:
    liked_books = details["matched_liked_books"]
    reason_anchor = details.get("reason_anchor")
    genres = details["matched_genres"]
    subjects = details["matched_subjects"]
    authors = details["matched_authors"]
    useful_tags = _unique_tags(genres + subjects)
    headline_book = reason_anchor or (liked_books[0] if liked_books else None)
    cluster_id = str(candidate.get("Discovery Cluster ID") or "") if candidate is not None else ""

    if len(useful_tags) < 2 and liked_books:
        titles = " and ".join(book["title"] for book in liked_books[:2])
        return f"Because you enjoyed {titles}, this may fit your reading taste."

    if genres and headline_book:
        anchor_title = headline_book["title"]
        rating = _format_rating(headline_book.get("rating"))
        rating_clause = f", which you rated {rating}," if rating else ""
        theme_label = _reader_theme_label(genres, subjects)
        if cluster_id == "ya-dystopian-speculative":
            return f"Because you enjoyed survival-focused dystopian stories like {anchor_title}{rating_clause}, this explores similar themes of control, survival, and resistance."
        if cluster_id == "ya-mystery-thriller":
            return f"Because you liked investigative stories like {anchor_title}{rating_clause}, this leans into {theme_label}."
        if cluster_id == "contemporary-romance-new-adult":
            return f"Because you enjoyed relationship-driven romance like {anchor_title}{rating_clause}, this follows similar emotional and contemporary romance patterns."
        if cluster_id in {"literary-classics", "literary-relationship-fiction", "russian-realism-moral-fiction"}:
            return f"Because {anchor_title}{rating_clause} worked for you, this recommendation emphasizes literary relationships, moral conflict, and psychological tension."
        if cluster_id in {"fantasy", "fantasy-romance"}:
            return f"Because you enjoyed fantasy anchors like {anchor_title}{rating_clause}, this recommendation stays close to magic, quests, and found-family stakes."
        return f"Because you enjoyed {anchor_title}{rating_clause}, this recommendation follows similar themes of {theme_label}."

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

    return "Recommended based on your reading history."


def _signal_percent(value) -> int | None:
    if value is None:
        return None
    try:
        numeric = float(value)
    except (TypeError, ValueError):
        return None
    return round(min(1.0, max(0.0, numeric)) * 100)


def _signals_from_row(row: pd.Series) -> dict:
    raw = row.get("_signal_scores")
    if not isinstance(raw, dict):
        raw = {}

    return {
        "genre_fit": _signal_percent(raw.get("genre_fit")),
        "mood_match": _signal_percent(raw.get("mood_match")),
        "reader_similarity": _signal_percent(raw.get("reader_similarity")),
        "author_affinity": _signal_percent(raw.get("author_affinity")),
    }


def _raw_signal_scores(row: pd.Series) -> dict:
    raw = row.get("_signal_scores")
    return raw if isinstance(raw, dict) else {}


def _breakdown_from_details(details: dict, signals: dict) -> dict:
    return {
        "genre_fit": signals.get("genre_fit"),
        "genre_label": ", ".join(_unique_tags(details["matched_genres"] + details["matched_subjects"])[:2]) or None,
        "mood_match": signals.get("mood_match"),
        "reader_similarity": signals.get("reader_similarity"),
        "author_affinity": signals.get("author_affinity"),
        "inspired_by": details["matched_liked_books"][:3],
    }


def _recommendation_reasons(details: dict) -> list[dict]:
    reasons: list[dict] = []
    liked_books = details["matched_liked_books"]
    genres = details["matched_genres"]
    subjects = details["matched_subjects"]
    authors = details["matched_authors"]
    useful_tags = _unique_tags(genres + subjects)

    if genres and len(useful_tags) >= 2:
        reasons.append(
            {
                "label": "Genre Match",
                "detail": f"Similar to {', '.join(genres[:2])} books you rated highly.",
            }
        )

    if subjects and len(useful_tags) >= 2:
        reasons.append(
            {
                "label": "Mood Match",
                "detail": f"Shares themes like {', '.join(subjects[:2])}.",
            }
        )

    if authors:
        reasons.append(
            {
                "label": "Author Affinity",
                "detail": f"Connected to authors you have enjoyed: {', '.join(authors[:2])}.",
            }
        )

    if liked_books:
        titles = ", ".join(book["title"] for book in liked_books[:3])
        reasons.append(
            {
                "label": "Inspired by books you enjoyed",
                "detail": titles,
            }
        )

    return reasons[:4]


def _related_books_from_details(details: dict) -> list[dict]:
    related: list[dict] = []
    seen: set[tuple[str, str]] = set()

    for book in details["matched_liked_books"]:
        title = str(book.get("title", "")).strip()
        author = str(book.get("author", "")).strip()
        key = (title.lower(), author.lower())

        if not title or key in seen:
            continue

        seen.add(key)
        related.append(
            {
                "id": str(book.get("id", "") or "").strip(),
                "title": title,
                "author": author,
                "rating": book.get("rating"),
            }
        )

        if len(related) >= 3:
            break

    return related


def _explanation(
    candidate: pd.Series,
    read_df: pd.DataFrame,
    precomputed_matches: list | None = None,
    score_anchors: list | None = None,
) -> str:
    pages_read = candidate.get("Pages Read", candidate.get("pages_read", 0)) or 0
    try:
        if float(pages_read) > 0:
            return "You already started this book."
    except (TypeError, ValueError):
        pass

    return _reason_from_details(
        _match_details(candidate, read_df, precomputed_matches, score_anchors),
        read_df,
        candidate,
    )


def _rank_tbr_for_style(df: pd.DataFrame, style: str, refresh: bool = False) -> pd.DataFrame:
    style = (style or "balanced").strip().lower()
    if style == "popular":
        return score_tbr_books(df, randomness_strength=0.0, diverse_authors=False)
    if style in {"discovery", "external_first"}:
        return score_tbr_books(df, randomness_strength=0.0, diverse_authors=True)
    return score_tbr_books(df, randomness_strength=0.0, diverse_authors=False)


def _candidate_identity(row: pd.Series) -> tuple[str, str, str]:
    work = str(row.get("Work Key", row.get("work_key", "")) or "").strip().lower()
    title = str(row.get("Title", row.get("title", "")) or "").strip().lower()
    author = str(row.get("Authors", row.get("author", "")) or "").strip().lower()
    return (work, title, author)


def _candidate_result_key(row: pd.Series) -> tuple[str, str]:
    work = str(row.get("Work Key", row.get("work_key", "")) or "").strip().lower()
    if work:
        return ("work", work)
    edition = str(row.get("Edition Key", row.get("edition_key", "")) or "").strip().lower()
    if edition:
        return ("edition", edition)
    isbn = _normalized_isbn(row.get("External ISBN", row.get("ISBN/UID")))
    if isbn:
        return ("isbn", isbn)
    _work, title, author = _candidate_identity(row)
    return ("title_author", f"{title}|{author}")


def _feedback_identity_keys(row: pd.Series) -> set[str]:
    metadata = row.get("metadata")
    related_isbns: list[str] = []
    if isinstance(metadata, dict):
        external = metadata.get("external")
        librarything = metadata.get("librarything")
        if isinstance(external, dict):
            related_isbns.extend(str(value) for value in external.get("related_isbns") or [])
        if isinstance(librarything, dict):
            related_isbns.extend(str(value) for value in librarything.get("related_isbns") or [])
    keys = recommendation_identity_aliases(
        work_id=str(row.get("External Work ID", row.get("Work Key", "")) or ""),
        isbn=str(row.get("External ISBN", row.get("ISBN/UID", "")) or ""),
        title=str(row.get("Title", row.get("title", "")) or ""),
        author=str(row.get("Authors", row.get("author", "")) or ""),
        related_isbns=related_isbns,
    )
    raw_uid = str(row.get("External ISBN", row.get("ISBN/UID", "")) or "").strip().casefold()
    if raw_uid:
        keys.add(raw_uid)
        keys.add(f"isbn:{raw_uid}")
    return keys


def _feedback_record_keys(record: dict) -> set[str]:
    keys = recommendation_identity_aliases(
        work_id=record.get("work_id"),
        isbn=record.get("isbn"),
        title=record.get("canonical_title"),
        author=record.get("canonical_author"),
    )
    identity = str(record.get("recommendation_identity") or "").strip()
    if identity:
        keys.add(identity)
        keys.add(identity.casefold())
    recommendation_id = str(record.get("recommendation_id") or "").strip()
    if recommendation_id:
        keys.add(recommendation_id)
        keys.add(recommendation_id.casefold())
    return keys


def _row_recommendation_identity(row: pd.Series) -> str:
    return recommendation_identity(
        work_id=str(row.get("External Work ID", row.get("Work Key", "")) or ""),
        isbn=str(row.get("External ISBN", row.get("ISBN/UID", "")) or ""),
        title=str(row.get("Title", row.get("title", "")) or ""),
        author=str(row.get("Authors", row.get("author", "")) or ""),
    )


def _filter_excluded_candidates(df: pd.DataFrame, excluded_identities: set[str] | None) -> pd.DataFrame:
    if df.empty or not excluded_identities:
        return df
    keep = [
        index
        for index, row in df.iterrows()
        if not (_feedback_identity_keys(row) & excluded_identities)
    ]
    return df.loc[keep].copy()


def _series_key(value: object) -> str:
    return re.sub(r"[^a-z0-9]+", " ", str(value or "").casefold()).strip()


def _series_position(value: object) -> float | None:
    if _is_missing_value(value):
        return None
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    return parsed if parsed > 0 and math.isfinite(parsed) else None


def _series_type(value: object) -> str | None:
    if _is_missing_value(value):
        return None
    text = str(value or "").strip().casefold().replace("_", " ").replace("-", " ")
    return text or None


def _is_main_series_type(value: object) -> bool:
    text = _series_type(value)
    return text in MAIN_SERIES_TYPES or text is None


def _series_state(source: pd.DataFrame) -> dict[str, dict]:
    if source.empty or "Series Name" not in source.columns:
        return {}
    status_col = "Read Status" if "Read Status" in source.columns else "read_status"
    state: dict[str, dict] = {}
    for _, row in source.iterrows():
        series_name = str(row.get("Series Name") or "").strip()
        key = _series_key(series_name)
        position = _series_position(row.get("Series Position"))
        if not key or position is None or not _is_main_series_type(row.get("Series Type")):
            continue
        status = normalize_status(row.get(status_col))
        entry = state.setdefault(
            key,
            {
                "series_name": series_name,
                "owned_positions": set(),
                "completed_positions": set(),
                "reading_positions": set(),
                "dnf_positions": set(),
            },
        )
        entry["owned_positions"].add(position)
        if status == "completed":
            entry["completed_positions"].add(position)
        elif status == "reading":
            entry["reading_positions"].add(position)
        elif status == "dnf":
            entry["dnf_positions"].add(position)

    for entry in state.values():
        next_required = 1.0
        completed = entry["completed_positions"]
        while next_required in completed:
            next_required += 1.0
        entry["highest_contiguous_completed_position"] = next_required - 1.0
        entry["next_required_main_position"] = next_required
    return state


def _apply_series_order_filter(ranked: pd.DataFrame, source: pd.DataFrame) -> pd.DataFrame:
    if ranked.empty or "Series Name" not in ranked.columns:
        return ranked
    state = _series_state(source)
    if not state:
        return ranked
    keep: list[object] = []
    for index, row in ranked.iterrows():
        series_name = str(row.get("Series Name") or "").strip()
        key = _series_key(series_name)
        position = _series_position(row.get("Series Position"))
        if not key or position is None or not _is_main_series_type(row.get("Series Type")) or key not in state:
            keep.append(index)
            continue
        entry = state[key]
        next_required = entry["next_required_main_position"]
        eligible = position == next_required
        logger.info(
            "series_order_eligibility series=%s completed_positions=%s next_required=%s "
            "candidate=%s candidate_position=%s eligible=%s reason=%s",
            entry["series_name"],
            sorted(entry["completed_positions"]),
            next_required,
            _debug_title(row),
            position,
            str(eligible).lower(),
            "ok" if eligible else "series_order_skip",
        )
        if eligible:
            keep.append(index)
            _log_debug_title("ranked", row, series=entry["series_name"], candidate_position=position, eligible=True)
        else:
            _log_debug_title("excluded", row, series=entry["series_name"], candidate_position=position, reason="series_order_skip")
    return ranked.loc[keep].copy()


def _apply_feedback_penalties(ranked: pd.DataFrame, feedback_records: list[dict] | None) -> pd.DataFrame:
    if ranked.empty or not feedback_records:
        return ranked

    negative = [record for record in feedback_records if record.get("feedback_type") in {"not_interested", "dismissed"}]
    positive = [record for record in feedback_records if record.get("feedback_type") in {"interested", "accepted"}]
    if not negative and not positive:
        return ranked

    negative_key_counts: dict[str, int] = {}
    positive_key_counts: dict[str, int] = {}
    genre_counts: dict[str, int] = {}
    author_counts: dict[str, int] = {}

    for record in negative:
        for key in _feedback_record_keys(record):
            negative_key_counts[key] = negative_key_counts.get(key, 0) + 1
        for genre in record.get("related_genres") or []:
            normalized = str(genre).strip().casefold()
            if normalized:
                genre_counts[normalized] = genre_counts.get(normalized, 0) + 1
        for author in [record.get("canonical_author"), *(record.get("related_authors") or [])]:
            normalized = str(author or "").strip().casefold()
            if normalized:
                author_counts[normalized] = author_counts.get(normalized, 0) + 1

    for record in positive:
        for key in _feedback_record_keys(record):
            positive_key_counts[key] = positive_key_counts.get(key, 0) + 1

    result = ranked.copy()
    penalties: dict[object, dict] = {}

    for index, row in result.iterrows():
        keys = _feedback_identity_keys(row)
        exact_rejections = max((negative_key_counts.get(key, 0) for key in keys), default=0)
        exact_positive = max((positive_key_counts.get(key, 0) for key in keys), default=0)
        feedback_penalty = 0.0
        feedback_boost = 0.0

        if exact_rejections:
            feedback_penalty += min(0.95, 0.65 + (0.15 * (exact_rejections - 1)))
        if exact_positive:
            feedback_boost += min(0.18, 0.08 * exact_positive)

        similar_penalty = 0.0
        row_genres = [str(value).strip().casefold() for value in _row_list(row.get("Genres")) + _row_list(row.get("Subjects"))]
        for genre in row_genres:
            count = genre_counts.get(genre, 0)
            if count >= 2:
                similar_penalty += min(0.06, 0.02 * count)

        row_author = str(row.get("Authors", row.get("author", "")) or "").strip().casefold()
        author_count = author_counts.get(row_author, 0)
        if author_count >= 2:
            similar_penalty += min(0.12, 0.04 * author_count)

        similar_penalty = min(0.22, similar_penalty)
        total_penalty = min(1.0, feedback_penalty + similar_penalty)
        score = _safe_score(row.get("score"), 0.0)
        result.at[index, "score"] = min(1.0, max(0.0, score + feedback_boost - total_penalty))
        penalties[index] = {
            "recommendation_feedback_penalty": round(total_penalty, 4),
            "exact_feedback_penalty": round(feedback_penalty, 4),
            "similar_feedback_penalty": round(similar_penalty, 4),
            "feedback_positive_boost": round(feedback_boost, 4),
            "exact_feedback_count": exact_rejections,
        }

    result["_feedback_breakdown"] = result.index.map(lambda index: penalties.get(index, {}))
    return result.sort_values("score", ascending=False)


def _exclude_completed_duplicate_works(ranked: pd.DataFrame, source: pd.DataFrame) -> pd.DataFrame:
    if ranked.empty:
        return ranked
    status_col = "Read Status" if "Read Status" in source.columns else "read_status"
    completed_keys = {
        _candidate_identity(row)
        for _, row in source.iterrows()
        if normalize_status(row.get(status_col)) == "completed"
    }
    completed_works = {work for work, _title, _author in completed_keys if work}
    completed_title_author = {(title, author) for _work, title, author in completed_keys if title and author}
    keep = []
    for index, row in ranked.iterrows():
        work, title, author = _candidate_identity(row)
        if work and work in completed_works:
            continue
        if title and author and (title, author) in completed_title_author:
            continue
        keep.append(index)
    return ranked.loc[keep].copy()


def _apply_ownership_ranking(ranked: pd.DataFrame, style: str) -> pd.DataFrame:
    if ranked.empty or "In Library" not in ranked.columns:
        return ranked
    result = ranked.copy()
    in_library = result["In Library"].map(lambda value: True if pd.isna(value) else bool(value))
    if style in {"discovery", "external_first"}:
        library_boost = 0.03
        external_boost = 0.08 if style == "external_first" else 0.04
    elif style == "popular":
        library_boost = 0.05
        external_boost = 0.0
    else:
        library_boost = 0.05
        external_boost = 0.0
    result.loc[in_library, "score"] = result.loc[in_library, "score"] + library_boost
    result.loc[~in_library, "score"] = result.loc[~in_library, "score"] + external_boost
    novelty_boost = pd.Series(0.0, index=result.index)
    if "Novelty Score" in result.columns:
        novelty = pd.to_numeric(result["Novelty Score"], errors="coerce").fillna(0.0).clip(0.0, 1.0)
        novelty_weight = 0.12 if style == "external_first" else 0.08 if style == "discovery" else 0.04
        novelty_boost = novelty * novelty_weight
        result.loc[~in_library, "score"] = result.loc[~in_library, "score"] + novelty_boost.loc[~in_library]
    exploration_boost = pd.Series(0.0, index=result.index)
    if "Exploration Mode" in result.columns:
        broad_exploration = (~in_library) & result["Exploration Mode"].map(lambda value: bool(str(value or "").strip()))
        exploration_value = 0.08 if style == "external_first" else 0.03
        exploration_boost.loc[broad_exploration] = exploration_value
        result.loc[broad_exploration, "score"] = result.loc[broad_exploration, "score"] + exploration_value
    result["score"] = result["score"].clip(0, 1)
    boosts = in_library.map(lambda value: library_boost if value else external_boost)
    result["_library_boost"] = boosts
    result["_novelty_boost"] = novelty_boost
    result["_exploration_boost"] = exploration_boost
    return result.sort_values("score", ascending=False)


def _apply_external_cluster_fit(ranked: pd.DataFrame) -> pd.DataFrame:
    if ranked.empty or "In Library" not in ranked.columns:
        return ranked
    result = ranked.copy()
    fits: dict[object, dict] = {}

    def weighted_overlap(candidate_values: list, target_values: list) -> float:
        candidate_terms = [normalize_specificity_term(value) for value in candidate_values]
        target_terms = [
            normalize_specificity_term(value)
            for value in target_values
            if metadata_specificity(value) >= 0.5
        ]
        if not candidate_terms or not target_terms:
            return 0.0
        possible = sum(metadata_specificity(term) for term in target_terms) or 1.0
        matched = 0.0
        for target in target_terms:
            if any(target == candidate or target in candidate or candidate in target for candidate in candidate_terms):
                matched += metadata_specificity(target)
        return min(1.0, matched / possible)

    def generic_overlap(values: list) -> float:
        if not values:
            return 0.0
        generic = sum(1 for value in values if metadata_specificity(value) <= 0.0)
        return min(1.0, generic / max(1, len(values)))

    for index, row in result.iterrows():
        if _is_in_library_row(row):
            fits[index] = {}
            continue
        signals = row.get("_signal_scores") if isinstance(row.get("_signal_scores"), dict) else {}
        query_confidence = _safe_score(row.get("Discovery Query Confidence"), 0.5)
        candidate_genres = _row_list(row.get("Genres"))
        candidate_themes = _row_list(row.get("Subjects"))
        query_genres = _row_list(row.get("Discovery Specific Genres"))
        query_themes = _row_list(row.get("Discovery Specific Themes"))
        query_authors = {
            normalize_specificity_term(value)
            for value in _row_list(row.get("Discovery Anchor Authors"))
            if normalize_specificity_term(value)
        }
        candidate_author = normalize_specificity_term(row.get("Authors"))
        genre_specific = weighted_overlap(candidate_genres + candidate_themes, query_genres)
        theme_specific = weighted_overlap(candidate_themes + candidate_genres, query_themes)
        author_affinity = _safe_score(signals.get("author_affinity"), 0.0)
        if candidate_author and candidate_author in query_authors:
            author_affinity = 1.0
        anchor_similarity = _safe_score(signals.get("candidate_similarity"), 0.0)
        cluster_fit = min(
            1.0,
            (genre_specific * 0.25)
            + (theme_specific * 0.25)
            + (anchor_similarity * 0.20)
            + (author_affinity * 0.15)
            + (query_confidence * 0.15),
        )
        result.at[index, "score"] = min(1.0, _safe_score(row.get("score"), 0.0) + (0.08 * cluster_fit))
        fits[index] = {
            "cluster_fit": round(cluster_fit, 4),
            "specific_genre_overlap": round(genre_specific, 4),
            "specific_theme_overlap": round(theme_specific, 4),
            "anchor_semantic_similarity": round(anchor_similarity, 4),
            "author_affinity": round(author_affinity, 4),
            "generic_metadata_overlap": round(generic_overlap(candidate_genres + candidate_themes), 4),
            "discovery_query_confidence": round(query_confidence, 4),
        }
    result["_cluster_fit_breakdown"] = result.index.map(lambda index: fits.get(index, {}))
    return result.sort_values("score", ascending=False)


def _apply_series_continuity_boost(ranked: pd.DataFrame, source: pd.DataFrame) -> pd.DataFrame:
    if ranked.empty or "Series Name" not in ranked.columns or "Series Name" not in source.columns:
        return ranked
    status_col = "Read Status" if "Read Status" in source.columns else "read_status"
    series_progress: dict[str, float] = {}
    for _, row in source.iterrows():
        if normalize_status(row.get(status_col)) not in {"completed", "reading"}:
            continue
        series_name = str(row.get("Series Name") or "").strip().casefold()
        if not series_name:
            continue
        try:
            position = float(row.get("Series Position") or 0)
        except (TypeError, ValueError):
            position = 0.0
        series_progress[series_name] = max(series_progress.get(series_name, 0.0), position)
    if not series_progress:
        return ranked

    result = ranked.copy()
    if "_feedback_breakdown" not in result.columns:
        result["_feedback_breakdown"] = [{} for _ in range(len(result))]
    for index, row in result.iterrows():
        series_name = str(row.get("Series Name") or "").strip().casefold()
        if not series_name or series_name not in series_progress:
            continue
        try:
            position = float(row.get("Series Position") or 0)
        except (TypeError, ValueError):
            position = 0.0
        if position and position <= series_progress[series_name]:
            continue
        confidence = _safe_score(row.get("Series Confidence"), 0.5)
        boost = 0.08 + (0.06 * confidence)
        result.at[index, "score"] = min(1.0, _safe_score(row.get("score"), 0.0) + boost)
        breakdown = row.get("_feedback_breakdown") if isinstance(row.get("_feedback_breakdown"), dict) else {}
        result.at[index, "_feedback_breakdown"] = {
            **breakdown,
            "series_continuity_boost": round(boost, 4),
        }
    return result.sort_values("score", ascending=False)


def _dedupe_ranked_candidates(ranked: pd.DataFrame) -> pd.DataFrame:
    if ranked.empty:
        return ranked
    keep: list[object] = []
    seen: set[tuple[str, str]] = set()
    for index, row in ranked.iterrows():
        key = _candidate_result_key(row)
        if key in seen:
            continue
        seen.add(key)
        keep.append(index)
    return ranked.loc[keep].copy()


def _refresh_ranked_candidates(
    ranked: pd.DataFrame,
    *,
    exclude_ids: set[str],
    top_n: int,
) -> pd.DataFrame:
    if ranked.empty or "score" not in ranked.columns:
        return ranked

    max_score = float(ranked["score"].max())
    strong = ranked[ranked["score"] >= max(0.0, max_score - 0.15)].copy()
    if strong.empty:
        return ranked

    id_col = _resolve_column(strong, ["ISBN/UID", "isbn_uid"])
    if id_col is None:
        return strong

    excluded_mask = strong[id_col].astype(str).isin(exclude_ids)
    fresh = strong[~excluded_mask].copy()
    fallback = strong[excluded_mask].copy()

    fresh_rows = list(fresh.index)
    fallback_rows = list(fallback.index)
    ordered_index = fresh_rows + fallback_rows

    remaining_rows = [index for index in ranked.index if index not in strong.index]
    return ranked.loc[ordered_index + remaining_rows]


def build_recommendations(
    df: pd.DataFrame,
    top_n: int = 10,
    style: str = "balanced",
    refresh: bool = False,
    exclude_ids: set[str] | None = None,
    feedback_records: list[dict] | None = None,
    excluded_identities: set[str] | None = None,
) -> list[dict]:
    total_started = time.perf_counter()
    timings: dict[str, float] = {}
    if df.empty:
        return []

    phase_started = time.perf_counter()
    df = normalize_rating(df)
    df = compute_recency(df)
    df = _filter_excluded_candidates(df, excluded_identities)
    timings["metadata_normalization"] = (time.perf_counter() - phase_started) * 1000
    read_df = _read_books(df)
    _log_anchor_debug(read_df)

    phase_started = time.perf_counter()
    tbr_ranked = _rank_tbr_for_style(df, style, refresh=refresh)
    tbr_ranked = _exclude_completed_duplicate_works(tbr_ranked, df)
    tbr_ranked = _apply_series_order_filter(tbr_ranked, df)
    tbr_ranked = _apply_librarything_signals(tbr_ranked, df)
    tbr_ranked = _apply_ownership_ranking(tbr_ranked, style)
    tbr_ranked = _apply_external_cluster_fit(tbr_ranked)
    tbr_ranked = _apply_series_continuity_boost(tbr_ranked, df)
    tbr_ranked = _apply_feedback_penalties(tbr_ranked, feedback_records)
    before_evidence_filter = tbr_ranked.copy()
    tbr_ranked = _apply_minimum_evidence_filter(tbr_ranked)
    if not before_evidence_filter.empty:
        before_external = before_evidence_filter[
            before_evidence_filter.apply(lambda row: not _is_in_library_row(row), axis=1)
        ]
        after_external_indexes = set(tbr_ranked.index)
        weak_removed = [
            row.get("Title")
            for index, row in before_external.iterrows()
            if index not in after_external_indexes
        ]
        logger.info(
            "recommendation_discovery_filter_diagnostics ranked_external=%s weak_evidence_removed=%s "
            "weak_evidence_titles=%s surviving_ranked=%s surviving_external=%s",
            len(before_external),
            len(weak_removed),
            weak_removed[:20],
            len(tbr_ranked),
            int(tbr_ranked.apply(lambda row: not _is_in_library_row(row), axis=1).sum()) if not tbr_ranked.empty else 0,
        )
    tbr_ranked = _dedupe_ranked_candidates(tbr_ranked)
    if refresh:
        tbr_ranked = _refresh_ranked_candidates(
            tbr_ranked,
            exclude_ids=exclude_ids or set(),
            top_n=top_n,
        )
    for rank_index, (_index, row) in enumerate(tbr_ranked.iterrows(), start=1):
        _log_debug_title(
            "ranked",
            row,
            rank=rank_index,
            score=_safe_score(row.get("score"), 0.0),
            source=row.get("Discovery Source"),
            outside_library=not _safe_bool(row.get("In Library", True), default=True),
        )
    timings["candidate_selection_ranking"] = (time.perf_counter() - phase_started) * 1000

    if tbr_ranked.empty:
        return []

    author_col = _resolve_column(df, ["author", "Authors"]) or "Authors"
    title_col = _resolve_column(df, ["title", "Title"]) or "Title"

    if author_col not in read_df.columns and not read_df.empty:
        read_df = read_df.copy()
        read_df[author_col] = "unknown"

    top = _blend_library_and_discovery(tbr_ranked, top_n, style)
    for rank_index, (_index, row) in enumerate(top.iterrows(), start=1):
        _log_debug_title(
            "diversified",
            row,
            rank=rank_index,
            source=row.get("Discovery Source"),
            outside_library=not _safe_bool(row.get("In Library", True), default=True),
        )
    results = []

    explanation_started = time.perf_counter()
    for _, row in top.iterrows():
        if excluded_identities and (_feedback_identity_keys(row) & excluded_identities):
            continue
        score = _safe_score(row.get("score", row.get("author_score", 0.5)))
        precomputed_matches = row.get("_similar_matches")
        if not isinstance(precomputed_matches, list):
            precomputed_matches = None
        score_anchors = row.get("_score_anchors")
        if not isinstance(score_anchors, list):
            score_anchors = None

        book_api = series_to_api_book(row)
        in_library = _safe_bool(row.get("In Library", True), default=True)
        book_id = _safe_int(row.get("Book ID")) if in_library else None
        external_id = _first_present(row.get("External ID"))
        work_id = _first_present(row.get("External Work ID"), row.get("Work Key"))
        edition_id = _first_present(row.get("External Edition ID"), row.get("Edition Key"))
        isbn = _first_present(row.get("External ISBN"))
        source_type = _safe_text(row.get("Source Type"), "library" if in_library else "external_discovery")
        discovery_source = _safe_text(row.get("Discovery Source"), "library" if in_library else "local_catalog")
        outside_library = not in_library
        library_status = _safe_value(row.get("Library Status")) if in_library else None
        details = _match_details(row, read_df, precomputed_matches, score_anchors)
        reason = _explanation(row, read_df, precomputed_matches, score_anchors)
        recommendation_reasons = _recommendation_reasons(details)
        related_books = _related_books_from_details(details)
        signals = _signals_from_row(row)
        raw_signals = _raw_signal_scores(row)
        library_boost = _safe_score(row.get("_library_boost"), 0.0)
        feedback_breakdown = row.get("_feedback_breakdown")
        if not isinstance(feedback_breakdown, dict):
            feedback_breakdown = {}
        feedback_breakdown = {
            "recommendation_feedback_penalty": 0.0,
            "exact_feedback_penalty": 0.0,
            "similar_feedback_penalty": 0.0,
            "feedback_positive_boost": 0.0,
            "exact_feedback_count": 0,
            "series_continuity_boost": 0.0,
            **feedback_breakdown,
        }
        cluster_fit_breakdown = row.get("_cluster_fit_breakdown")
        if not isinstance(cluster_fit_breakdown, dict):
            cluster_fit_breakdown = {}
        recommendation_breakdown = _breakdown_from_details(details, signals)
        recommended_book = {
            "id": book_api["id"],
            "book_id": book_id,
            "external_id": external_id,
            "work_id": work_id,
            "edition_id": edition_id,
            "isbn": isbn,
            "recommendation_id": _row_recommendation_identity(row),
            "title": book_api["title"],
            "author": book_api["author"],
            "cover_url": book_api.get("cover_url"),
            "description": book_api.get("description"),
            "genres": _row_list(row.get("Genres")),
            "subjects": _row_list(row.get("Subjects")),
            "outside_library": outside_library,
            "series_name": _first_present(row.get("Series Name")),
            "canonical_series_identity": _first_present(row.get("Canonical Series Identity")),
            "series_position": _safe_value(row.get("Series Position")),
            "series_position_label": _first_present(row.get("Series Position Label")),
            "series_type": _first_present(row.get("Series Type")),
            "series_source": _first_present(row.get("Series Source")),
            "series_confidence": _safe_value(row.get("Series Confidence")),
            "series_source": _first_present(row.get("Series Source")),
            "is_main_series_entry": _safe_value(row.get("Is Main Series Entry")),
            "user_owned_positions": _safe_value(row.get("User Owned Series Positions")) or [],
            "user_completed_positions": _safe_value(row.get("User Completed Series Positions")) or [],
            "required_next_position": _safe_value(row.get("Required Next Series Position")),
            "series_order_decision": _safe_value(row.get("Series Order Decision")),
            "canonical_work_identity": _first_present(row.get("Canonical Work Identity")),
            "canonical_title": _first_present(row.get("Canonical Title")),
            "original_title": _first_present(row.get("Original Title")),
            "language": _first_present(row.get("Language")),
            "edition_identity": _first_present(row.get("Edition Identity")),
            "collection_type": _first_present(row.get("Collection Type")),
            "component_work_ids": _safe_value(row.get("Component Work IDs")) or [],
            "component_titles": _safe_value(row.get("Component Titles")) or [],
            "component_series_positions": _safe_value(row.get("Component Series Positions")) or [],
        }
        _log_debug_title(
            "identity_created",
            row,
            identity=recommended_book["recommendation_id"],
            work_id=work_id,
            isbn=isbn,
            source=discovery_source,
        )
        ownership_reason = "Already on your shelf" if in_library else "Discovered for you"

        result = _safe_value(
            {
                "recommended_book": recommended_book,
                "book": recommended_book,
                "book_id": book_id,
                "external_id": external_id,
                "work_id": work_id,
                "edition_id": edition_id,
                "isbn": isbn,
                "recommendation_id": recommended_book["recommendation_id"],
                "title": book_api["title"],
                "author": book_api["author"],
                "cover_url": book_api.get("cover_url"),
                "description": book_api.get("description"),
                "genres": _row_list(row.get("Genres")),
                "subjects": _row_list(row.get("Subjects")),
                "series_name": recommended_book["series_name"],
                "canonical_series_identity": recommended_book["canonical_series_identity"],
                "series_position": recommended_book["series_position"],
                "series_position_label": recommended_book["series_position_label"],
                "series_type": recommended_book["series_type"],
                "series_source": recommended_book["series_source"],
                "series_confidence": recommended_book["series_confidence"],
                "series_source": recommended_book["series_source"],
                "is_main_series_entry": recommended_book["is_main_series_entry"],
                "user_owned_positions": recommended_book["user_owned_positions"],
                "user_completed_positions": recommended_book["user_completed_positions"],
                "required_next_position": recommended_book["required_next_position"],
                "series_order_decision": recommended_book["series_order_decision"],
                "canonical_work_identity": recommended_book["canonical_work_identity"],
                "canonical_title": recommended_book["canonical_title"],
                "original_title": recommended_book["original_title"],
                "language": recommended_book["language"],
                "edition_identity": recommended_book["edition_identity"],
                "collection_type": recommended_book["collection_type"],
                "component_work_ids": recommended_book["component_work_ids"],
                "component_titles": recommended_book["component_titles"],
                "component_series_positions": recommended_book["component_series_positions"],
                "duplicate_checks": _safe_value(row.get("Duplicate Checks")) or [],
                "series_order_check": _safe_value(row.get("Series Order Check")),
                "final_inclusion_reason": _safe_value(row.get("Inclusion Reason")),
                "series_books": _safe_value(row.get("Series Books")),
                "series_publication_order": _safe_value(row.get("Series Publication Order")),
                "series_chronological_order": _safe_value(row.get("Series Chronological Order")),
                "score": score,
                "final_score": score,
                "match_score": score,
                "in_library": in_library,
                "is_in_library": in_library,
                "source": "library" if in_library else "external",
                "source_type": source_type,
                "external_discovery": not in_library,
                "outside_library": outside_library,
                "discovery_source": discovery_source,
                "discovery_query": _safe_value(row.get("Discovery Query")),
                "discovery_cluster_id": _safe_value(row.get("Discovery Cluster ID")),
                "exploration_mode": _safe_value(row.get("Exploration Mode")),
                "exploration_source": _safe_value(row.get("Exploration Source")),
                "provider_rank": _safe_value(row.get("Provider Rank")),
                "novelty_score": _safe_value(row.get("Novelty Score")),
                "discovery_anchor_titles": _safe_value(row.get("Discovery Anchor Titles")),
                "provider_metadata_confidence": _safe_value(row.get("Provider Metadata Confidence")),
                "provider": discovery_source,
                "library_status": library_status,
                "reason": reason,
                "explanation": reason,
                "matched_genres": details["matched_genres"],
                "matched_subjects": details["matched_subjects"],
                "matched_authors": details["matched_authors"],
                "matched_liked_books": details["matched_liked_books"],
                "related_books": related_books,
                "recommendation_reasons": [
                    {"label": ownership_reason, "detail": "This recommendation is available in your library." if in_library else f"Found from {discovery_source.replace('_', ' ')} metadata."},
                    *recommendation_reasons,
                ][:4],
                "signals": signals,
                "recommendation_breakdown": recommendation_breakdown,
                "score_breakdown": {
                    "overall": score,
                    "match_percentage_source": "final_score_clamped_times_100_deprecated_for_ui",
                    "match_label_source": "thresholds_on_final_score",
                    "explanation_source": "backend_reader_reason_from_anchor_cluster_themes",
                    "novelty_score": _safe_value(row.get("Novelty Score")),
                    "exploration_mode": _safe_value(row.get("Exploration Mode")),
                    "exploration_source": _safe_value(row.get("Exploration Source")),
                    "candidate_similarity": raw_signals.get("candidate_similarity"),
                    "long_term_preference_score": raw_signals.get("long_term_preference_score"),
                    "rating_affinity_score": raw_signals.get("rating_affinity_score"),
                    "current_mood_score": raw_signals.get("current_mood_score"),
                    "status_pattern_score": raw_signals.get("status_pattern_score"),
                    "diversity_bonus": raw_signals.get("diversity_bonus"),
                    "anchor_similarity": raw_signals.get("candidate_similarity"),
                    "genre_theme_match": max(
                        raw_signals.get("genre_fit") or 0.0,
                        raw_signals.get("mood_match") or 0.0,
                    ),
                    "series_score": feedback_breakdown.get("series_continuity_boost", 0.0),
                    "preference_score": raw_signals.get("long_term_preference_score"),
                    "recency_score": raw_signals.get("current_mood_score"),
                    "library_boost": library_boost,
                    "penalties": {
                        "dislike_penalty": raw_signals.get("negative_preference_penalty"),
                        "recommendation_feedback_penalty": feedback_breakdown.get("recommendation_feedback_penalty", 0.0),
                    },
                    "negative_preference_penalty": raw_signals.get("negative_preference_penalty"),
                    **feedback_breakdown,
                    **cluster_fit_breakdown,
                    "canonical_work_identity": recommended_book["canonical_work_identity"],
                    "edition_identity": recommended_book["edition_identity"],
                    "language": recommended_book["language"],
                    "original_title": recommended_book["original_title"],
                    "collection_type": recommended_book["collection_type"],
                    "component_work_ids": recommended_book["component_work_ids"],
                    "duplicate_checks": _safe_value(row.get("Duplicate Checks")) or [],
                    "series_order_check": _safe_value(row.get("Series Order Check")),
                    "canonical_series_identity": recommended_book["canonical_series_identity"],
                    "series_name": recommended_book["series_name"],
                    "series_position": recommended_book["series_position"],
                    "series_source": recommended_book["series_source"],
                    "series_confidence": recommended_book["series_confidence"],
                    "user_owned_positions": recommended_book["user_owned_positions"],
                    "user_completed_positions": recommended_book["user_completed_positions"],
                    "required_next_position": recommended_book["required_next_position"],
                    "series_order_decision": recommended_book["series_order_decision"],
                    "final_inclusion_reason": _safe_value(row.get("Inclusion Reason")),
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
                    score_anchors=score_anchors,
                ),
            }
        )
        _log_debug_title(
            "serialized",
            row,
            source=discovery_source,
            outside_library=outside_library,
            rank=len(results) + 1,
            identity=recommended_book["recommendation_id"],
        )
        if outside_library:
            logger.info(
                "external_candidate_final title=%s provider=%s source_query=%s cluster=%s "
                "anchor_titles=%s semantic_similarity=%s specific_genre_overlap=%s "
                "specific_theme_overlap=%s generic_metadata_overlap=%s cluster_fit=%s "
                "final_score=%s final_rank=%s included=true identity=%s",
                book_api["title"],
                discovery_source,
                result.get("discovery_query"),
                result.get("discovery_cluster_id"),
                result.get("discovery_anchor_titles"),
                raw_signals.get("candidate_similarity"),
                cluster_fit_breakdown.get("specific_genre_overlap"),
                cluster_fit_breakdown.get("specific_theme_overlap"),
                cluster_fit_breakdown.get("generic_metadata_overlap"),
                cluster_fit_breakdown.get("cluster_fit"),
                score,
                len(results) + 1,
                recommended_book["recommendation_id"],
            )
        _log_recommendation_serialization_probe(result)
        results.append(result)

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
    _log_final_recommendations(results)
    return results
