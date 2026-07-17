from __future__ import annotations

from collections import Counter, defaultdict, deque
from dataclasses import dataclass
import logging
from uuid import UUID
import re

import pandas as pd
from sqlalchemy.orm import Session

from backend.services.metadata_specificity import is_generic_metadata, metadata_specificity, normalize_specificity_term
from backend.services.recommendation import (
    MAX_RECOMMENDATION_BOOKS,
    _candidate_status,
    _normalize_style,
    books_to_dataframe,
    get_books_for_recommendation,
    recommendation_sections_response,
)
from backend.services.recommendation_builder import build_recommendations
from backend.services.recommendation_discovery import DiscoveryQuery, discovery_candidate_rows
from backend.services.recommendation_feedback import (
    active_feedback_for_user,
    active_not_interested_identities,
    feedback_to_ranking_records,
)

logger = logging.getLogger(__name__)
MAX_ANCHORS_PER_CLUSTER = 3
DEFAULT_RECOMMENDATIONS_PER_CLUSTER = 3

CLUSTER_IDENTITY_TERMS: dict[str, tuple[str, ...]] = {
    "literary-classics": ("Russian realism", "psychological classics", "moral conflict", "literary relationships"),
    "ya-dystopian-speculative": ("survival competitions", "dystopian rebellion", "state control", "resistance"),
    "ya-mystery-thriller": ("criminal profilers", "serial investigations", "teen detectives", "cold cases"),
    "contemporary-romance-new-adult": ("women in STEM", "academic rivals", "romantic comedy", "contemporary relationships"),
    "fantasy": ("found family", "magic", "fae courts", "fantasy quests"),
}

GENERIC_HEADER_TERMS = {
    "young adult",
    "children's fiction",
    "childrens fiction",
    "juvenile fiction",
    "new york times bestseller",
    "schools",
    "school",
    "fiction",
    "literature",
    "general",
    "romance",
    "fantasy",
    "contemporary",
}

FALLBACK_TOPIC_WEAK_TERMS = {
    "young adult",
    "young adult fiction",
    "juvenile fiction",
    "juvenile literature",
    "juvenile works",
    "children s fiction",
    "children's fiction",
    "child and youth fiction",
    "boys",
    "boys fiction",
    "gays",
    "gay teenagers",
    "teenage boys",
    "young men",
    "young women",
    "youth",
    "high schools",
    "high school students",
    "elementary and junior high school",
    "schools",
    "schools fiction",
    "school",
    "comic books strips",
    "love",
    "survival",
    "survival fiction",
    "coming of age",
    "fiction coming of age",
    "friendship",
    "friendship fiction",
    "new york times bestseller",
    "book set",
    "book_set",
    "historical fiction",
    "historical",
    "drama",
    "contemporary",
    "nonfiction",
    "non fiction",
    "memoir",
    "memoirs",
    "biography",
    "biographies",
    "autobiography",
    "autobiographies",
    "history",
    "books",
    "book",
    "literature",
    "readers",
    "readers adult",
    "women",
    "interpersonal relations",
    "interpersonal relations fiction",
    "memory",
}

FALLBACK_TOPIC_ALLOWED_GENERIC_PREFIXES = (
    "young adult fiction comics graphic novels",
)

FANTASY_STRONG_TERMS = {
    "magic",
    "magical",
    "fae",
    "faeries",
    "fairies",
    "witch",
    "witches",
    "wizard",
    "wizards",
    "dragon",
    "dragons",
    "quest",
    "quests",
    "found family",
    "paranormal",
    "supernatural",
    "spells",
    "sorcery",
    "juvenile fantasy",
    "high fantasy",
    "urban fantasy",
    "epic fantasy",
    "fantasy romance",
    "paranormal romance",
    "children's fantasy",
    "childrens fantasy",
}

FANTASY_TITLE_TERMS = {
    "court of",
    "amari",
}

FANTASY_BROAD_TERMS = {
    "fantasy",
    "fantasy fiction",
    "canadian fantasy fiction",
}

FANTASY_CONTRADICTORY_TERMS = {
    "nonfiction",
    "non-fiction",
    "memoir",
    "autobiography",
    "autobiographies",
    "biography",
    "law",
    "legal",
    "criminal justice",
    "imprisonment",
    "prison",
    "civil rights",
    "capital punishment",
    "death row",
    "racism",
    "political dystopia",
    "dystopian",
    "dystopia",
    "totalitarian",
    "feminism",
    "women political activity",
    "social justice",
}


@dataclass(frozen=True)
class ClusterRule:
    cluster_id: str
    label: str
    title: str
    keywords: tuple[str, ...]
    authors: tuple[str, ...] = ()
    title_keywords: tuple[str, ...] = ()
    required_any: tuple[str, ...] = ()
    excluded_keywords: tuple[str, ...] = ()


@dataclass
class ClusterDiagnostics:
    cluster_id: str
    title: str
    anchor_count: int
    strong_local_candidate_count: int = 0
    discovery_queries_allocated: list[str] | None = None
    discovered_candidate_count: int = 0
    candidate_count_before_evidence_gating: int = 0
    candidate_count_after_evidence_gating: int = 0
    backfill_candidate_count: int = 0
    final_recommendation_count: int = 0
    evidence_rejections: list[dict] | None = None
    repeated_completed_support: float = 0.0
    recent_support: float = 0.0
    rating_support: float = 0.0
    cluster_reader_intent_score: float = 0.0
    final_display_priority: float = 0.0
    raw_local_candidate_count: int = 0
    qualified_local_candidate_count: int = 0
    strong_continuity_candidate_count: int = 0
    requested_external_candidate_count: int = 0
    hardcover_queried: bool = False
    allocation_reason: str | None = None
    external_results_returned: int = 0
    external_results_admitted: int = 0
    external_rejection_reasons: list[dict] | None = None

    def to_dict(self) -> dict:
        return {
            "cluster_id": self.cluster_id,
            "title": self.title,
            "anchor_count": self.anchor_count,
            "strong_local_candidate_count": self.strong_local_candidate_count,
            "discovery_queries_allocated": self.discovery_queries_allocated or [],
            "discovered_candidate_count": self.discovered_candidate_count,
            "candidate_count_before_evidence_gating": self.candidate_count_before_evidence_gating,
            "candidate_count_after_evidence_gating": self.candidate_count_after_evidence_gating,
            "backfill_candidate_count": self.backfill_candidate_count,
            "final_recommendation_count": self.final_recommendation_count,
            "evidence_rejections": self.evidence_rejections or [],
            "repeated_completed_support": self.repeated_completed_support,
            "recent_support": self.recent_support,
            "rating_support": self.rating_support,
            "cluster_reader_intent_score": self.cluster_reader_intent_score,
            "final_display_priority": self.final_display_priority,
            "raw_local_candidate_count": self.raw_local_candidate_count,
            "qualified_local_candidate_count": self.qualified_local_candidate_count,
            "strong_continuity_candidate_count": self.strong_continuity_candidate_count,
            "requested_external_candidate_count": self.requested_external_candidate_count,
            "hardcover_queried": self.hardcover_queried,
            "allocation_reason": self.allocation_reason,
            "external_results_returned": self.external_results_returned,
            "external_results_admitted": self.external_results_admitted,
            "external_rejection_reasons": self.external_rejection_reasons or [],
        }


