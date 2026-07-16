from __future__ import annotations

import logging
import os
import re
import time
from dataclasses import dataclass, field
from datetime import date

from backend.db.models import Book
from backend.services.book_search import (
    OPEN_LIBRARY_SEARCH_TIMEOUT_SECONDS,
    _http_get_json,
    _normalized_result,
)
from backend.services.metadata_normalization import filter_specific_subjects, subjects_to_genres
from backend.services.metadata_specificity import specific_terms
from backend.services.status import normalize_status

logger = logging.getLogger(__name__)

DEFAULT_EXTERNAL_EXPLORATION_SUBJECTS_PER_DIMENSION = 4
DEFAULT_EXTERNAL_EXPLORATION_RESULTS_PER_SOURCE = 12


def _env_int(name: str, default: int, *, minimum: int, maximum: int) -> int:
    try:
        value = int(os.getenv(name, str(default)))
    except (TypeError, ValueError):
        return default
    return max(minimum, min(maximum, value))


def exploration_subjects_per_dimension() -> int:
    return _env_int(
        "EXTERNAL_EXPLORATION_SUBJECTS_PER_DIMENSION",
        DEFAULT_EXTERNAL_EXPLORATION_SUBJECTS_PER_DIMENSION,
        minimum=1,
        maximum=8,
    )


def exploration_results_per_source() -> int:
    return _env_int(
        "EXTERNAL_EXPLORATION_RESULTS_PER_SOURCE",
        DEFAULT_EXTERNAL_EXPLORATION_RESULTS_PER_SOURCE,
        minimum=3,
        maximum=25,
    )


@dataclass(frozen=True)
class TasteDimension:
    cluster_id: str
    specific_genres: tuple[str, ...] = ()
    specific_themes: tuple[str, ...] = ()
    positive_authors: tuple[str, ...] = ()
    negative_signals: tuple[str, ...] = ()
    semantic_centroid_terms: tuple[str, ...] = ()
    evidence_strength: float = 0.0
    anchor_titles: tuple[str, ...] = ()

    def to_dict(self) -> dict:
        return {
            "cluster_id": self.cluster_id,
            "specific_genres": list(self.specific_genres),
            "specific_themes": list(self.specific_themes),
            "positive_authors": list(self.positive_authors),
            "negative_signals": list(self.negative_signals),
            "semantic_centroid_terms": list(self.semantic_centroid_terms),
            "evidence_strength": round(self.evidence_strength, 3),
            "anchor_titles": list(self.anchor_titles),
        }


@dataclass
class ExternalExplorationDiagnostics:
    taste_dimensions: list[dict] = field(default_factory=list)
    exploration_requests: list[dict] = field(default_factory=list)
    total_open_library_candidates_fetched: int = 0
    subject_exploration_candidates: int = 0
    adjacent_exploration_candidates: int = 0
    author_neighborhood_candidates: int = 0
    related_work_candidates: int = 0
    exact_anchor_query_candidates: int = 0
    broad_exploration_candidates: int = 0
    elapsed_ms: float = 0.0

    def to_dict(self) -> dict:
        return {
            "taste_dimensions": self.taste_dimensions,
            "exploration_requests": self.exploration_requests,
            "total_open_library_candidates_fetched": self.total_open_library_candidates_fetched,
            "subject_exploration_candidates": self.subject_exploration_candidates,
            "adjacent_exploration_candidates": self.adjacent_exploration_candidates,
            "author_neighborhood_candidates": self.author_neighborhood_candidates,
            "related_work_candidates": self.related_work_candidates,
            "exact_anchor_query_candidates": self.exact_anchor_query_candidates,
            "broad_exploration_candidates": self.broad_exploration_candidates,
            "elapsed_ms": round(self.elapsed_ms, 2),
        }


def _norm(value: object) -> str:
    return " ".join(re.sub(r"[^a-z0-9]+", " ", str(value or "").casefold()).split())


def _lead_author(value: object) -> str:
    return str(value or "").split(",", 1)[0].strip()


def _status(book: Book) -> str:
    return normalize_status(
        book.read_status,
        progress_percent=float(book.progress_percent or 0),
        pages_read=int(book.pages_read or 0),
    )


