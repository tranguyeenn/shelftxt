from __future__ import annotations

import logging
import os
import re
import time
from collections import Counter
from dataclasses import dataclass, field
from datetime import date
from difflib import SequenceMatcher
from uuid import UUID

from sqlalchemy.orm import Session

from backend.db.models import Book
from backend.services import book_search
from backend.services import external_candidate_exploration
from backend.services.canonical_work import (
    canonical_work_for_book,
    canonical_work_for_result,
    completed_component_identities,
    owned_component_identities,
)
from backend.services.series_metadata import (
    book_series_metadata,
    canonical_series_identity,
    next_series_candidates,
    series_metadata_for_result,
    series_order_decision_for_result,
)
from backend.services.status import normalize_status
from backend.services.metadata_specificity import (
    is_generic_metadata,
    metadata_specificity,
    normalize_specificity_term,
    specific_terms,
)

logger = logging.getLogger(__name__)
DEBUG_TITLES = {"killer instinct", "all in", "bad blood"}

DEFAULT_DISCOVERY_MAX_QUERIES = 3
MAX_LOCAL_DISCOVERY_CANDIDATES = 250
DEFAULT_DISCOVERY_RESULTS_PER_QUERY = 20
DEFAULT_EXTERNAL_DISCOVERY_TIMEOUT_SECONDS = 4.0
DEFAULT_EXTERNAL_DISCOVERY_CANDIDATE_LIMIT = 30
MIN_DISCOVERY_CONFIDENCE = 0.35


def _run_aggregation(
    query: str,
    local_candidates: list[dict],
    *,
    allow_external: bool = True,
    result_limit: int | None = None,
    timeout_seconds: float | None = None,
):
    return book_search._run_aggregation(
        query,
        local_candidates,
        allow_external=allow_external,
        result_limit=result_limit,
        timeout_seconds=timeout_seconds,
    )


def explore_external_candidates(
    library_books: list[Book],
    *,
    limit: int = 80,
    result_limit_per_source: int | None = None,
    deadline: float | None = None,
):
    return external_candidate_exploration.explore_external_candidates(
        library_books,
        limit=limit,
        result_limit_per_source=result_limit_per_source,
        deadline=deadline,
    )


def _env_int(name: str, default: int, *, minimum: int, maximum: int) -> int:
    try:
        value = int(os.getenv(name, str(default)))
    except (TypeError, ValueError):
        return default
    return max(minimum, min(maximum, value))


def discovery_max_queries() -> int:
    return _env_int("DISCOVERY_MAX_QUERIES", DEFAULT_DISCOVERY_MAX_QUERIES, minimum=1, maximum=8)


def discovery_results_per_query() -> int:
    return _env_int("DISCOVERY_RESULTS_PER_QUERY", DEFAULT_DISCOVERY_RESULTS_PER_QUERY, minimum=5, maximum=30)


def external_discovery_candidate_limit() -> int:
    return _env_int(
        "EXTERNAL_DISCOVERY_CANDIDATE_LIMIT",
        DEFAULT_EXTERNAL_DISCOVERY_CANDIDATE_LIMIT,
        minimum=5,
        maximum=60,
    )


def external_discovery_timeout_seconds() -> float:
    try:
        value = float(os.getenv("EXTERNAL_DISCOVERY_TIMEOUT_SECONDS", str(DEFAULT_EXTERNAL_DISCOVERY_TIMEOUT_SECONDS)))
    except (TypeError, ValueError):
        return DEFAULT_EXTERNAL_DISCOVERY_TIMEOUT_SECONDS
    return max(0.25, min(10.0, value))


@dataclass(frozen=True)
class DiscoveryQuery:
    query: str
    cluster_id: str
    anchor_titles: tuple[str, ...] = ()
    anchor_authors: tuple[str, ...] = ()
    specific_genres: tuple[str, ...] = ()
    specific_themes: tuple[str, ...] = ()
    confidence: float = 0.5
    source_anchor: str | None = None
    source_anchor_rating: float | None = None
    cluster_size: int = 0
    cluster_priority: float = 0.0
    allocation_reason: str | None = None

    def to_dict(self) -> dict:
        return {
            "query": self.query,
            "cluster_id": self.cluster_id,
            "anchor_titles": list(self.anchor_titles),
            "anchor_authors": list(self.anchor_authors),
            "specific_genres": list(self.specific_genres),
            "specific_themes": list(self.specific_themes),
            "confidence": round(self.confidence, 3),
            "source_anchor": self.source_anchor,
            "source_anchor_rating": self.source_anchor_rating,
            "cluster_size": self.cluster_size,
            "cluster_priority": round(self.cluster_priority, 3),
            "allocation_reason": self.allocation_reason,
        }


def _is_debug_title(value: object) -> bool:
    return str(value or "").strip().casefold() in DEBUG_TITLES


def _log_debug_title(stage: str, title: object, **fields) -> None:
    if not _is_debug_title(title):
        return
    logger.info(
        "recommendation_title_trace stage=%s title=%s %s",
        stage,
        str(title or "").strip(),
        " ".join(f"{key}={value}" for key, value in fields.items()),
    )