CLUSTER_RULES = (
    ClusterRule(
        cluster_id="literary-classics",
        label="Literary Classics",
        title="Because you enjoyed Literary Classics",
        keywords=(
            "classic",
            "classics",
            "literary",
            "literature",
            "russian literature",
            "historical fiction",
            "drama",
            "tragedy",
        ),
        authors=("tolstoy", "shakespeare", "fitzgerald", "dickens", "hawthorne", "eliot", "austen"),
        title_keywords=("anna karenina", "war and peace", "great gatsby", "ivan ilyich"),
    ),
    ClusterRule(
        cluster_id="ya-dystopian-speculative",
        label="YA Dystopian / Speculative",
        title="Because you enjoyed The Hunger Games",
        keywords=(
            "dystopian",
            "dystopia",
            "science fiction",
            "speculative",
            "rebellion",
            "post-apocalyptic",
        ),
        title_keywords=("hunger games", "catching fire", "mockingjay", "scythe"),
        required_any=("dystopian", "dystopia", "speculative", "rebellion", "post-apocalyptic", "hunger games", "maze runner", "scythe"),
    ),
    ClusterRule(
        cluster_id="ya-mystery-thriller",
        label="YA Mystery / Thriller",
        title="Because you enjoyed The Naturals",
        keywords=(
            "mystery",
            "thriller",
            "crime fiction",
            "detective",
            "serial killer",
            "profiling",
            "psychological",
            "suspense",
            "puzzle",
        ),
        authors=("jennifer lynn barnes", "maureen johnson"),
        title_keywords=("naturals", "killer instinct", "all in", "bad blood", "truly devious"),
        required_any=("mystery", "thriller", "crime fiction", "detective", "serial killer", "profiling", "suspense", "puzzle", "naturals", "truly devious"),
    ),
    ClusterRule(
        cluster_id="contemporary-romance-new-adult",
        label="Contemporary Romance / New Adult",
        title="Because you enjoyed Book Lovers",
        keywords=(
            "romance",
            "contemporary romance",
            "new adult",
            "love stories",
            "relationships",
            "romantic comedy",
        ),
        authors=("emily henry", "ali hazelwood", "abby jimenez", "tessa bailey"),
        title_keywords=("book lovers", "happy place", "funny story", "beach read", "deep end"),
        required_any=("contemporary romance", "new adult", "romantic comedy", "book lovers", "happy place", "funny story", "deep end", "emily henry", "ali hazelwood"),
        excluded_keywords=("fantasy fiction", "high fantasy", "paranormal"),
    ),
    ClusterRule(
        cluster_id="fantasy",
        label="Fantasy",
        title="Because you enjoyed Fantasy",
        keywords=("fantasy", "magic", "paranormal", "faeries", "juvenile fantasy"),
        title_keywords=("court of", "amari"),
        required_any=("fantasy", "magic", "paranormal", "faeries", "court of", "amari"),
    ),
)


def _text(value: object) -> str:
    return str(value or "").strip()