def _rating(book: Book) -> float:
    try:
        return float(book.star_rating or 0)
    except (TypeError, ValueError):
        return 0.0


def _recency(book: Book) -> float:
    finished = book.end_date or book.last_date_read
    if not finished:
        return 0.75
    days = max(0, (date.today() - finished).days)
    return max(0.35, 1.0 - (days / 365))


def _cluster_id_for_book(book: Book) -> str:
    text = _norm(" ".join([book.title or "", book.authors or "", *[str(v) for v in book.genres or []], *[str(v) for v in book.subjects or []]]))
    if any(value in text for value in ("naturals", "criminal profiling", "serial killer", "mystery thriller", "truly devious")):
        return "ya-mystery-thriller"
    if any(value in text for value in ("hunger games", "dystopian", "rebellion", "survival competition", "scythe")):
        return "ya-dystopian-speculative"
    if any(value in text for value in ("book lovers", "emily henry", "ali hazelwood", "women in stem", "contemporary romance", "romantic comedy")):
        return "contemporary-romance-new-adult"
    if any(value in text for value in ("sally rooney", "relationship fiction", "normal people", "interpersonal relationships")):
        return "literary-relationship-fiction"
    if any(value in text for value in ("anna karenina", "tolstoy", "russian realism", "russian literature")):
        return "russian-realism-moral-fiction"
    if any(value in text for value in ("frankenstein", "gothic fiction", "gothic horror")):
        return "gothic-classics"
    if any(value in text for value in ("fantasy romance", "faeries", "court of", "romantasy")):
        return "fantasy-romance"
    if any(value in text for value in ("political philosophy", "social contract", "john locke")):
        return "political-philosophy"
    terms = specific_terms([*(book.genres or []), *(book.subjects or [])], minimum=0.5)
    return f"topic-{_norm(terms[0]).replace(' ', '-')}" if terms else "topic-specific-reading"


DEFAULT_DIMENSION_TERMS: dict[str, dict[str, tuple[str, ...]]] = {
    "ya-mystery-thriller": {
        "genres": ("young adult mystery", "thriller"),
        "themes": ("criminal profiling", "serial killers", "closed circle mystery"),
    },
    "ya-dystopian-speculative": {
        "genres": ("dystopian fiction", "young adult science fiction"),
        "themes": ("survival", "rebellion", "speculative political fiction"),
    },
    "contemporary-romance-new-adult": {
        "genres": ("contemporary romance", "new adult fiction"),
        "themes": ("women in STEM", "academic romance", "romantic comedy"),
    },
    "literary-relationship-fiction": {
        "genres": ("literary fiction", "relationship fiction"),
        "themes": ("interpersonal relationships", "coming of age", "modern relationships"),
    },
    "russian-realism-moral-fiction": {
        "genres": ("russian realism", "literary classics"),
        "themes": ("moral philosophy", "psychological fiction", "marriage"),
    },
    "gothic-classics": {
        "genres": ("gothic fiction", "literary classics"),
        "themes": ("scientific ambition", "monstrosity", "gothic horror"),
    },
    "fantasy-romance": {
        "genres": ("fantasy romance", "fantasy fiction"),
        "themes": ("faeries", "magic", "romantic fantasy"),
    },
    "political-philosophy": {
        "genres": ("political philosophy",),
        "themes": ("social contract", "liberty", "toleration"),
    },
}


SUBJECT_POOLS: dict[str, tuple[str, ...]] = {
    "ya-mystery-thriller": ("young_adult_mystery", "criminal_profilers", "mystery_and_detective_stories", "psychological_fiction"),
    "ya-dystopian-speculative": ("dystopias", "dystopian_fiction", "survival", "political_fiction"),
    "contemporary-romance-new-adult": ("contemporary_romance", "women_scientists", "love_stories", "romantic_comedy"),
    "literary-relationship-fiction": ("interpersonal_relations", "love_stories", "psychological_fiction", "coming_of_age"),
    "russian-realism-moral-fiction": ("russian_literature", "psychological_fiction", "marriage", "moral_conditions"),
    "gothic-classics": ("gothic_fiction", "horror_tales", "monsters", "scientists"),
    "fantasy-romance": ("fantasy_fiction", "magic", "fairies", "love_stories"),
    "political-philosophy": ("political_science", "liberty", "social_contract", "toleration"),
}