@dataclass
class DiscoveryDiagnostics:
    library_candidate_count: int = 0
    open_library_candidate_count: int = 0
    librarything_candidate_count: int = 0
    other_provider_candidate_count: int = 0
    external_candidate_count: int = 0
    external_provider_attempts: int = 0
    external_provider_successes: int = 0
    deduplicated_external_count: int = 0
    feedback_removed_count: int = 0
    final_eligible_candidate_count: int = 0
    final_source_breakdown: dict[str, int] = field(default_factory=dict)
    provider_failures: list[dict] = field(default_factory=list)
    queries: list[str] = field(default_factory=list)
    structured_queries: list[dict] = field(default_factory=list)
    provider_results_returned: int = 0
    duplicate_removed_count: int = 0
    series_order_removed_count: int = 0
    low_provider_confidence_count: int = 0
    translated_edition_rejections: list[dict] = field(default_factory=list)
    collection_rejections: list[dict] = field(default_factory=list)
    series_order_rejections: list[dict] = field(default_factory=list)
    exploration_modes_used: list[dict] = field(default_factory=list)
    external_exploration_candidate_count: int = 0
    broad_exploration_candidate_count: int = 0
    exact_anchor_query_candidate_count: int = 0
    canonical_works_after_dedupe: int = 0
    already_in_library_count: int = 0
    genuinely_new_work_count: int = 0
    elapsed_ms: float = 0.0

    def to_dict(self) -> dict:
        return {
            "library_candidate_count": self.library_candidate_count,
            "open_library_candidate_count": self.open_library_candidate_count,
            "librarything_candidate_count": self.librarything_candidate_count,
            "other_provider_candidate_count": self.other_provider_candidate_count,
            "external_candidate_count": self.external_candidate_count,
            "external_provider_attempts": self.external_provider_attempts,
            "external_provider_successes": self.external_provider_successes,
            "deduplicated_external_count": self.deduplicated_external_count,
            "feedback_removed_count": self.feedback_removed_count,
            "final_eligible_candidate_count": self.final_eligible_candidate_count,
            "final_source_breakdown": self.final_source_breakdown,
            "provider_failures": self.provider_failures,
            "queries": self.queries,
            "structured_queries": self.structured_queries,
            "provider_results_returned": self.provider_results_returned,
            "duplicate_removed_count": self.duplicate_removed_count,
            "series_order_removed_count": self.series_order_removed_count,
            "low_provider_confidence_count": self.low_provider_confidence_count,
            "translated_edition_rejections": self.translated_edition_rejections,
            "collection_rejections": self.collection_rejections,
            "series_order_rejections": self.series_order_rejections,
            "exploration_modes_used": self.exploration_modes_used,
            "external_exploration_candidate_count": self.external_exploration_candidate_count,
            "broad_exploration_candidate_count": self.broad_exploration_candidate_count,
            "exact_anchor_query_candidate_count": self.exact_anchor_query_candidate_count,
            "canonical_works_after_dedupe": self.canonical_works_after_dedupe,
            "already_in_library_count": self.already_in_library_count,
            "genuinely_new_work_count": self.genuinely_new_work_count,
            "elapsed_ms": round(self.elapsed_ms, 2),
        }


def _normalize_isbn(value: object) -> str | None:
    cleaned = re.sub(r"[^0-9Xx]", "", str(value or "")).upper()
    return cleaned if len(cleaned) in {10, 13} else None


def _normalize_text(value: object) -> str:
    return " ".join(re.sub(r"[^a-z0-9]+", " ", str(value or "").casefold()).split())


def _lead_author(value: object) -> str:
    return str(value or "").split(",", 1)[0].strip()


def _result_author(result: dict) -> str:
    authors = result.get("authors") or []
    return str(authors[0]).strip() if authors else "Unknown author"


def _title_author_key(title: object, author: object) -> tuple[str, str]:
    return (_normalize_text(title), _normalize_text(_lead_author(author)))


def _book_isbns(book: Book) -> set[str]:
    values = {_normalize_isbn(book.isbn_uid)}
    metadata = book.book_metadata or {}
    librarything = metadata.get("librarything") if isinstance(metadata, dict) else None
    if isinstance(librarything, dict):
        values.update(_normalize_isbn(value) for value in librarything.get("related_isbns") or [])
    return {value for value in values if value}


def _result_isbns(result: dict) -> set[str]:
    values = {_normalize_isbn(result.get("isbn_uid"))}
    values.update(_normalize_isbn(value) for value in result.get("related_isbns") or [])
    return {value for value in values if value}


def _library_identity_sets(library_books: list[Book]) -> dict[str, set]:
    return {
        "isbns": {isbn for book in library_books for isbn in _book_isbns(book)},
        "works": {str(book.work_key).strip() for book in library_books if str(book.work_key or "").strip()},
        "editions": {str(book.edition_key).strip() for book in library_books if str(book.edition_key or "").strip()},
        "canonical_works": {canonical_work_for_book(book).canonical_work_identity for book in library_books},
        "completed_canonical_works": completed_component_identities(library_books),
        "owned_canonical_works": owned_component_identities(library_books),
        "title_authors": {
            _title_author_key(book.title, book.authors)
            for book in library_books
            if _normalize_text(book.title)
        },
    }


def _result_duplicates_library(result: dict, identities: dict[str, set]) -> bool:
    result_isbns = _result_isbns(result)
    if result_isbns and result_isbns.intersection(identities["isbns"]):
        return True
    if result.get("work_key") and result["work_key"] in identities["works"]:
        return True
    if result.get("edition_key") and result["edition_key"] in identities["editions"]:
        return True
    canonical = canonical_work_for_result(result)
    if canonical.collection_type == "single_work" and canonical.canonical_work_identity in identities["canonical_works"]:
        return True
    title_author = _title_author_key(result.get("title"), _result_author(result))
    if title_author in identities["title_authors"]:
        return True
    return False


def _canonical_rejection_reason(result: dict, identities: dict[str, set]) -> tuple[str, dict] | None:
    canonical = canonical_work_for_result(result)
    base = {
        "title": result.get("title"),
        "canonical_work_identity": canonical.canonical_work_identity,
        "canonical_title": canonical.canonical_title,
        "original_title": canonical.original_title,
        "language": canonical.language,
        "edition_identity": canonical.edition_identity,
        "collection_type": canonical.collection_type,
    }
    if canonical.collection_type == "single_work" and canonical.canonical_work_identity in identities["canonical_works"]:
        return (
            "translated_or_alternate_edition_duplicate",
            {
                **base,
                "reason": "canonical_work_already_in_library",
            },
        )
    if canonical.collection_type in {"omnibus", "box_set"}:
        component_ids = [component.canonical_work_identity for component in canonical.component_works]
        completed = sorted(set(component_ids) & identities["completed_canonical_works"])
        owned = sorted(set(component_ids) & identities["owned_canonical_works"])
        meaningful_owned = len(owned) >= 1 and len(owned) / max(1, len(component_ids)) >= 0.34
        if completed:
            return (
                "collection_duplicates_completed_component",
                {
                    **base,
                    "reason": "collection_contains_completed_component",
                    "component_work_ids": component_ids,
                    "completed_component_work_ids": completed,
                    "owned_component_work_ids": owned,
                },
            )
        if meaningful_owned:
            return (
                "collection_duplicates_owned_components",
                {
                    **base,
                    "reason": "collection_contains_owned_components",
                    "component_work_ids": component_ids,
                    "owned_component_work_ids": owned,
                },
            )
    return None