def _slug(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", value.casefold()).strip("-") or "cluster"


def _list_values(value: object) -> list[str]:
    if value is None:
        return []
    if isinstance(value, list | tuple | set):
        return [_text(item) for item in value if _text(item)]
    return [_text(value)] if _text(value) else []


def _row_title(row) -> str:
    return _text(row.get("Title") or row.get("title"))


def _row_author(row) -> str:
    return _text(row.get("Authors") or row.get("author"))


def _row_tags(row) -> list[str]:
    return [*_list_values(row.get("Genres")), *_list_values(row.get("Subjects"))]


def _row_genres(row) -> list[str]:
    return _list_values(row.get("Genres"))


def _normalized_terms(values: list[str]) -> set[str]:
    return {normalize_specificity_term(value) for value in values if normalize_specificity_term(value)}


def _fallback_topic_term_allowed(value: object) -> bool:
    normalized = normalize_specificity_term(value)
    if not normalized:
        return False
    if _fallback_topic_metadata_noise(normalized):
        return False
    if normalized in FALLBACK_TOPIC_WEAK_TERMS or normalized in GENERIC_HEADER_TERMS or is_generic_metadata(normalized):
        return False
    if any(normalized.startswith(prefix) for prefix in FALLBACK_TOPIC_ALLOWED_GENERIC_PREFIXES):
        return normalized != "young adult fiction comics graphic novels general"
    if any(part in normalized.split() for part in {"boys", "youth"}):
        return False
    if "school" in normalized:
        return False
    if metadata_specificity(normalized) < 0.5:
        return False
    return True


def _fallback_topic_metadata_noise(normalized: str) -> bool:
    if not normalized:
        return True
    if normalized.startswith("collectionid "):
        return True
    if "new york times" in normalized or normalized.startswith("nyt ") or " nyt " in normalized:
        return True
    if "bestseller" in normalized:
        return True
    if any(term in normalized for term in ("paperback monthly", "hardcover monthly", "trade fiction paperback")):
        return True
    if re.search(r"\b(monthly|weekly|chart|list|ranking|rankings)\b", normalized) and re.search(r"\b(19|20)\d{2}\b", normalized):
        return True
    if re.search(r"\b(19|20)\d{2}\s+\d{1,2}\s+\d{1,2}\b", normalized):
        return True
    if re.search(r"\b\d{4}\s+\d{2}\s+\d{2}\b", normalized):
        return True
    if any(term in normalized for term in ("open library", "open syllabus", "long now manual")):
        return True
    if normalized in {"book set", "book_set", "in library", "large type books", "fictional works publication type"}:
        return True
    return False


def _fallback_topic_terms_from_raw(terms: set[str]) -> set[str]:
    return {normalize_specificity_term(term) for term in terms if _fallback_topic_term_allowed(term)}


def _has_any(terms: set[str], needles: tuple[str, ...]) -> bool:
    return any(any(needle in term for needle in needles) for term in terms)


def _fallback_identity_label(raw_terms: set[str], preferred_terms: set[str] | None = None) -> str | None:
    allowed_terms = _fallback_topic_terms_from_raw(raw_terms)
    preferred = allowed_terms & (preferred_terms or set())
    evidence_terms = preferred or allowed_terms
    all_terms = {normalize_specificity_term(term) for term in raw_terms if normalize_specificity_term(term)}

    if _has_any(evidence_terms, ("criminal justice memoir",)):
        return "Criminal justice memoirs"
    if _has_any(evidence_terms, ("criminal justice", "wrongful conviction", "legal reform")) and _has_any(all_terms, ("memoir", "nonfiction", "non fiction")):
        return "Criminal justice memoirs"
    if _has_any(evidence_terms, ("modern dance", "choreographer", "dancers biography")) and _has_any(all_terms, ("biography", "dancer")):
        return "Modern dance biographies"
    if _has_any(evidence_terms, ("holocaust", "concentration camp")) and _has_any(all_terms, ("memoir", "survival", "historical")):
        return "Holocaust memoir and survival"
    if _has_any(evidence_terms, ("science history", "history of science", "scientific discovery")):
        return "Science history"
    if _has_any(evidence_terms, ("political biography", "presidents", "political leaders")):
        return "Political biography"
    if _has_any(evidence_terms, ("young adult fiction comics graphic novels lgbt", "lgbtq")) and _has_any(evidence_terms | all_terms, ("love in adolescence", "romance")):
        return "Queer teen graphic romance"
    if _has_any(evidence_terms, ("young adult fiction comics graphic novels lgbt", "lgbtq")):
        return "Queer YA graphic novels"
    if _has_any(evidence_terms, ("love in adolescence",)) and _has_any(evidence_terms | all_terms, ("mental illness", "emotional problems")):
        return "Contemporary teen relationships and mental health"
    if _has_any(evidence_terms, ("love in adolescence",)):
        return "Contemporary teen relationships"
    if _has_any(evidence_terms, ("emotional problems", "cutting self mutilation", "sexual abuse")):
        return "Teen grief, identity, and healing"
    if _has_any(evidence_terms, ("amnesia", "bullying", "self perception", "interpersonal relations")):
        return "Middle-grade friendship and moral choices"

    if preferred:
        return next(iter(sorted(preferred, key=_fallback_topic_priority, reverse=True)), None)
    return None


HIGH_CONFIDENCE_FALLBACK_LABELS = {
    "Criminal justice memoirs",
    "Modern dance biographies",
    "Holocaust memoir and survival",
    "Science history",
    "Political biography",
    "Queer teen graphic romance",
    "Queer YA graphic novels",
    "Contemporary teen relationships",
    "Contemporary teen relationships and mental health",
    "Teen grief, identity, and healing",
    "Middle-grade friendship and moral choices",
}


def _high_confidence_fallback_rule(rule: ClusterRule) -> bool:
    return rule.cluster_id.startswith("topic-") and rule.label in HIGH_CONFIDENCE_FALLBACK_LABELS


def _fallback_topic_priority(value: object) -> tuple[int, int]:
    normalized = normalize_specificity_term(value)
    if any(term in normalized for term in ("love in adolescence", "emotional problems", "cutting self mutilation", "sex crimes")):
        return (3, len(normalized))
    if any(term in normalized for term in ("lgbt", "graphic novels", "comic")):
        return (2, len(normalized))
    return (1, len(normalized))


def _contains_term(haystack: str, terms: set[str]) -> set[str]:
    hits: set[str] = set()
    for term in terms:
        if not term:
            continue
        pattern = r"(?<![a-z0-9])" + re.escape(term.casefold()) + r"(?![a-z0-9])"
        if re.search(pattern, haystack.casefold()):
            hits.add(term)
    return hits


def _row_identity(row) -> str:
    for key in (
        "External Work ID",
        "Work Key",
        "External ID",
        "External ISBN",
        "ISBN/UID",
        "Book ID",
    ):
        value = _text(row.get(key))
        if value:
            return f"{key}:{value.casefold()}"
    title = _row_title(row).casefold()
    author = _row_author(row).casefold()
    return f"title:{title}|author:{author}"


def _row_rating(row) -> float:
    try:
        return float(row.get("Star Rating") or 0)
    except (TypeError, ValueError):
        return 0.0


def _row_in_library(row) -> bool:
    value = row.get("In Library")
    if value is None:
        return True
    try:
        if pd.isna(value):
            return True
    except (TypeError, ValueError):
        pass
    return bool(value)


def _cluster_recency_weight(row) -> float:
    value = row.get("End Date", row.get("end_date", row.get("Last Date Read")))
    parsed = pd.to_datetime(value, errors="coerce")
    if pd.isna(parsed):
        return 0.25
    today = pd.Timestamp.utcnow().tz_localize(None)
    parsed = parsed.tz_localize(None) if getattr(parsed, "tzinfo", None) else parsed
    days = max(0, (today - parsed).days)
    return float(max(0.15, 1.0 - (days / 365)))


def _cluster_rating_weight(row) -> float:
    rating = _row_rating(row)
    if rating >= 5:
        return 1.0
    if rating >= 4.5:
        return 0.9
    if rating >= 4:
        return 0.75
    if rating >= 3.5:
        return 0.35
    if rating >= 3:
        return 0.1
    return 0.0


def _cluster_reader_support(rows: list[pd.Series], recommendations: list[dict]) -> dict:
    completed_rows = [
        row
        for row in rows
        if _candidate_status(row) in {"completed", "reading"}
    ]
    if not completed_rows:
        return {
            "repeated_completed_support": 0.0,
            "recent_support": 0.0,
            "rating_support": 0.0,
            "cluster_reader_intent_score": 0.0,
            "final_display_priority": 0.0,
        }
    repeated_support = min(1.0, len(completed_rows) / 4.0)
    recent_support = sum(_cluster_recency_weight(row) for row in completed_rows) / len(completed_rows)
    rating_support = sum(_cluster_rating_weight(row) for row in completed_rows) / len(completed_rows)
    candidate_quality = max((float(item.get("score") or 0.0) for item in recommendations), default=0.0)
    cluster_reader_intent_score = min(
        1.0,
        (repeated_support * 0.45)
        + (recent_support * 0.30)
        + (rating_support * 0.25),
    )
    confidence = min(1.0, len(rows) / 6.0)
    final_display_priority = min(
        1.0,
        (cluster_reader_intent_score * 0.55)
        + (candidate_quality * 0.30)
        + (confidence * 0.15),
    )
    return {
        "repeated_completed_support": round(repeated_support, 4),
        "recent_support": round(recent_support, 4),
        "rating_support": round(rating_support, 4),
        "cluster_reader_intent_score": round(cluster_reader_intent_score, 4),
        "final_display_priority": round(final_display_priority, 4),
    }


def _rule_score(row, rule: ClusterRule) -> int:
    title = _row_title(row).casefold()
    author_text = _row_author(row).casefold()
    metadata_haystack = " ".join(
        [
            author_text,
            *_row_tags(row),
        ]
    ).casefold()
    haystack = " ".join(
        [
            title,
            author_text,
            *_row_tags(row),
        ]
    ).casefold()
    if rule.excluded_keywords and any(keyword in haystack for keyword in rule.excluded_keywords):
        return 0
    if rule.required_any and not any(keyword in haystack for keyword in rule.required_any):
        return 0
    score = 0
    score += sum(2 for keyword in rule.keywords if keyword in metadata_haystack)
    score += sum(3 for author in rule.authors if author in author_text)
    score += sum(4 for title_keyword in rule.title_keywords if title_keyword in title)
    return score


def _fantasy_evidence(row) -> tuple[bool, str]:
    title = _row_title(row).casefold()
    tags = _row_tags(row)
    genres = _row_genres(row)
    tag_terms = _normalized_terms(tags)
    genre_terms = _normalized_terms(genres)
    haystack = " ".join([title, _row_author(row), *tags]).casefold()
    discovery_cluster = _text(row.get("Discovery Cluster ID")).casefold()
    signal_scores = row.get("_signal_scores")
    signal_scores = signal_scores if isinstance(signal_scores, dict) else {}
    cluster_fit = row.get("_cluster_fit_breakdown")
    cluster_fit = cluster_fit if isinstance(cluster_fit, dict) else {}

    strong_hits = sorted(_contains_term(haystack, FANTASY_STRONG_TERMS))
    title_hits = sorted(_contains_term(title, FANTASY_TITLE_TERMS))
    broad_hits = sorted((tag_terms | genre_terms) & FANTASY_BROAD_TERMS)
    contradictory_hits = sorted(_contains_term(haystack, FANTASY_CONTRADICTORY_TERMS))
    trusted_genre_hits = sorted(genre_terms & FANTASY_STRONG_TERMS)
    explicit_discovery = discovery_cluster in {"fantasy", "fantasy-romance"}
    semantic_similarity = max(
        float(signal_scores.get("candidate_similarity") or 0.0),
        float(cluster_fit.get("cluster_fit") or 0.0),
    )

    if explicit_discovery:
        return True, "explicit_fantasy_discovery_cluster"
    if title_hits:
        return True, f"fantasy_title_signal:{','.join(title_hits[:3])}"
    if contradictory_hits and not strong_hits and semantic_similarity < 0.35:
        return False, f"contradictory_metadata:{','.join(contradictory_hits[:3])}"
    if strong_hits:
        return True, f"strong_fantasy_terms:{','.join(strong_hits[:3])}"
    if semantic_similarity >= 0.55 and (broad_hits or trusted_genre_hits):
        return True, "fantasy_semantic_similarity"
    if broad_hits:
        return False, "broad_fantasy_metadata_only"
    return False, "missing_strong_fantasy_evidence"


def _cluster_evidence_decision(row, rule: ClusterRule) -> tuple[bool, str]:
    if _candidate_status(row) != "not_started":
        return True, "anchor_or_non_candidate"
    if rule.cluster_id == "fantasy":
        return _fantasy_evidence(row)
    if rule.cluster_id.startswith("topic-"):
        return True, "topic_cluster"
    return (_rule_score(row, rule) > 0, "deterministic_rule_match" if _rule_score(row, rule) > 0 else "missing_deterministic_rule_match")


def _single_anchor_strong_overlap(rule: ClusterRule | None, overlap: list[str]) -> bool:
    label = rule.label if rule is not None else ""
    strong_terms = {
        "Criminal justice memoirs": ("criminal justice memoir",),
        "Holocaust memoir and survival": ("holocaust", "concentration camp"),
        "Queer teen graphic romance": ("young adult fiction comics graphic novels lgbt", "love in adolescence"),
        "Queer YA graphic novels": ("young adult fiction comics graphic novels lgbt",),
    }.get(label, ())
    return bool(strong_terms and any(any(term in item for term in strong_terms) for item in overlap))


def _topic_cluster_evidence_decision(
    row,
    anchor_terms: set[str],
    anchor_authors: set[str],
    *,
    rule: ClusterRule | None = None,
    anchor_count: int = 0,
) -> tuple[bool, str]:
    if _candidate_status(row) != "not_started":
        return True, "anchor_or_non_candidate"
    allowed_anchor_terms = _fallback_topic_terms_from_raw(anchor_terms)
    row_terms = _fallback_topic_terms_from_raw({tag.casefold() for tag in _row_tags(row)})
    overlap = sorted(row_terms & allowed_anchor_terms)
    if overlap:
        if anchor_count <= 1 and len(overlap) < 2 and not _single_anchor_strong_overlap(rule, overlap):
            return False, f"single_anchor_weak_topic_overlap:{','.join(overlap[:3])}"
        return True, f"specific_topic_overlap:{','.join(overlap[:3])}"
    author = _row_author(row).casefold()
    if author and author in anchor_authors:
        return True, "topic_author_match"
    return False, "missing_specific_topic_overlap"


def _best_rule(row) -> ClusterRule | None:
    scored = sorted(((_rule_score(row, rule), rule) for rule in CLUSTER_RULES), key=lambda item: item[0], reverse=True)
    if scored and scored[0][0] > 0:
        return scored[0][1]
    return None


def _fallback_rule(row, preferred_terms: set[str] | None = None) -> ClusterRule:
    raw_terms = {tag.casefold() for tag in _row_tags(row)}
    label = _fallback_identity_label(raw_terms, preferred_terms) or "General Reading"
    title_label = label[:1].upper() + label[1:]
    return ClusterRule(
        cluster_id=f"topic-{_slug(label)}",
        label=title_label,
        title=f"Because you enjoyed {title_label}",
        keywords=(label.casefold(),),
    )


def _is_anchor_candidate(row) -> bool:
    status = _candidate_status(row)
    if status != "completed":
        return False
    return _row_rating(row) >= 4.0 or bool(_best_rule(row))


def _anchor_payload(row) -> dict:
    return {
        "title": _row_title(row),
        "author": _row_author(row),
        "rating": _row_rating(row) or None,
        "book_id": str(row.get("Book ID")) if row.get("Book ID") is not None else None,
        "work_id": _text(row.get("Work Key") or row.get("External Work ID")) or None,
        "genres": _list_values(row.get("Genres")),
        "subjects": _list_values(row.get("Subjects")),
    }


def _append_discovery(base_df: pd.DataFrame, discovery_rows: list[dict]) -> pd.DataFrame:
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


def _dominant_terms(rows: list[pd.Series], *, limit: int = 5) -> list[str]:
    counts: Counter[str] = Counter()
    seen_display: dict[str, str] = {}
    for row in rows:
        for tag in _row_tags(row):
            key = tag.casefold()
            if not key:
                continue
            normalized = normalize_specificity_term(tag)
            if normalized in GENERIC_HEADER_TERMS or is_generic_metadata(normalized):
                continue
            specificity = metadata_specificity(tag)
            if specificity < 0.5:
                continue
            counts[key] += max(1, round(specificity * 3))
            seen_display.setdefault(key, tag)
    return [seen_display[key] for key, _count in counts.most_common(limit)]


def _cluster_identity_terms(cluster_id: str, rows: list[pd.Series], *, limit: int = 5) -> list[str]:
    terms = list(CLUSTER_IDENTITY_TERMS.get(cluster_id, ()))
    terms.extend(_dominant_terms(rows, limit=limit * 2))
    seen: set[str] = set()
    filtered: list[str] = []
    for term in terms:
        key = normalize_specificity_term(term)
        if not key or key in seen:
            continue
        if key in GENERIC_HEADER_TERMS or is_generic_metadata(key):
            continue
        if metadata_specificity(term) < 0.5 and term not in CLUSTER_IDENTITY_TERMS.get(cluster_id, ()):
            continue
        seen.add(key)
        filtered.append(term)
        if len(filtered) >= limit:
            break
    return filtered


def _candidate_matches_cluster_raw(row, rule: ClusterRule, anchor_terms: set[str], anchor_authors: set[str]) -> bool:
    if _rule_score(row, rule) > 0:
        return True
    if not rule.cluster_id.startswith("topic-"):
        author = _row_author(row).casefold()
        return bool(author and author in anchor_authors and rule.authors and author in rule.authors)
    row_terms = _fallback_topic_terms_from_raw({tag.casefold() for tag in _row_tags(row)})
    anchor_terms = _fallback_topic_terms_from_raw(anchor_terms)
    if row_terms.intersection(anchor_terms):
        return True
    author = _row_author(row).casefold()
    return bool(author and author in anchor_authors)


def _candidate_matches_cluster(row, rule: ClusterRule, anchor_terms: set[str], anchor_authors: set[str]) -> tuple[bool, str]:
    if not _candidate_matches_cluster_raw(row, rule, anchor_terms, anchor_authors):
        return False, "cluster_rule_miss"
    if rule.cluster_id.startswith("topic-"):
        return _topic_cluster_evidence_decision(row, anchor_terms, anchor_authors, rule=rule)
    return _cluster_evidence_decision(row, rule)


def _cluster_dataframe(
    df: pd.DataFrame,
    anchor_rows: list[pd.Series],
    rule: ClusterRule,
    *,
    diagnostics: ClusterDiagnostics | None = None,
) -> pd.DataFrame:
    anchor_ids = {_row_identity(row) for row in anchor_rows}
    anchor_terms = {tag.casefold() for row in anchor_rows for tag in _row_tags(row)}
    anchor_authors = {_row_author(row).casefold() for row in anchor_rows if _row_author(row)}
    selected: list[dict] = []
    seen: set[str] = set()
    evidence_rejections: list[dict] = []
    before_gate = 0
    after_gate = 0

    for _, row in df.iterrows():
        identity = _row_identity(row)
        if identity in seen:
            continue
        status = _candidate_status(row)
        include = identity in anchor_ids
        if not include and status == "not_started":
            raw_match = _candidate_matches_cluster_raw(row, rule, anchor_terms, anchor_authors)
            if raw_match:
                before_gate += 1
                if rule.cluster_id.startswith("topic-"):
                    allowed, reason = _topic_cluster_evidence_decision(
                        row,
                        anchor_terms,
                        anchor_authors,
                        rule=rule,
                        anchor_count=len(anchor_rows),
                    )
                else:
                    allowed, reason = _candidate_matches_cluster(row, rule, anchor_terms, anchor_authors)
                if allowed:
                    after_gate += 1
                    include = True
                else:
                    evidence_rejections.append({"title": _row_title(row), "reason": reason})
        if not include:
            continue
        seen.add(identity)
        selected.append(row.to_dict())

    if diagnostics is not None:
        diagnostics.candidate_count_before_evidence_gating = before_gate
        diagnostics.candidate_count_after_evidence_gating = after_gate
        diagnostics.evidence_rejections = evidence_rejections[:20]
    return pd.DataFrame(selected, columns=df.columns).astype(object).where(pd.notnull(pd.DataFrame(selected, columns=df.columns)), None) if selected else pd.DataFrame(columns=df.columns)


def _cluster_anchor_groups(df: pd.DataFrame) -> tuple[dict[str, list[pd.Series]], dict[str, ClusterRule]]:
    grouped: defaultdict[str, list[pd.Series]] = defaultdict(list)
    rules_by_id: dict[str, ClusterRule] = {}
    fallback_rows: list[pd.Series] = []
    for _, row in df.iterrows():
        if not _is_anchor_candidate(row):
            continue
        rule = _best_rule(row)
        if rule is None:
            fallback_rows.append(row)
            continue
        grouped[rule.cluster_id].append(row)
        rules_by_id[rule.cluster_id] = rule
    fallback_counts: Counter[str] = Counter()
    for row in fallback_rows:
        fallback_counts.update(_fallback_topic_terms_from_raw({tag.casefold() for tag in _row_tags(row)}))
    preferred_terms = {term for term, count in fallback_counts.items() if count >= 2}
    for row in fallback_rows:
        rule = _fallback_rule(row, preferred_terms)
        grouped[rule.cluster_id].append(row)
        rules_by_id[rule.cluster_id] = rule
    return grouped, rules_by_id


def _fallback_discovery_query(
    rule: ClusterRule,
    anchors: list[pd.Series],
    *,
    strong_local: int,
    target: int,
) -> DiscoveryQuery | None:
    query_by_label = {
        "Queer teen graphic romance": (
            "queer teen graphic romance",
            ("young adult graphic novel", "romance"),
            ("lgbtq", "love in adolescence"),
        ),
        "Queer YA graphic novels": (
            "queer YA graphic novels",
            ("young adult graphic novel",),
            ("lgbtq",),
        ),
        "Contemporary teen relationships": (
            "contemporary teen relationships fiction",
            ("young adult contemporary",),
            ("love in adolescence", "relationships"),
        ),
        "Contemporary teen relationships and mental health": (
            "YA mental health recovery fiction",
            ("young adult contemporary",),
            ("mental health", "relationships"),
        ),
        "Teen grief, identity, and healing": (
            "YA mental health recovery fiction",
            ("young adult contemporary",),
            ("emotional recovery", "identity"),
        ),
        "Middle-grade friendship and moral choices": (
            "middle-grade bullying redemption friendship",
            ("middle grade realistic fiction",),
            ("bullying", "self perception"),
        ),
        "Modern dance biographies": (
            "modern dance biography choreographers",
            ("biography",),
            ("modern dance", "choreographers"),
        ),
        "Criminal justice memoirs": (
            "criminal justice memoir legal reform",
            ("memoir", "nonfiction"),
            ("criminal justice", "legal reform"),
        ),
        "Holocaust memoir and survival": (
            "Holocaust memoir survival",
            ("memoir", "nonfiction"),
            ("holocaust", "survival"),
        ),
        "Science history": (
            "science history nonfiction",
            ("nonfiction",),
            ("science history",),
        ),
        "Political biography": (
            "political biography nonfiction",
            ("biography", "nonfiction"),
            ("political biography",),
        ),
    }
    spec = query_by_label.get(rule.label)
    if spec is None:
        return None
    query, genres, themes = spec
    anchor_titles = tuple(_row_title(row) for row in anchors if _row_title(row))[:2]
    anchor_authors = tuple(_row_author(row) for row in anchors if _row_author(row))[:2]
    anchor_strength = min(1.0, max(0.45, len(anchors) / 2.0))
    priority = anchor_strength + max(0.0, (target - strong_local) * 0.1)
    reason = (
        "underpopulated_synthesized_fallback_cluster "
        f"strong_local_candidates={strong_local} target={target} anchor_count={len(anchors)}"
    )
    return DiscoveryQuery(
        query=query,
        cluster_id=rule.cluster_id,
        anchor_titles=anchor_titles,
        anchor_authors=anchor_authors,
        specific_genres=genres,
        specific_themes=themes,
        confidence=0.88 if len(anchors) >= 2 else 0.76,
        source_anchor=anchor_titles[0] if anchor_titles else None,
        source_anchor_rating=max((_row_rating(row) for row in anchors), default=None),
        cluster_size=len(anchors),
        cluster_priority=priority,
        allocation_reason=reason,
    )


QUALIFIED_LOCAL_SUPPLY_SCORE = 0.40
QUALIFIED_LOCAL_SCORE_READER_INTENT = 0.25
QUALIFIED_LOCAL_SCORE_SIMILARITY = 0.40
QUALIFIED_LOCAL_READER_INTENT = 0.35
QUALIFIED_LOCAL_SIMILARITY = 0.15
QUALIFIED_LOCAL_TARGET = 2
FINAL_ADMISSION_MIN_SCORE = 0.18
FINAL_ADMISSION_MIN_READER_LIKELIHOOD = 0.15
FINAL_ADMISSION_STYLE_JUMP_READER_LIKELIHOOD = 0.70
VAGUE_EXPLANATION_TERMS = (
    "related themes",
    "similar themes",
    "may fit your reading taste",
)
GENERIC_EXPLANATION_TERMS = {
    "related themes",
    "similar themes",
    "reading history",
    "your reading taste",
    "fiction",
    "general",
    "young adult",
    "children s fiction",
    "children's fiction",
    "literature",
    "classic",
    "classics",
    "romance",
    "fantasy",
}


def _strong_continuity_recommendation(item: dict) -> bool:
    breakdown = item.get("score_breakdown") if isinstance(item.get("score_breakdown"), dict) else {}
    if float(breakdown.get("series_continuity_boost") or 0.0) > 0:
        return True
    if float(breakdown.get("series_support") or 0.0) >= 0.8:
        return True
    if float(breakdown.get("author_support") or 0.0) >= 0.85:
        return True
    return False


def _final_admission_float(value: object) -> float:
    try:
        return float(value or 0.0)
    except (TypeError, ValueError):
        return 0.0


def _final_admission_likelihood(item: dict, breakdown: dict, score: float) -> float:
    raw = item.get("reader_likelihood_score")
    if raw is None:
        raw = breakdown.get("reader_likelihood_score")
    if raw is None:
        return score
    return _final_admission_float(raw)


def _recommendation_book(item: dict) -> dict:
    book = item.get("recommended_book") or item.get("book") or {}
    return book if isinstance(book, dict) else {}


def _final_admission_explanation_text(item: dict) -> str:
    explanation = item.get("explanation")
    if isinstance(explanation, dict):
        explanation = explanation.get("primary_reason")
    return _text(item.get("reason") or explanation or item.get("reader_explanation")).casefold()


def _final_admission_terms(values: object) -> set[str]:
    return {
        normalize_specificity_term(value)
        for value in _list_values(values)
        if normalize_specificity_term(value)
    }


def _specific_final_evidence_terms(values: object) -> list[str]:
    terms = sorted(_final_admission_terms(values))
    return [
        term
        for term in terms
        if term not in GENERIC_EXPLANATION_TERMS
        and term not in GENERIC_HEADER_TERMS
        and not is_generic_metadata(term)
        and metadata_specificity(term) >= 0.45
    ]


def _has_final_continuity(item: dict) -> bool:
    return _strong_continuity_recommendation(item)


def _has_specific_explanation_evidence(item: dict) -> bool:
    if _has_final_continuity(item):
        return True
    related_books = item.get("related_books") or item.get("matched_liked_books") or []
    if any(_text(book.get("title") if isinstance(book, dict) else book) for book in related_books):
        return True
    if _specific_final_evidence_terms(item.get("matched_genres") or item.get("genres")):
        return True
    if _specific_final_evidence_terms(item.get("matched_subjects") or item.get("traits") or item.get("subjects")):
        return True
    breakdown = item.get("score_breakdown") if isinstance(item.get("score_breakdown"), dict) else {}
    if int(breakdown.get("qualified_anchor_count") or 0) > 0:
        return True
    if _final_admission_float(breakdown.get("multiple_loved_books_likelihood")) > 0:
        return True
    return False


def _vague_explanation_only(item: dict) -> bool:
    text = _final_admission_explanation_text(item)
    if not text:
        return True
    has_vague_text = any(term in text for term in VAGUE_EXPLANATION_TERMS)
    breakdown = item.get("score_breakdown") if isinstance(item.get("score_breakdown"), dict) else {}
    weak_explanation_penalty = _final_admission_float(breakdown.get("weak_explanation_likelihood_penalty")) > 0
    return (has_vague_text or weak_explanation_penalty) and not _has_specific_explanation_evidence(item)


def _style_jump_penalty_active(item: dict) -> bool:
    breakdown = item.get("score_breakdown") if isinstance(item.get("score_breakdown"), dict) else {}
    strict_penalty_keys = (
        "style_jump_likelihood_penalty",
        "ya_survival_style_jump_likelihood_penalty",
        "political_dystopia_likelihood_penalty",
    )
    if any(_final_admission_float(breakdown.get(key)) > 0 for key in strict_penalty_keys):
        return True
    if _final_admission_float(breakdown.get("prestige_literary_likelihood_penalty")) <= 0:
        return False
    similarity = _final_admission_float(
        breakdown.get("candidate_similarity")
        or breakdown.get("anchor_similarity")
        or breakdown.get("cluster_fit")
    )
    return similarity < 0.6


def _final_admission_decision(item: dict) -> dict:
    breakdown = item.get("score_breakdown") if isinstance(item.get("score_breakdown"), dict) else {}
    score = _final_admission_float(item.get("final_score") if item.get("final_score") is not None else item.get("score"))
    likelihood = _final_admission_likelihood(item, breakdown, score)
    has_continuity = _has_final_continuity(item)
    has_specific_evidence = _has_specific_explanation_evidence(item)
    vague_only = _vague_explanation_only(item)
    thresholds = {
        "min_score": FINAL_ADMISSION_MIN_SCORE,
        "min_reader_likelihood": FINAL_ADMISSION_MIN_READER_LIKELIHOOD,
        "style_jump_reader_likelihood": FINAL_ADMISSION_STYLE_JUMP_READER_LIKELIHOOD,
    }

    if has_continuity and likelihood >= 0.35 and has_specific_evidence:
        return {
            "admitted": True,
            "reason": "continuity",
            "path": "final_continuity_admission",
            "thresholds": thresholds,
            "score": score,
            "reader_likelihood_score": likelihood,
        }
    if score <= 0.001:
        reason = "score_below_minimum"
    elif likelihood < FINAL_ADMISSION_MIN_READER_LIKELIHOOD:
        reason = "reader_likelihood_below_minimum"
    elif vague_only:
        reason = "vague_explanation_without_specific_evidence"
    elif _style_jump_penalty_active(item) and likelihood < FINAL_ADMISSION_STYLE_JUMP_READER_LIKELIHOOD:
        reason = "style_jump_reader_likelihood_below_minimum"
    elif score < FINAL_ADMISSION_MIN_SCORE:
        reason = "score_below_minimum"
    elif not has_specific_evidence:
        reason = "missing_specific_explanation_evidence"
    else:
        return {
            "admitted": True,
            "reason": "quality",
            "path": "final_quality_admission",
            "thresholds": thresholds,
            "score": score,
            "reader_likelihood_score": likelihood,
        }
    return {
        "admitted": False,
        "reason": reason,
        "path": "final_universal_admission_rejection",
        "thresholds": thresholds,
        "score": score,
        "reader_likelihood_score": likelihood,
    }


def _apply_final_admission(items: list[dict]) -> tuple[list[dict], list[dict]]:
    admitted: list[dict] = []
    rejected: list[dict] = []
    for item in items:
        decision = _final_admission_decision(item)
        enriched = {
            **item,
            "final_admission_decision": "admitted" if decision["admitted"] else "rejected",
            "final_admission_reason": decision["reason"],
            "final_admission_path": decision["path"],
            "final_admission_thresholds": decision["thresholds"],
        }
        if decision["admitted"]:
            admitted.append(enriched)
        else:
            book = _recommendation_book(item)
            rejected.append(
                {
                    "title": item.get("title") or book.get("title"),
                    "source": item.get("provider") or item.get("discovery_source") or item.get("source_type"),
                    "reason": decision["reason"],
                    "score": decision["score"],
                    "reader_likelihood_score": decision["reader_likelihood_score"],
                }
            )
    return admitted, rejected


def _qualified_supply_recommendation(item: dict) -> bool:
    if _strong_continuity_recommendation(item):
        return True
    breakdown = item.get("score_breakdown") if isinstance(item.get("score_breakdown"), dict) else {}
    score = float(item.get("score") or item.get("final_score") or 0.0)
    reader_intent = float(breakdown.get("reader_intent_score") or 0.0)
    similarity = float(
        breakdown.get("candidate_similarity")
        or breakdown.get("anchor_similarity")
        or breakdown.get("cluster_fit")
        or 0.0
    )
    mismatch = float(breakdown.get("reader_mismatch_penalty") or 0.0)
    if mismatch >= 0.08:
        return False
    if score >= QUALIFIED_LOCAL_SUPPLY_SCORE:
        return (
            reader_intent >= QUALIFIED_LOCAL_SCORE_READER_INTENT
            or similarity >= QUALIFIED_LOCAL_SCORE_SIMILARITY
        )
    return reader_intent >= QUALIFIED_LOCAL_READER_INTENT and similarity >= QUALIFIED_LOCAL_SIMILARITY


def _cluster_local_supply_quality(
    cluster_df: pd.DataFrame,
    rule: ClusterRule,
    anchors: list[pd.Series],
    *,
    target: int,
    style: str = "external_first",
) -> dict:
    raw_local = 0
    if not cluster_df.empty:
        raw_local = int(
            cluster_df.apply(
                lambda row: _candidate_status(row) == "not_started" and _row_in_library(row),
                axis=1,
            ).sum()
        )
    anchor_terms = {tag.casefold() for row in anchors for tag in _row_tags(row)}
    anchor_authors = {_row_author(row).casefold() for row in anchors if _row_author(row)}

    def cluster_admission_filter(row):
        if rule.cluster_id.startswith("topic-"):
            return _topic_cluster_evidence_decision(row, anchor_terms, anchor_authors, rule=rule, anchor_count=len(anchors))
        return _cluster_evidence_decision(row, rule)

    recommendations = build_recommendations(
        cluster_df,
        top_n=max(target, QUALIFIED_LOCAL_TARGET),
        style=style,
        candidate_evidence_filter=cluster_admission_filter,
    ) if not cluster_df.empty else []
    local_recommendations = [item for item in recommendations if bool(item.get("in_library", True))]
    strong_continuity = sum(1 for item in recommendations if _strong_continuity_recommendation(item))
    qualified = sum(1 for item in local_recommendations if _qualified_supply_recommendation(item))
    required = min(QUALIFIED_LOCAL_TARGET, target)
    requested = max(0, target - qualified)
    needs_external = qualified < required
    reason = (
        f"quality_aware_supply raw_local_candidates={raw_local} "
        f"qualified_local_candidates={qualified} strong_continuity_candidates={strong_continuity} "
        f"target={target} required_qualified={required}"
    )
    return {
        "raw_local_candidate_count": raw_local,
        "qualified_local_candidate_count": qualified,
        "strong_continuity_candidate_count": strong_continuity,
        "requested_external_candidate_count": requested if needs_external else 0,
        "needs_external": needs_external,
        "allocation_reason": reason,
        "local_recommendation_titles": [item.get("title") for item in local_recommendations],
    }


def _local_cluster_discovery_needs(
    base_df: pd.DataFrame,
    *,
    max_per_cluster: int,
) -> tuple[set[str], dict[str, str], list[DiscoveryQuery], list[dict]]:
    if base_df.empty:
        return set(), {}, [], []
    grouped, rules_by_id = _cluster_anchor_groups(base_df)
    preferred: set[str] = set()
    reasons: dict[str, str] = {}
    supplemental_queries: list[DiscoveryQuery] = []
    allocation_diagnostics: list[dict] = []
    for cluster_id, rows in grouped.items():
        if cluster_id == "topic-general-reading":
            continue
        if cluster_id.startswith("topic-") and len(rows) < 2 and not _high_confidence_fallback_rule(rules_by_id[cluster_id]):
            continue
        rule = rules_by_id[cluster_id]
        anchors = sorted(
            rows,
            key=lambda row: (-_rule_score(row, rule), -_row_rating(row), _row_title(row).casefold()),
        )[:MAX_ANCHORS_PER_CLUSTER]
        diagnostics = ClusterDiagnostics(cluster_id=cluster_id, title=_cluster_title(rule, anchors), anchor_count=len(anchors))
        cluster_df = _cluster_dataframe(base_df, anchors, rule, diagnostics=diagnostics)
        supply = _cluster_local_supply_quality(cluster_df, rule, anchors, target=max_per_cluster)
        allocation_diagnostics.append(
            {
                "cluster_id": cluster_id,
                "title": diagnostics.title,
                **supply,
            }
        )
        qualified_local = int(supply["qualified_local_candidate_count"])
        raw_local = int(supply["raw_local_candidate_count"])
        if supply["needs_external"] and not cluster_id.startswith("topic-"):
            preferred.add(cluster_id)
            reasons[cluster_id] = f"{supply['allocation_reason']} anchor_count={len(anchors)}"
        if supply["needs_external"] and _high_confidence_fallback_rule(rule):
            query = _fallback_discovery_query(rule, anchors, strong_local=qualified_local, target=max_per_cluster)
            if query is not None:
                supplemental_queries.append(query)
                reasons[cluster_id] = query.allocation_reason or "underpopulated_synthesized_fallback_cluster"
        elif raw_local < max_per_cluster and _high_confidence_fallback_rule(rule):
            query = _fallback_discovery_query(rule, anchors, strong_local=qualified_local, target=max_per_cluster)
            if query is not None:
                supplemental_queries.append(query)
                reasons[cluster_id] = query.allocation_reason or "underpopulated_synthesized_fallback_cluster"
    supplemental_queries.sort(key=lambda query: (-query.cluster_size, -query.cluster_priority, query.cluster_id))
    return preferred, reasons, supplemental_queries[:2], allocation_diagnostics


def _unique_recommendations(items: list[dict]) -> list[dict]:
    unique: list[dict] = []
    seen: set[str] = set()
    for item in items:
        book = item.get("recommended_book") or item.get("book") or {}
        identity = _text(
            item.get("recommendation_id")
            or item.get("work_id")
            or book.get("recommendation_id")
            or book.get("work_id")
            or item.get("isbn")
            or book.get("isbn")
            or item.get("title")
        ).casefold()
        if not identity or identity in seen:
            continue
        seen.add(identity)
        unique.append(item)
    return unique


def _section_item_identity(item: dict) -> str:
    book = item.get("recommended_book") or item.get("book") or {}
    return _text(
        item.get("recommendation_id")
        or item.get("work_id")
        or book.get("recommendation_id")
        or book.get("work_id")
        or item.get("isbn")
        or book.get("isbn")
        or item.get("title")
    ).casefold()


def flatten_clustered_recommendations(
    clusters: list[dict],
    *,
    top_n: int = 10,
    max_per_cluster: int = DEFAULT_RECOMMENDATIONS_PER_CLUSTER,
) -> list[dict]:
    queues = [
        (
            cluster["cluster_id"],
            deque(cluster.get("recommendations", [])[:max_per_cluster]),
        )
        for cluster in clusters
        if cluster.get("recommendations")
    ]
    flattened: list[dict] = []
    seen: set[str] = set()
    while queues and len(flattened) < top_n:
        next_queues = []
        for cluster_id, queue in queues:
            while queue:
                item = queue.popleft()
                identity = _text(item.get("recommendation_id") or item.get("work_id") or item.get("title")).casefold()
                if identity in seen:
                    continue
                enriched = {**item, "taste_cluster_id": cluster_id}
                flattened.append(enriched)
                seen.add(identity)
                break
            if queue:
                next_queues.append((cluster_id, queue))
            if len(flattened) >= top_n:
                break
        queues = next_queues
    return flattened


def build_reading_clusters_from_dataframe(
    df: pd.DataFrame,
    *,
    top_n: int = 3,
    style: str = "balanced",
    max_per_cluster: int = DEFAULT_RECOMMENDATIONS_PER_CLUSTER,
    feedback_records: list[dict] | None = None,
    excluded_identities: set[str] | None = None,
    discovery_diagnostics: object | None = None,
) -> list[dict]:
    if df.empty:
        return []

    grouped, rules_by_id = _cluster_anchor_groups(df)

    clusters: list[dict] = []
    normalized_style = _normalize_style(style)
    for cluster_id, rows in grouped.items():
        rule = rules_by_id[cluster_id]
        if cluster_id == "topic-general-reading":
            continue
        if cluster_id.startswith("topic-") and len(rows) < 2 and not _high_confidence_fallback_rule(rules_by_id[cluster_id]):
            continue
        anchors = sorted(
            rows,
            key=lambda row: (-_rule_score(row, rule), -_row_rating(row), _row_title(row).casefold()),
        )[:MAX_ANCHORS_PER_CLUSTER]
        title = _cluster_title(rule, anchors)
        diagnostics = ClusterDiagnostics(
            cluster_id=cluster_id,
            title=title,
            anchor_count=len(anchors),
        )
        cluster_df = _cluster_dataframe(df, anchors, rule, diagnostics=diagnostics)
        if not cluster_df.empty:
            diagnostics.strong_local_candidate_count = int(
                cluster_df.apply(
                    lambda row: _candidate_status(row) == "not_started" and _row_in_library(row),
                    axis=1,
                ).sum()
            )
            diagnostics.discovered_candidate_count = int(
                cluster_df.apply(
                    lambda row: _candidate_status(row) == "not_started" and not _row_in_library(row),
                    axis=1,
                ).sum()
            )
        if discovery_diagnostics is not None:
            structured_queries = getattr(discovery_diagnostics, "structured_queries", []) or []
            diagnostics.discovery_queries_allocated = [
                query.get("query")
                for query in structured_queries
                if isinstance(query, dict) and query.get("cluster_id") == cluster_id
            ]
            allocation_items = getattr(discovery_diagnostics, "cluster_allocation_diagnostics", []) or []
            allocation = next(
                (
                    item
                    for item in allocation_items
                    if isinstance(item, dict) and item.get("cluster_id") == cluster_id
                ),
                {},
            )
            diagnostics.raw_local_candidate_count = int(allocation.get("raw_local_candidate_count") or diagnostics.strong_local_candidate_count)
            diagnostics.qualified_local_candidate_count = int(allocation.get("qualified_local_candidate_count") or 0)
            diagnostics.strong_continuity_candidate_count = int(allocation.get("strong_continuity_candidate_count") or 0)
            diagnostics.requested_external_candidate_count = int(allocation.get("requested_external_candidate_count") or 0)
            diagnostics.allocation_reason = allocation.get("allocation_reason")
            provider_queries = getattr(discovery_diagnostics, "provider_query_diagnostics", []) or []
            cluster_provider_queries = [
                item
                for item in provider_queries
                if isinstance(item, dict) and item.get("cluster_id") == cluster_id
            ]
            diagnostics.hardcover_queried = any(item.get("provider") == "hardcover" for item in cluster_provider_queries)
            diagnostics.external_results_returned = sum(int(item.get("result_count") or 0) for item in cluster_provider_queries)
        builder_diagnostics: dict = {}
        anchor_terms = {tag.casefold() for row in anchors for tag in _row_tags(row)}
        anchor_authors = {_row_author(row).casefold() for row in anchors if _row_author(row)}

        def cluster_admission_filter(row, cluster_rule=rule, terms=anchor_terms, authors=anchor_authors):
            if cluster_rule.cluster_id.startswith("topic-"):
                return _topic_cluster_evidence_decision(row, terms, authors, rule=cluster_rule, anchor_count=len(anchors))
            return _cluster_evidence_decision(row, cluster_rule)

        recommendations = build_recommendations(
            cluster_df,
            top_n=max(top_n, max_per_cluster),
            style=normalized_style,
            feedback_records=feedback_records,
            excluded_identities=excluded_identities,
            candidate_evidence_filter=cluster_admission_filter,
            diagnostics=builder_diagnostics,
        )
        recommendations = _unique_recommendations(recommendations)
        recommendations, final_admission_rejections = _apply_final_admission(recommendations)
        recommendations = recommendations[:max_per_cluster]
        if not recommendations:
            if final_admission_rejections:
                diagnostics.external_rejection_reasons = final_admission_rejections[:20]
                logger.info("recommendation_cluster_diagnostics %s", diagnostics.to_dict())
            continue
        diagnostics.backfill_candidate_count = int(builder_diagnostics.get("backfill_candidate_count") or 0)
        diagnostics.final_recommendation_count = len(recommendations)
        diagnostics.external_results_admitted = sum(1 for item in recommendations if item.get("external_discovery"))
        diagnostics.external_rejection_reasons = [
            *[
                item
                for item in (diagnostics.evidence_rejections or [])
                if isinstance(item, dict)
            ],
            *final_admission_rejections,
        ][:20]
        support = _cluster_reader_support(rows, recommendations)
        diagnostics.repeated_completed_support = support["repeated_completed_support"]
        diagnostics.recent_support = support["recent_support"]
        diagnostics.rating_support = support["rating_support"]
        diagnostics.cluster_reader_intent_score = support["cluster_reader_intent_score"]
        diagnostics.final_display_priority = support["final_display_priority"]
        terms = _cluster_identity_terms(cluster_id, rows)
        logger.info("recommendation_cluster_diagnostics %s", diagnostics.to_dict())
        clusters.append(
            {
                "cluster_id": cluster_id,
                "title": title,
                "reading_identity": title,
                "why": (
                    f"Clustered from {len(rows)} completed or highly rated books"
                    + (f" around {', '.join(terms[:3])}." if terms else ".")
                ),
                "anchors": [_anchor_payload(row) for row in anchors],
                "dominant_genres": terms,
                "dominant_themes": terms,
                "cluster_size": len(rows),
                "diagnostics": diagnostics.to_dict(),
                "recommendations": recommendation_sections_response(recommendations, style=normalized_style)["sections"][0]["items"]
                if recommendations
                else [],
            }
        )

    clusters.sort(
        key=lambda cluster: (
            -float((cluster.get("diagnostics") or {}).get("final_display_priority") or 0.0),
            -float((cluster.get("diagnostics") or {}).get("cluster_reader_intent_score") or 0.0),
            -max((float(item.get("score") or 0.0) for item in cluster["recommendations"]), default=0.0),
            -cluster["cluster_size"],
            cluster["title"].casefold(),
        )
    )
    seen_recommendation_identities: set[str] = set()
    deduped_clusters: list[dict] = []
    for cluster in clusters:
        recommendations = []
        for item in cluster.get("recommendations", []):
            identity = _section_item_identity(item)
            if identity and identity in seen_recommendation_identities:
                continue
            if identity:
                seen_recommendation_identities.add(identity)
            recommendations.append(item)
        if recommendations:
            cluster = {**cluster, "recommendations": recommendations}
            diagnostics = dict(cluster.get("diagnostics") or {})
            diagnostics["final_recommendation_count"] = len(recommendations)
            diagnostics["external_results_admitted"] = sum(1 for item in recommendations if item.get("external_discovery"))
            cluster["diagnostics"] = diagnostics
            deduped_clusters.append(cluster)
    clusters = deduped_clusters
    return clusters


def _cluster_title(rule: ClusterRule, anchors: list[pd.Series]) -> str:
    anchor_titles = {_row_title(row).casefold() for row in anchors}
    if rule.cluster_id == "ya-dystopian-speculative" and "the hunger games" in anchor_titles:
        return "Survival and dystopian rebellion"
    if rule.cluster_id == "ya-mystery-thriller" and "the naturals" in anchor_titles:
        return "Criminal profilers and teen mysteries"
    if rule.cluster_id == "contemporary-romance-new-adult" and "book lovers" in anchor_titles:
        return "Contemporary romance and academic rivals"
    if rule.cluster_id == "literary-classics":
        return "Literary relationships and moral conflict"
    if rule.cluster_id == "fantasy":
        return "Magic, quests, and found family"
    identity_terms = CLUSTER_IDENTITY_TERMS.get(rule.cluster_id)
    if identity_terms:
        label = " and ".join(identity_terms[:2])
        return label[:1].upper() + label[1:]
    return rule.label


def get_clustered_recommendations(
    db: Session,
    user_id: UUID,
    *,
    top_n: int = 3,
    style: str = "balanced",
    max_per_cluster: int = DEFAULT_RECOMMENDATIONS_PER_CLUSTER,
    include_discovery: bool = True,
) -> list[dict]:
    books = get_books_for_recommendation(db, user_id, MAX_RECOMMENDATION_BOOKS)
    base_df = books_to_dataframe(books, user_id)
    discovery_rows: list[dict] = []
    discovery_diagnostics = None
    if include_discovery:
        preferred_cluster_ids, allocation_reasons, supplemental_queries, allocation_diagnostics = _local_cluster_discovery_needs(
            base_df,
            max_per_cluster=max_per_cluster,
        )
        discovery_rows, discovery_diagnostics = discovery_candidate_rows(
            db,
            user_id,
            books,
            limit=max(50, top_n * max_per_cluster * 5),
            allow_external=True,
            preferred_cluster_ids=preferred_cluster_ids,
            allocation_reasons=allocation_reasons,
            supplemental_query_specs=supplemental_queries,
            allocation_diagnostics=allocation_diagnostics,
        )
    df = _append_discovery(base_df, discovery_rows)
    active_feedback = active_feedback_for_user(db, user_id)
    return build_reading_clusters_from_dataframe(
        df,
        top_n=top_n,
        style=style,
        max_per_cluster=max_per_cluster,
        feedback_records=feedback_to_ranking_records(active_feedback),
        excluded_identities=active_not_interested_identities(db, user_id),
        discovery_diagnostics=discovery_diagnostics,
    )