ADJACENT_SUBJECTS: dict[str, tuple[str, ...]] = {
    "ya-mystery-thriller": ("closed_circle_mystery", "crime_fiction"),
    "ya-dystopian-speculative": ("speculative_fiction", "revolutions", "survivalism"),
    "contemporary-romance-new-adult": ("academic_fiction", "workplace_romance"),
    "literary-relationship-fiction": ("domestic_fiction", "college_students"),
    "russian-realism-moral-fiction": ("philosophy", "families"),
    "gothic-classics": ("science_fiction", "horror_fiction"),
    "fantasy-romance": ("paranormal_romance", "imaginary_places"),
}


def build_taste_dimensions(library_books: list[Book]) -> list[TasteDimension]:
    grouped: dict[str, list[Book]] = {}
    for book in library_books:
        status = _status(book)
        if status == "completed" and _rating(book) < 3.5:
            continue
        if status not in {"completed", "reading", "not_started"}:
            continue
        grouped.setdefault(_cluster_id_for_book(book), []).append(book)

    dimensions: list[TasteDimension] = []
    for cluster_id, books in grouped.items():
        tags = specific_terms(
            [tag for book in books for tag in [*(book.genres or []), *(book.subjects or [])]],
            minimum=0.5,
        )
        defaults = DEFAULT_DIMENSION_TERMS.get(cluster_id, {})
        genres = tuple(dict.fromkeys([*(defaults.get("genres") or ()), *tags[:2]]))[:4]
        themes = tuple(dict.fromkeys([*(defaults.get("themes") or ()), *tags[2:6]]))[:5]
        authors = tuple(
            dict.fromkeys(
                author
                for book in sorted(books, key=lambda item: (-_rating(item), item.title or ""))
                if (author := _lead_author(book.authors)) and author.casefold() != "unknown author"
            )
        )[:4]
        completed = [book for book in books if _status(book) == "completed"]
        evidence = min(
            1.0,
            (0.22 * len(books))
            + (0.16 * len(completed))
            + (0.08 * len(genres))
            + (0.08 * len(themes))
            + (0.12 * sum(_recency(book) for book in books) / max(1, len(books))),
        )
        if len(books) == 1 and evidence < 0.45:
            continue
        dimensions.append(
            TasteDimension(
                cluster_id=cluster_id,
                specific_genres=genres,
                specific_themes=themes,
                positive_authors=authors,
                negative_signals=(),
                semantic_centroid_terms=tuple(dict.fromkeys([*genres, *themes]))[:8],
                evidence_strength=evidence,
                anchor_titles=tuple(book.title for book in books if book.title)[:4],
            )
        )
    dimensions.sort(key=lambda item: (item.evidence_strength, len(item.anchor_titles)), reverse=True)
    return dimensions


def _open_library_subject_results(subject: str, *, limit: int) -> list[dict]:
    payload = _http_get_json(
        "open_library",
        "https://openlibrary.org/search.json",
        params={
            "subject": subject.replace("_", " "),
            "limit": limit,
            "fields": "title,author_name,subject,key,description,first_publish_year,cover_i",
        },
        timeout=OPEN_LIBRARY_SEARCH_TIMEOUT_SECONDS,
    )
    docs = payload.get("docs", []) if isinstance(payload, dict) else []
    results: list[dict] = []
    for provider_rank, doc in enumerate(docs if isinstance(docs, list) else [], start=1):
        if not isinstance(doc, dict) or not str(doc.get("title") or "").strip():
            continue
        subjects = filter_specific_subjects(doc.get("subject"))
        cover_id = doc.get("cover_i")
        normalized = _normalized_result(
            title=doc.get("title"),
            authors=doc.get("author_name") or [],
            description=doc.get("description"),
            subjects=subjects,
            genres=subjects_to_genres(subjects),
            first_publish_year=doc.get("first_publish_year"),
            metadata_source="open_library",
            work_key=doc.get("key"),
            cover_url=f"https://covers.openlibrary.org/b/id/{cover_id}-L.jpg?default=false" if cover_id else None,
            confidence_score=max(0.38, 0.74 - (provider_rank * 0.02)),
        )
        normalized["provider_rank"] = provider_rank
        results.append(normalized)
    return results