def _external_duplicate_key(result: dict) -> tuple[str, str]:
    canonical = canonical_work_for_result(result)
    if canonical.collection_type == "single_work" and canonical.canonical_work_identity:
        return ("canonical_work", canonical.canonical_work_identity)
    work = str(result.get("work_key") or "").strip()
    if work:
        return ("work", work)
    edition = str(result.get("edition_key") or "").strip()
    if edition:
        return ("edition", edition)
    isbns = sorted(_result_isbns(result))
    if isbns:
        return ("isbn", isbns[0])
    title, author = _title_author_key(result.get("title"), _result_author(result))
    return ("title_author", f"{title}|{author}")


def _book_to_local_candidate(book: Book) -> dict:
    metadata = book.book_metadata or {}
    librarything = metadata.get("librarything") if isinstance(metadata, dict) else None
    series = book_series_metadata(book)
    result = {
        "title": book.title,
        "authors": [value.strip() for value in (book.authors or "").split(",") if value.strip()],
        "isbn_uid": book.isbn_uid,
        "description": book.description,
        "cover_url": book.cover_url,
        "total_pages": book.total_pages,
        "subjects": book.subjects or [],
        "genres": book.genres or [],
        "first_publish_year": book.first_publish_year,
        "metadata_source": book.metadata_source or "local_catalog",
        "work_key": book.work_key,
        "edition_key": book.edition_key,
        "language": book.language,
        "related_isbns": librarything.get("related_isbns", []) if isinstance(librarything, dict) else [],
        "already_in_library": False,
        "confidence_score": 0.65,
    }
    if series:
        result.update(series)
        result["series"] = series
    return result


def _candidate_search_text(candidate: dict) -> str:
    parts = [
        candidate.get("title"),
        " ".join(candidate.get("authors") or []),
        candidate.get("description"),
        " ".join(candidate.get("subjects") or []),
        " ".join(candidate.get("genres") or []),
        candidate.get("work_key"),
        candidate.get("edition_key"),
    ]
    return _normalize_text(" ".join(str(part or "") for part in parts))


def _local_candidate_matches_query(candidate: dict, query: DiscoveryQuery) -> bool:
    text = _candidate_search_text(candidate)
    if not text:
        return False
    strong_terms = specific_terms(
        [
            *query.anchor_titles,
            *query.anchor_authors,
            *query.specific_genres,
            *query.specific_themes,
        ],
        minimum=0.5,
    )
    if not strong_terms:
        return False
    for term in strong_terms:
        normalized = _normalize_text(term)
        if normalized and normalized in text:
            return True
    return False


def _metadata_values(book: Book, field_name: str) -> list[str]:
    value = getattr(book, field_name, None) or []
    return [str(item).strip() for item in value if str(item).strip()]


def _recency_weight(book: Book) -> float:
    finished = book.end_date or book.last_date_read
    if not finished:
        return 0.75
    days = max(0, (date.today() - finished).days)
    return max(0.35, 1.0 - (days / 365))


def _rating_weight(book: Book) -> float:
    try:
        rating = float(book.star_rating or 0)
    except (TypeError, ValueError):
        rating = 0.0
    if rating >= 4:
        return 2.0
    if rating >= 3:
        return 1.25
    return 0.0


def _cluster_for_book(book: Book) -> tuple[str, str, tuple[str, ...], tuple[str, ...]]:
    text = " ".join(
        [
            book.title or "",
            book.authors or "",
            *[str(value) for value in book.genres or []],
            *[str(value) for value in book.subjects or []],
        ]
    ).casefold()
    if any(value in text for value in ("naturals", "jennifer lynn barnes", "criminal profiling", "serial murders", "mystery")):
        return ("ya-mystery-thriller", "YA Mystery / Thriller", ("young adult mystery", "thriller"), ("criminal profiling",))
    if any(value in text for value in ("book lovers", "emily henry", "ali hazelwood", "contemporary romance", "women in stem", "romantic comedy")):
        return ("contemporary-romance-new-adult", "Contemporary Romance", ("contemporary romance",), ("women in STEM",))
    if any(value in text for value in ("hunger games", "suzanne collins", "dystopian", "rebellion", "maze runner", "scythe")):
        return ("ya-dystopian-speculative", "YA Dystopian / Speculative", ("dystopian",), ("survival", "rebellion"))
    if any(value in text for value in ("normal people", "sally rooney", "relationship fiction", "coming of age")):
        return ("literary-relationship-fiction", "Literary Relationship Fiction", ("literary relationship fiction",), ("relationships", "coming of age"))
    if any(value in text for value in ("frankenstein", "mary shelley", "gothic fiction")):
        return ("gothic-classics", "Gothic Classics", ("gothic fiction", "literary classics"), ("scientific ambition", "monstrosity"))
    if any(value in text for value in ("anna karenina", "tolstoy", "russian literature", "classic", "classics", "literary")):
        return ("literary-classics", "Literary Classics", ("literary fiction",), ("russian realism", "psychological classics"))
    if any(value in text for value in ("john locke", "political philosophy", "social contract", "toleration", "liberty")):
        return ("political-philosophy", "Political Philosophy", ("political philosophy",), ("social contract", "liberty"))
    if any(value in text for value in ("wonder", "r.j. palacio", "r j palacio", "craniofacial", "empathy")):
        return ("middle-grade-empathy", "Middle Grade Empathy", ("middle grade realistic fiction",), ("empathy", "visible difference"))
    if any(value in text for value in ("fantasy", "magic", "faeries", "court of", "amari")):
        return ("fantasy", "Fantasy", ("fantasy",), ("magic",))
    tags = specific_terms([*(book.genres or []), *(book.subjects or [])], minimum=0.5)
    label = tags[0] if tags else "specific-books"
    return (f"topic-{_normalize_text(label).replace(' ', '-')}", label.title(), tuple(tags[:2]), tuple(tags[2:5]))


