from __future__ import annotations

import pandas as pd

from backend.services.metadata_specificity import metadata_specificity, normalize_specificity_term

MIN_ANCHOR_SIMILARITY = 0.15
MIN_GENRE_WITH_ANCHOR_SIMILARITY = 0.12
STRONG_SEMANTIC_SIMILARITY = 0.55
MEANINGFUL_METADATA_OVERLAP = 0.4
GENERIC_BACKFILL_TERMS = {
    "fiction",
    "general",
    "general fiction",
    "life",
    "literature",
    "drama",
    "novel",
    "new york times bestseller",
}
BACKFILL_EXCLUDED_TERMS = {
    "government",
    "natural rights",
    "political authority",
    "political philosophy",
}


def _safe_score(value: object, default: float = 0.0) -> float:
    try:
        score = float(value)
    except (TypeError, ValueError):
        score = default
    if pd.isna(score):
        score = default
    return min(1.0, max(0.0, score))


def valid_anchor_similarity(value: object) -> bool:
    return _safe_score(value) >= MIN_ANCHOR_SIMILARITY


def metadata_evidence(row: pd.Series) -> dict[str, float]:
    signals = row.get("_signal_scores")
    if not isinstance(signals, dict):
        signals = {}
    feedback_breakdown = row.get("_feedback_breakdown")
    if not isinstance(feedback_breakdown, dict):
        feedback_breakdown = {}
    return {
        "anchor_similarity": _safe_score(signals.get("candidate_similarity")),
        "genre_fit": _safe_score(signals.get("genre_fit")),
        "theme_match": _safe_score(signals.get("mood_match")),
        "author_affinity": _safe_score(signals.get("author_affinity")),
        "series_score": _safe_score(feedback_breakdown.get("series_continuity_boost")),
        "negative_preference_penalty": _safe_score(signals.get("negative_preference_penalty")),
    }


def genre_theme_evidence(row: pd.Series) -> float:
    evidence = metadata_evidence(row)
    return max(evidence["genre_fit"], evidence["theme_match"])


def fallback_eligible(ranked: pd.DataFrame, keep_indexes: list[object]) -> bool:
    return bool(ranked.empty or not keep_indexes)


def has_backfill_evidence(row: pd.Series) -> bool:
    evidence = metadata_evidence(row)
    cluster_fit_breakdown = row.get("_cluster_fit_breakdown")
    if not isinstance(cluster_fit_breakdown, dict):
        cluster_fit_breakdown = {}
    if evidence.get("negative_preference_penalty", 0.0) > 0:
        return False
    if evidence["anchor_similarity"] >= 0.05:
        return True
    if evidence["series_score"] > 0:
        return True
    if evidence["author_affinity"] > 0:
        return True
    if _safe_score(cluster_fit_breakdown.get("cluster_fit")) >= 0.15:
        return True
    if _is_library_row(row) and _has_specific_backfill_metadata(row):
        return True
    return False


def _is_library_row(row: pd.Series) -> bool:
    value = row.get("In Library")
    return True if pd.isna(value) else bool(value)


def _has_specific_backfill_metadata(row: pd.Series) -> bool:
    normalized_terms: set[str] = set()
    for column in ("Genres", "Subjects"):
        values = row.get(column) or []
        if not isinstance(values, (list, tuple, set)):
            continue
        for value in values:
            normalized = normalize_specificity_term(value)
            normalized_terms.add(normalized)
            if normalized in BACKFILL_EXCLUDED_TERMS:
                return False
            if normalized in GENERIC_BACKFILL_TERMS:
                continue
            if metadata_specificity(value) >= 0.5:
                return True
    return False


def has_minimum_positive_evidence(row: pd.Series) -> bool:
    evidence = metadata_evidence(row)
    anchor_similarity = evidence["anchor_similarity"]
    specific_signal_count = 0
    if valid_anchor_similarity(anchor_similarity):
        return True
    if evidence["series_score"] > 0:
        return True
    if evidence["author_affinity"] >= 1.0:
        return True
    if evidence["genre_fit"] >= MEANINGFUL_METADATA_OVERLAP and _specific_metadata_overlap(row, "Genres") >= 0.5:
        specific_signal_count += 1
    if evidence["theme_match"] >= MEANINGFUL_METADATA_OVERLAP and _specific_metadata_overlap(row, "Subjects") >= 0.5:
        specific_signal_count += 1
    if anchor_similarity >= MIN_GENRE_WITH_ANCHOR_SIMILARITY:
        specific_signal_count += 1
    if evidence.get("author_affinity", 0.0) > 0:
        specific_signal_count += 1
    if _safe_score(row.get("Discovery Query Confidence")) >= 0.6 and row.get("Discovery Query"):
        specific_signal_count += 1
    if specific_signal_count >= 2:
        return True
    return False


def _specific_metadata_overlap(row: pd.Series, column: str) -> float:
    values = row.get(column) or []
    if not isinstance(values, (list, tuple, set)):
        return 0.0
    return max((metadata_specificity(value) for value in values), default=0.0)


def apply_minimum_evidence_filter(ranked: pd.DataFrame) -> pd.DataFrame:
    if ranked.empty:
        return ranked
    keep = [index for index, row in ranked.iterrows() if has_minimum_positive_evidence(row)]
    backfill = [
        index
        for index, row in ranked.iterrows()
        if index not in keep and has_backfill_evidence(row)
    ]
    if keep and backfill:
        return ranked.loc[[*keep, *backfill]].copy()
    if fallback_eligible(ranked, keep):
        if keep:
            return ranked
        specific_fallback = [
            index
            for index, row in ranked.iterrows()
            if max(_specific_metadata_overlap(row, "Genres"), _specific_metadata_overlap(row, "Subjects")) >= 0.5
            or (_safe_score(row.get("Discovery Query Confidence")) >= 0.6 and row.get("Discovery Query"))
        ]
        if specific_fallback:
            return ranked.loc[specific_fallback].copy()
        return ranked
    return ranked.loc[keep].copy()


def strong_classification_allowed(
    *,
    anchor_similarity: float | None = None,
    direct_series_match: bool = False,
    direct_author_match: bool = False,
    semantic_similarity: float | None = None,
    metadata_overlap: float | None = None,
) -> bool:
    if valid_anchor_similarity(anchor_similarity):
        return True
    if direct_series_match or direct_author_match:
        return True
    return (
        _safe_score(semantic_similarity) >= STRONG_SEMANTIC_SIMILARITY
        and _safe_score(metadata_overlap) >= MEANINGFUL_METADATA_OVERLAP
    )