def _mode_sources(dimension: TasteDimension) -> list[tuple[str, str]]:
    subjects = list(SUBJECT_POOLS.get(dimension.cluster_id, ()))
    if not subjects:
        subjects = [_norm(term).replace(" ", "_") for term in [*dimension.specific_themes, *dimension.specific_genres] if _norm(term)]
    selected_subjects = subjects[:exploration_subjects_per_dimension()]
    modes = [("subject", subject) for subject in selected_subjects]
    modes.extend(("controlled_adjacent", subject) for subject in ADJACENT_SUBJECTS.get(dimension.cluster_id, ())[:2])
    if dimension.specific_themes:
        modes.append(("author_neighborhood", _norm(dimension.specific_themes[0]).replace(" ", "_")))
    return modes


def explore_external_candidates(
    library_books: list[Book],
    *,
    limit: int = 80,
    result_limit_per_source: int | None = None,
) -> tuple[list[dict], ExternalExplorationDiagnostics]:
    started = time.perf_counter()
    diagnostics = ExternalExplorationDiagnostics()
    dimensions = build_taste_dimensions(library_books)
    diagnostics.taste_dimensions = [dimension.to_dict() for dimension in dimensions]
    per_source = result_limit_per_source or exploration_results_per_source()
    candidates: list[dict] = []
    max_per_dimension = max(per_source, limit // max(1, len(dimensions))) if dimensions else limit

    for dimension in dimensions:
        dimension_count = 0
        for mode, source in _mode_sources(dimension):
            if len(candidates) >= limit:
                break
            if dimension_count >= max_per_dimension:
                break
            try:
                results = _open_library_subject_results(source, limit=per_source)
            except Exception as exc:
                logger.info(
                    "external_candidate_exploration_failed mode=%s source=%s cluster=%s error=%s",
                    mode,
                    source,
                    dimension.cluster_id,
                    type(exc).__name__,
                )
                diagnostics.exploration_requests.append(
                    {"mode": mode, "source": source, "cluster_id": dimension.cluster_id, "result_count": 0, "error_type": type(exc).__name__}
                )
                continue
            diagnostics.exploration_requests.append(
                {"mode": mode, "source": source, "cluster_id": dimension.cluster_id, "result_count": len(results)}
            )
            diagnostics.total_open_library_candidates_fetched += len(results)
            if mode == "subject":
                diagnostics.subject_exploration_candidates += len(results)
            elif mode == "controlled_adjacent":
                diagnostics.adjacent_exploration_candidates += len(results)
            elif mode == "author_neighborhood":
                diagnostics.author_neighborhood_candidates += len(results)
            else:
                diagnostics.related_work_candidates += len(results)
            for result in results:
                result.update(
                    {
                        "provider": "open_library",
                        "exploration_mode": mode,
                        "exploration_source": source,
                        "provider_rank": result.get("provider_rank"),
                        "discovery_query": None,
                        "discovery_cluster_id": dimension.cluster_id,
                        "discovery_query_confidence": dimension.evidence_strength,
                        "discovery_anchor_titles": list(dimension.anchor_titles),
                        "discovery_anchor_authors": list(dimension.positive_authors),
                        "discovery_specific_genres": list(dimension.specific_genres),
                        "discovery_specific_themes": list(dimension.specific_themes),
                        "taste_dimension": dimension.to_dict(),
                    }
                )
                candidates.append(result)
                dimension_count += 1
                if len(candidates) >= limit:
                    break
                if dimension_count >= max_per_dimension:
                    break
        if len(candidates) >= limit:
            break

    diagnostics.broad_exploration_candidates = len(candidates)
    diagnostics.elapsed_ms = (time.perf_counter() - started) * 1000
    logger.info("external_candidate_exploration_diagnostics %s", diagnostics.to_dict())
    return candidates, diagnostics