def _book_anchor_weight(book: Book) -> float:
    return _rating_weight(book) * _recency_weight(book)


def _numeric_rating(book: Book) -> float | None:
    try:
        return float(book.star_rating) if book.star_rating is not None else None
    except (TypeError, ValueError):
        return None


def _cluster_priority(books: list[Book], genres: tuple[str, ...], themes: tuple[str, ...]) -> tuple[float, str]:
    cluster_size = len(books)
    anchor_strength = min(1.0, sum(_book_anchor_weight(book) or 0.25 for book in books) / 4.0)
    specific_signal_count = len(specific_terms([*genres, *themes], minimum=0.5))
    cluster_coherence = min(1.0, (cluster_size / 3.0) + (0.12 * specific_signal_count))
    ratings = [_numeric_rating(book) for book in books if _numeric_rating(book) is not None]
    positive_rating_strength = min(1.0, (sum(max(0.0, rating - 3.0) for rating in ratings) / max(1, len(ratings))) / 2.0) if ratings else 0.55
    recency_factor = min(1.0, sum(_recency_weight(book) for book in books) / max(1, cluster_size))
    discovery_need = 0.7 + (0.1 * min(3, cluster_size))
    priority = anchor_strength * cluster_coherence * max(0.35, positive_rating_strength) * recency_factor * discovery_need
    reason = (
        f"anchor_strength={anchor_strength:.2f} cluster_coherence={cluster_coherence:.2f} "
        f"positive_rating_strength={positive_rating_strength:.2f} recency_factor={recency_factor:.2f} "
        f"discovery_need={discovery_need:.2f}"
    )
    return priority, reason


def _with_allocation(query: DiscoveryQuery, strongest: list[Book], cluster_size: int, priority: float, reason: str) -> DiscoveryQuery:
    anchor = strongest[0] if strongest else None
    return DiscoveryQuery(
        query=query.query,
        cluster_id=query.cluster_id,
        anchor_titles=query.anchor_titles,
        anchor_authors=query.anchor_authors,
        specific_genres=query.specific_genres,
        specific_themes=query.specific_themes,
        confidence=query.confidence,
        source_anchor=anchor.title if anchor else None,
        source_anchor_rating=_numeric_rating(anchor) if anchor else None,
        cluster_size=cluster_size,
        cluster_priority=priority,
        allocation_reason=reason,
    )


def _cluster_anchor_priority(book: Book, cluster_id: str) -> int:
    text = " ".join(
        [
            book.title or "",
            book.authors or "",
            *[str(value) for value in book.genres or []],
            *[str(value) for value in book.subjects or []],
        ]
    ).casefold()
    if cluster_id == "ya-dystopian-speculative":
        if any(value in text for value in ("hunger games", "suzanne collins", "dystopian", "rebellion", "maze runner", "scythe")):
            return 3
        return 0
    if cluster_id == "ya-mystery-thriller":
        if any(value in text for value in ("naturals", "jennifer lynn barnes", "criminal profiling")):
            return 3
    if cluster_id == "contemporary-romance-new-adult":
        if any(value in text for value in ("emily henry", "ali hazelwood", "book lovers", "women in stem")):
            return 3
    return 1


def _query_is_specific(query: str, query_data: DiscoveryQuery) -> bool:
    terms = [*query_data.anchor_titles, *query_data.anchor_authors, *query_data.specific_genres, *query_data.specific_themes]
    return any(metadata_specificity(term) >= 0.5 for term in terms)


def _clean_query_parts(parts: list[str]) -> list[str]:
    cleaned: list[str] = []
    seen: set[str] = set()
    for part in parts:
        text = " ".join(str(part or "").split())
        if not text:
            continue
        key = normalize_specificity_term(text)
        if key in seen:
            continue
        if is_generic_metadata(key):
            continue
        seen.add(key)
        cleaned.append(text)
    return cleaned


def _structured_discovery_queries(library_books: list[Book]) -> list[DiscoveryQuery]:
    completed = [
        book
        for book in library_books
        if normalize_status(
            book.read_status,
            progress_percent=float(book.progress_percent or 0),
            pages_read=int(book.pages_read or 0),
        )
        == "completed"
        and (book.star_rating is not None and float(book.star_rating or 0) >= 3.5)
    ]
    current_or_tbr = [
        book
        for book in library_books
        if normalize_status(
            book.read_status,
            progress_percent=float(book.progress_percent or 0),
            pages_read=int(book.pages_read or 0),
        )
        in {"reading", "not_started"}
    ]
    anchors = completed + current_or_tbr
    if not anchors:
        return [
            DiscoveryQuery(
                query="recent acclaimed mystery romance dystopian",
                cluster_id="cold-start",
                specific_genres=("mystery", "romance", "dystopian"),
                confidence=0.35,
            )
        ]

    grouped: dict[str, list[Book]] = {}
    cluster_meta: dict[str, tuple[str, tuple[str, ...], tuple[str, ...]]] = {}
    for book in anchors:
        base = _book_anchor_weight(book)
        if base <= 0 and normalize_status(book.read_status) == "completed":
            continue
        cluster_id, _label, default_genres, default_themes = _cluster_for_book(book)
        grouped.setdefault(cluster_id, []).append(book)
        cluster_meta[cluster_id] = (_label, default_genres, default_themes)

    queries: list[DiscoveryQuery] = []
    max_queries = discovery_max_queries()
    cluster_candidates: list[tuple[float, str, list[DiscoveryQuery], list[Book], str]] = []
    for cluster_id, books in grouped.items():
        label, default_genres, default_themes = cluster_meta[cluster_id]
        strongest = sorted(
            books,
            key=lambda book: (-_cluster_anchor_priority(book, cluster_id), -(_book_anchor_weight(book) or 0.35), book.title or ""),
        )[:3]
        authors = []
        for book in strongest:
            author = _lead_author(book.authors)
            if author and author.casefold() != "unknown author" and author not in authors:
                authors.append(author)
        titles = [book.title for book in strongest if book.title][:2]
        tags = specific_terms(
            [tag for book in strongest for tag in [*_metadata_values(book, "genres"), *_metadata_values(book, "subjects")]],
            minimum=0.5,
        )
        genres = tuple(_clean_query_parts([*default_genres, *tags[:2]]))[:3]
        themes = tuple(_clean_query_parts([*default_themes, *tags[2:5]]))[:3]
        confidence = min(0.98, 0.55 + (0.12 * len(strongest)) + (0.08 if genres else 0) + (0.08 if themes else 0))
        priority, reason = _cluster_priority(books, genres, themes)
        candidates: list[DiscoveryQuery] = []
        if authors and genres:
            candidates.append(DiscoveryQuery(" ".join(_clean_query_parts([authors[0], *genres[:2]])), cluster_id, tuple(titles[:1]), tuple(authors[:1]), genres, themes, confidence))
        if themes and genres:
            candidates.append(DiscoveryQuery(" ".join(_clean_query_parts([*themes[:2], *genres[:1]])), cluster_id, tuple(titles[:1]), tuple(authors[:1]), genres, themes, confidence - 0.04))
        if titles and authors:
            candidates.append(DiscoveryQuery(f"books like {titles[0]} {authors[0]}", cluster_id, tuple(titles[:1]), tuple(authors[:1]), genres, themes, confidence - 0.02))
        if cluster_id == "literary-classics" and authors:
            candidates.append(DiscoveryQuery(" ".join(_clean_query_parts(["Russian realism", "psychological classics", authors[0]])), cluster_id, tuple(titles[:1]), tuple(authors[:1]), genres, themes, confidence - 0.05))
        valid_candidates = [
            _with_allocation(candidate, strongest, len(books), priority, reason)
            for candidate in candidates
            if candidate.query and _query_is_specific(candidate.query, candidate)
        ]
        if valid_candidates:
            cluster_candidates.append((priority, cluster_id, valid_candidates, strongest, reason))

    cluster_candidates.sort(key=lambda item: (item[0], len(grouped.get(item[1], []))), reverse=True)
    max_per_cluster = max(1, min(2, round(max_queries * 0.35)))
    for priority, cluster_id, candidates, strongest, reason in cluster_candidates:
        if len(queries) >= max_queries:
            break
        if len(strongest) <= 1 and priority < 0.08:
            continue
        if cluster_id == "topic-specific-books" and not (candidates[0].specific_genres or candidates[0].specific_themes):
            continue
        used_for_cluster = sum(1 for query in queries if query.cluster_id == cluster_id)
        if used_for_cluster >= max_per_cluster:
            continue
        queries.append(candidates[0])

    for priority, cluster_id, candidates, strongest, reason in cluster_candidates:
        if len(queries) >= max_queries:
            break
        if len(candidates) < 2 or priority < 0.15:
            continue
        used_for_cluster = sum(1 for query in queries if query.cluster_id == cluster_id)
        if used_for_cluster >= max_per_cluster:
            continue
        next_query = candidates[used_for_cluster]
        if all(query.query.casefold() != next_query.query.casefold() for query in queries):
            queries.append(next_query)

    for cluster_id, books in grouped.items():
        if len(queries) >= max_queries:
            break
        if any(query.cluster_id == cluster_id for query in queries):
            continue
        label, default_genres, default_themes = cluster_meta[cluster_id]
        strongest = sorted(
            books,
            key=lambda book: (-_cluster_anchor_priority(book, cluster_id), -(_book_anchor_weight(book) or 0.35), book.title or ""),
        )[:1]
        if not strongest:
            continue
        author = _lead_author(strongest[0].authors)
        parts = _clean_query_parts([author, *(default_themes or default_genres), *(default_genres or ())])
        priority, reason = _cluster_priority(books, tuple(default_genres), tuple(default_themes))
        if len(books) <= 1 and priority < 0.08:
            continue
        query = DiscoveryQuery(
            " ".join(parts),
            cluster_id,
            (strongest[0].title,) if strongest[0].title else (),
            (author,) if author else (),
            tuple(default_genres),
            tuple(default_themes),
            0.62,
        )
        if query.query and _query_is_specific(query.query, query):
            queries.append(_with_allocation(query, strongest, len(books), priority, reason))

    deduped: list[DiscoveryQuery] = []
    seen: set[str] = set()
    for query in queries:
        clean = " ".join(str(query.query).split())
        key = clean.casefold()
        if clean and key not in seen:
            seen.add(key)
            deduped.append(query)
        if len(deduped) >= max_queries:
            break
    return deduped


def _discovery_queries(library_books: list[Book]) -> list[str]:
    return [query.query for query in _structured_discovery_queries(library_books)]


def _external_id(result: dict) -> str:
    return (
        str(result.get("work_key") or "").strip()
        or str(result.get("edition_key") or "").strip()
        or str(result.get("isbn_uid") or "").strip()
        or f"external:{_normalize_text(result.get('title'))}:{_normalize_text(_result_author(result))}"
    )


def _result_to_row(result: dict) -> dict:
    external_id = _external_id(result)
    series = series_metadata_for_result(result) or (result.get("series") if isinstance(result.get("series"), dict) else {})
    canonical = canonical_work_for_result(result)
    decision = result.get("series_order_decision") if isinstance(result.get("series_order_decision"), dict) else {}
    series_name = result.get("series_name") or series.get("series_name")
    row = {
        "Title": result.get("title") or "Untitled",
        "Authors": _result_author(result),
        "ISBN/UID": external_id,
        "Read Status": "to-read",
        "Star Rating": None,
        "Last Date Read": None,
        "Start Date": None,
        "End Date": None,
        "Progress (%)": 0,
        "Pages Read": 0,
        "Total Pages": result.get("total_pages"),
        "Description": result.get("description"),
        "Cover URL": result.get("cover_url"),
        "Subjects": result.get("subjects") or [],
        "Genres": result.get("genres") or [],
        "First Publish Year": result.get("first_publish_year"),
        "Language": result.get("language"),
        "Work Key": result.get("work_key"),
        "Edition Key": result.get("edition_key"),
        "metadata": {
            "external": {
                "isbn_uid": result.get("isbn_uid"),
                "related_isbns": result.get("related_isbns") or [],
                "publisher": result.get("publisher"),
                "publish_date": result.get("publish_date"),
                "confidence_score": result.get("confidence_score"),
            }
        },
        "In Library": False,
        "Source Type": "external_discovery",
        "Discovery Source": result.get("metadata_source") or "metadata_aggregation",
        "Library Status": None,
        "Book ID": None,
        "External ID": external_id,
        "External Work ID": result.get("work_key"),
        "External Edition ID": result.get("edition_key"),
        "External ISBN": result.get("isbn_uid"),
        "Series Name": series_name,
        "Canonical Series Identity": canonical_series_identity(series_name),
        "Series Position": result.get("series_position") or series.get("series_position"),
        "Series Position Label": result.get("series_position_label") or series.get("series_position_label"),
        "Series Type": result.get("series_type") or series.get("series_type"),
        "Series Books": result.get("series_books") or series.get("series_books") or [],
        "Series Source": result.get("series_source") or series.get("series_source"),
        "Series Confidence": result.get("series_confidence") or series.get("series_confidence"),
        "Is Main Series Entry": decision.get("is_main_series_entry"),
        "User Owned Series Positions": decision.get("user_owned_positions") or [],
        "User Completed Series Positions": decision.get("user_completed_positions") or [],
        "Required Next Series Position": decision.get("required_next_position"),
        "Series Order Decision": decision.get("decision"),
        "Series Order Rejection Reason": decision.get("reason") if decision.get("decision") == "rejected" else None,
        "Series Publication Order": result.get("series_publication_order") or series.get("series_publication_order"),
        "Series Chronological Order": result.get("series_chronological_order") or series.get("series_chronological_order"),
        "Discovery Query": result.get("discovery_query"),
        "Discovery Cluster ID": result.get("discovery_cluster_id"),
        "Discovery Query Confidence": result.get("discovery_query_confidence"),
        "Exploration Mode": result.get("exploration_mode"),
        "Exploration Source": result.get("exploration_source"),
        "Provider Rank": result.get("provider_rank"),
        "Novelty Score": result.get("novelty_score"),
        "Discovery Anchor Titles": result.get("discovery_anchor_titles") or [],
        "Discovery Anchor Authors": result.get("discovery_anchor_authors") or [],
        "Discovery Specific Genres": result.get("discovery_specific_genres") or [],
        "Discovery Specific Themes": result.get("discovery_specific_themes") or [],
        "Provider Metadata Confidence": result.get("confidence_score"),
        "Canonical Work Identity": canonical.canonical_work_identity,
        "Canonical Title": canonical.canonical_title,
        "Original Title": canonical.original_title,
        "Edition Identity": canonical.edition_identity,
        "Collection Type": canonical.collection_type,
        "Component Work IDs": [component.canonical_work_identity for component in canonical.component_works],
        "Component Titles": [component.title for component in canonical.component_works],
        "Component Series Positions": [component.series_position for component in canonical.component_works],
        "Duplicate Checks": result.get("duplicate_checks") or [],
        "Series Order Check": result.get("series_order_check") or decision.get("decision"),
        "Inclusion Reason": result.get("inclusion_reason") or "eligible_after_canonical_duplicate_and_series_checks",
    }
    _log_debug_title(
        "normalized",
        row["Title"],
        source=row["Discovery Source"],
        work_id=row["External Work ID"],
        isbn=row["External ISBN"],
        series=row["Series Name"],
        position=row["Series Position"],
    )
    return row


def _stronger_result(left: dict, right: dict) -> dict:
    left_score = float(left.get("confidence_score") or 0.0)
    right_score = float(right.get("confidence_score") or 0.0)
    if right_score > left_score:
        return right
    left_title = _normalize_text(left.get("title"))
    right_title = _normalize_text(right.get("title"))
    if left_title and right_title and SequenceMatcher(None, right_title, left_title).ratio() > 0.98:
        return left
    return left


def _novelty_score(result: dict, library_books: list[Book]) -> float:
    canonical = canonical_work_for_result(result)
    library_authors = {_normalize_text(_lead_author(book.authors)) for book in library_books if _lead_author(book.authors)}
    library_terms = {
        normalize_specificity_term(term)
        for book in library_books
        for term in [*(book.genres or []), *(book.subjects or [])]
        if metadata_specificity(term) >= 0.5
    }
    result_terms = {
        normalize_specificity_term(term)
        for term in [*(result.get("genres") or []), *(result.get("subjects") or [])]
        if metadata_specificity(term) >= 0.5
    }
    author = _normalize_text(_result_author(result))
    external_only_bonus = 0.35 if result.get("metadata_source") == "open_library" else 0.2
    new_author_bonus = 0.25 if author and author not in library_authors else 0.0
    adjacent_theme_bonus = 0.25 if result_terms and result_terms.intersection(library_terms) else 0.1
    excessive_distance_penalty = 0.25 if result_terms and library_terms and not result_terms.intersection(library_terms) else 0.0
    collection_penalty = 0.2 if canonical.collection_type in {"omnibus", "box_set", "anthology"} else 0.0
    return max(0.0, min(1.0, external_only_bonus + new_author_bonus + adjacent_theme_bonus - excessive_distance_penalty - collection_penalty))


def _prepare_external_result(result: dict, library_books: list[Book]) -> dict:
    prepared = dict(result)
    prepared["novelty_score"] = _novelty_score(prepared, library_books)
    prepared.setdefault("duplicate_checks", [
        "open_library_work_id",
        "provider_work_id",
        "isbn_relationships",
        "translated_original_title_aliases",
        "normalized_author_canonical_title",
    ])
    return prepared


def discovery_candidate_rows(
    db: Session,
    user_id: UUID,
    library_books: list[Book],
    *,
    limit: int = 40,
    allow_external: bool = True,
    include_broad_exploration: bool = True,
) -> tuple[list[dict], DiscoveryDiagnostics]:
    started = time.perf_counter()
    diagnostics = DiscoveryDiagnostics()
    query_specs = _structured_discovery_queries(library_books)
    if allow_external:
        query_specs = query_specs[:discovery_max_queries()]
    diagnostics.queries = [query.query for query in query_specs]
    diagnostics.structured_queries = [query.to_dict() for query in query_specs]
    if not query_specs:
        diagnostics.elapsed_ms = (time.perf_counter() - started) * 1000
        return [], diagnostics

    local_books = (
        db.query(Book)
        .filter(Book.user_id.is_(None))
        .order_by(Book.id.desc())
        .limit(MAX_LOCAL_DISCOVERY_CANDIDATES)
        .all()
    )
    local_candidates = [_book_to_local_candidate(book) for book in local_books]
    identities = _library_identity_sets(library_books)
    by_key: dict[tuple[str, str], dict] = {}
    deduped_count = 0
    for result in next_series_candidates(library_books):
        key = _external_duplicate_key(result)
        if key in by_key:
            by_key[key] = _stronger_result(by_key[key], result)
            deduped_count += 1
        else:
            by_key[key] = result

    results_per_query = discovery_results_per_query()
    deadline = time.perf_counter() + external_discovery_timeout_seconds() if allow_external else None
    for query_spec in query_specs:
        remaining = None if deadline is None else deadline - time.perf_counter()
        if remaining is not None and remaining <= 0:
            diagnostics.provider_failures.append(
                {"source": "external_discovery", "outcome": "timeout", "error_type": "DiscoveryBudgetExceeded"}
            )
            break
        query = query_spec.query
        query_local_candidates = [
            candidate for candidate in local_candidates if _local_candidate_matches_query(candidate, query_spec)
        ]
        try:
            aggregation = _run_aggregation(
                query,
                query_local_candidates,
                allow_external=allow_external,
                result_limit=results_per_query,
                timeout_seconds=max(0.0, remaining) if remaining is not None else None,
            )
        except TypeError as exc:
            if "timeout_seconds" in str(exc):
                try:
                    aggregation = _run_aggregation(
                        query,
                        query_local_candidates,
                        allow_external=allow_external,
                        result_limit=results_per_query,
                    )
                except TypeError as nested_exc:
                    if "result_limit" in str(nested_exc):
                        aggregation = _run_aggregation(query, query_local_candidates, allow_external=allow_external)
                    elif "allow_external" in str(nested_exc):
                        aggregation = _run_aggregation(query, query_local_candidates)
                    else:
                        raise
            elif "result_limit" in str(exc):
                try:
                    aggregation = _run_aggregation(query, query_local_candidates, allow_external=allow_external)
                except TypeError as nested_exc:
                    if "allow_external" not in str(nested_exc):
                        raise
                    aggregation = _run_aggregation(query, query_local_candidates)
            elif "allow_external" in str(exc):
                aggregation = _run_aggregation(query, query_local_candidates)
            else:
                raise
        external_outcomes = [outcome for outcome in aggregation.outcomes if outcome.source != "local"]
        diagnostics.external_provider_attempts += len(external_outcomes)
        diagnostics.external_provider_successes += sum(1 for outcome in external_outcomes if outcome.success)
        diagnostics.open_library_candidate_count += sum(
            outcome.result_count for outcome in external_outcomes if outcome.source == "open_library"
        )
        diagnostics.librarything_candidate_count += sum(
            outcome.result_count for outcome in external_outcomes if outcome.source == "librarything"
        )
        diagnostics.other_provider_candidate_count += sum(
            outcome.result_count
            for outcome in external_outcomes
            if outcome.source not in {"open_library", "librarything"}
        )
        diagnostics.provider_failures.extend(
            {
                "source": outcome.source,
                "outcome": outcome.outcome,
                "error_type": outcome.error_type,
            }
            for outcome in external_outcomes
            if not outcome.success and outcome.outcome not in {"disabled", "not_configured", "empty_success"}
        )

        logger.info(
            "recommendation_discovery_query query=%s cluster=%s confidence=%.3f results=%s provider_results_per_query=%s",
            query_spec.query,
            query_spec.cluster_id,
            query_spec.confidence,
            len(aggregation.results),
            results_per_query,
        )
        diagnostics.provider_results_returned += len(aggregation.results)

        for raw_result in aggregation.results[:results_per_query]:
            result = {
                **raw_result,
                "discovery_query": query_spec.query,
                "discovery_cluster_id": query_spec.cluster_id,
                "discovery_query_confidence": query_spec.confidence,
                "discovery_anchor_titles": list(query_spec.anchor_titles),
                "discovery_anchor_authors": list(query_spec.anchor_authors),
                "discovery_specific_genres": list(query_spec.specific_genres),
                "discovery_specific_themes": list(query_spec.specific_themes),
            }
            result = _prepare_external_result(result, library_books)
            diagnostics.exact_anchor_query_candidate_count += 1
            resolved_series = series_metadata_for_result(result)
            if resolved_series:
                result.update(resolved_series)
                result["series"] = resolved_series
            _log_debug_title(
                "provider_result",
                result.get("title"),
                source=result.get("metadata_source"),
                work_id=result.get("work_key"),
                isbn=result.get("isbn_uid"),
                series=result.get("series_name") or ((result.get("series") or {}).get("series_name") if isinstance(result.get("series"), dict) else None),
                position=result.get("series_position") or ((result.get("series") or {}).get("series_position") if isinstance(result.get("series"), dict) else None),
            )
            if result.get("already_in_library") or _result_duplicates_library(result, identities):
                _log_debug_title("excluded", result.get("title"), reason="ownership_duplicate", source=result.get("metadata_source"))
                deduped_count += 1
                diagnostics.duplicate_removed_count += 1
                canonical = canonical_work_for_result(result)
                if canonical.collection_type == "single_work":
                    diagnostics.translated_edition_rejections.append(
                        {
                            "title": result.get("title"),
                            "reason": "canonical_or_provider_duplicate",
                            "canonical_work_identity": canonical.canonical_work_identity,
                            "canonical_title": canonical.canonical_title,
                            "language": canonical.language,
                        }
                    )
                continue
            canonical_rejection = _canonical_rejection_reason(result, identities)
            if canonical_rejection:
                reason, payload = canonical_rejection
                _log_debug_title("excluded", result.get("title"), reason=reason, source=result.get("metadata_source"))
                if payload.get("collection_type") in {"omnibus", "box_set"}:
                    diagnostics.collection_rejections.append(payload)
                else:
                    diagnostics.translated_edition_rejections.append(payload)
                deduped_count += 1
                diagnostics.duplicate_removed_count += 1
                continue
            series_decision = series_order_decision_for_result(result, library_books)
            result["series_order_decision"] = series_decision
            if series_decision["decision"] == "rejected":
                _log_debug_title("excluded", result.get("title"), reason="series_order_skip", source=result.get("metadata_source"))
                deduped_count += 1
                diagnostics.series_order_removed_count += 1
                diagnostics.series_order_rejections.append(
                    {
                        "title": result.get("title"),
                        "series_name": series_decision.get("series_name"),
                        "canonical_series_identity": series_decision.get("canonical_series_identity"),
                        "series_position": series_decision.get("series_position"),
                        "series_source": series_decision.get("series_source"),
                        "series_confidence": series_decision.get("series_confidence"),
                        "user_owned_positions": series_decision.get("user_owned_positions"),
                        "user_completed_positions": series_decision.get("user_completed_positions"),
                        "required_next_position": series_decision.get("required_next_position"),
                        "decision": "rejected",
                        "reason": series_decision.get("reason"),
                    }
                )
                continue
            if float(result.get("confidence_score") or 0.0) < MIN_DISCOVERY_CONFIDENCE:
                diagnostics.low_provider_confidence_count += 1
            key = _external_duplicate_key(result)
            if key in by_key:
                _log_debug_title("deduplicated", result.get("title"), key=key, source=result.get("metadata_source"))
                by_key[key] = _stronger_result(by_key[key], result)
                deduped_count += 1
                diagnostics.duplicate_removed_count += 1
            else:
                result["series_order_check"] = series_decision.get("decision") or "passed"
                result["inclusion_reason"] = "eligible_after_canonical_duplicate_and_series_checks"
                by_key[key] = result
            if allow_external and len(by_key) >= external_discovery_candidate_limit():
                break
        if allow_external and len(by_key) >= external_discovery_candidate_limit():
            break

    budget_remaining = None if deadline is None else deadline - time.perf_counter()
    if (
        allow_external
        and include_broad_exploration
        and not diagnostics.provider_failures
        and (budget_remaining is None or budget_remaining > 0.25)
        and len(by_key) < external_discovery_candidate_limit()
    ):
        exploration_results, exploration_diagnostics = explore_external_candidates(
            library_books,
            limit=min(
                external_discovery_candidate_limit() - len(by_key),
                max(limit, results_per_query * max(1, len(query_specs))),
            ),
            result_limit_per_source=results_per_query,
            deadline=deadline,
        )
        diagnostics.exploration_modes_used = exploration_diagnostics.exploration_requests
        diagnostics.external_exploration_candidate_count = exploration_diagnostics.total_open_library_candidates_fetched
        diagnostics.broad_exploration_candidate_count = exploration_diagnostics.broad_exploration_candidates
        diagnostics.open_library_candidate_count += exploration_diagnostics.total_open_library_candidates_fetched
        diagnostics.provider_results_returned += exploration_diagnostics.total_open_library_candidates_fetched
        for raw_result in exploration_results:
            result = _prepare_external_result(raw_result, library_books)
            resolved_series = series_metadata_for_result(result)
            if resolved_series:
                result.update(resolved_series)
                result["series"] = resolved_series
            if result.get("already_in_library") or _result_duplicates_library(result, identities):
                deduped_count += 1
                diagnostics.duplicate_removed_count += 1
                diagnostics.already_in_library_count += 1
                canonical = canonical_work_for_result(result)
                if canonical.collection_type == "single_work":
                    diagnostics.translated_edition_rejections.append(
                        {
                            "title": result.get("title"),
                            "reason": "canonical_or_provider_duplicate",
                            "canonical_work_identity": canonical.canonical_work_identity,
                            "canonical_title": canonical.canonical_title,
                            "language": canonical.language,
                        }
                    )
                continue
            canonical_rejection = _canonical_rejection_reason(result, identities)
            if canonical_rejection:
                reason, payload = canonical_rejection
                if payload.get("collection_type") in {"omnibus", "box_set"}:
                    diagnostics.collection_rejections.append(payload)
                else:
                    diagnostics.translated_edition_rejections.append(payload)
                deduped_count += 1
                diagnostics.duplicate_removed_count += 1
                continue
            series_decision = series_order_decision_for_result(result, library_books)
            result["series_order_decision"] = series_decision
            if series_decision["decision"] == "rejected":
                deduped_count += 1
                diagnostics.series_order_removed_count += 1
                diagnostics.series_order_rejections.append(
                    {
                        "title": result.get("title"),
                        "series_name": series_decision.get("series_name"),
                        "canonical_series_identity": series_decision.get("canonical_series_identity"),
                        "series_position": series_decision.get("series_position"),
                        "series_source": series_decision.get("series_source"),
                        "series_confidence": series_decision.get("series_confidence"),
                        "user_owned_positions": series_decision.get("user_owned_positions"),
                        "user_completed_positions": series_decision.get("user_completed_positions"),
                        "required_next_position": series_decision.get("required_next_position"),
                        "decision": "rejected",
                        "reason": series_decision.get("reason"),
                    }
                )
                continue
            if float(result.get("confidence_score") or 0.0) < MIN_DISCOVERY_CONFIDENCE:
                diagnostics.low_provider_confidence_count += 1
            key = _external_duplicate_key(result)
            if key in by_key:
                by_key[key] = _stronger_result(by_key[key], result)
                deduped_count += 1
                diagnostics.duplicate_removed_count += 1
            else:
                result["series_order_check"] = series_decision.get("decision") or "passed"
                result["inclusion_reason"] = "eligible_after_broad_exploration_canonical_duplicate_and_series_checks"
                by_key[key] = result
            if len(by_key) >= external_discovery_candidate_limit():
                break

    rows = [_result_to_row(result) for result in by_key.values()]
    rows = rows[:limit]
    diagnostics.external_candidate_count = len(rows)
    diagnostics.deduplicated_external_count = deduped_count
    diagnostics.canonical_works_after_dedupe = len(by_key)
    diagnostics.genuinely_new_work_count = sum(1 for result in by_key.values() if not _result_duplicates_library(result, identities))
    diagnostics.elapsed_ms = (time.perf_counter() - started) * 1000
    logger.info("recommendation_discovery_diagnostics %s", diagnostics.to_dict())
    return rows, diagnostics
