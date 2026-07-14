from __future__ import annotations

import logging
import re
import time
from collections import Counter
from dataclasses import dataclass, field
from datetime import date
from difflib import SequenceMatcher
from uuid import UUID

from sqlalchemy.orm import Session

from backend.db.models import Book
from backend.services.book_search import _run_aggregation
from backend.services.status import normalize_status

logger = logging.getLogger(__name__)

MAX_DISCOVERY_QUERIES = 3
MAX_LOCAL_DISCOVERY_CANDIDATES = 250
MAX_DISCOVERY_RESULTS_PER_QUERY = 12
MIN_DISCOVERY_CONFIDENCE = 0.35


@dataclass
class DiscoveryDiagnostics:
    library_candidate_count: int = 0
    external_candidate_count: int = 0
    external_provider_attempts: int = 0
    external_provider_successes: int = 0
    deduplicated_external_count: int = 0
    provider_failures: list[dict] = field(default_factory=list)
    queries: list[str] = field(default_factory=list)
    elapsed_ms: float = 0.0

    def to_dict(self) -> dict:
        return {
            "library_candidate_count": self.library_candidate_count,
            "external_candidate_count": self.external_candidate_count,
            "external_provider_attempts": self.external_provider_attempts,
            "external_provider_successes": self.external_provider_successes,
            "deduplicated_external_count": self.deduplicated_external_count,
            "provider_failures": self.provider_failures,
            "queries": self.queries,
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
    title_author = _title_author_key(result.get("title"), _result_author(result))
    if title_author in identities["title_authors"]:
        return True
    return False


def _external_duplicate_key(result: dict) -> tuple[str, str]:
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
    return {
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
    return 0.8


def _discovery_queries(library_books: list[Book]) -> list[str]:
    completed = [
        book
        for book in library_books
        if normalize_status(
            book.read_status,
            progress_percent=float(book.progress_percent or 0),
            pages_read=int(book.pages_read or 0),
        )
        == "completed"
    ]
    anchors = completed or library_books
    if not anchors:
        return []

    author_weights: Counter[str] = Counter()
    tag_weights: Counter[str] = Counter()
    title_weights: Counter[str] = Counter()
    for book in anchors:
        base = _rating_weight(book) * _recency_weight(book)
        author = _lead_author(book.authors)
        if author and author.casefold() != "unknown author":
            author_weights[author] += base
        for tag in [*_metadata_values(book, "genres"), *_metadata_values(book, "subjects")]:
            tag_weights[tag] += base
        if book.title:
            title_weights[book.title] += base

    queries: list[str] = []
    top_author = author_weights.most_common(1)[0][0] if author_weights else None
    top_tags = [tag for tag, _weight in tag_weights.most_common(3)]
    if top_author and top_tags:
        queries.append(f"{top_author} {top_tags[0]}")
    if len(top_tags) >= 2:
        queries.append(f"{top_tags[0]} {top_tags[1]}")
    elif top_tags:
        queries.append(top_tags[0])
    if top_author and top_author not in queries:
        queries.append(top_author)
    if len(queries) < MAX_DISCOVERY_QUERIES and title_weights:
        queries.append(title_weights.most_common(1)[0][0])

    deduped: list[str] = []
    seen: set[str] = set()
    for query in queries:
        clean = " ".join(str(query).split())
        key = clean.casefold()
        if clean and key not in seen:
            seen.add(key)
            deduped.append(clean)
        if len(deduped) >= MAX_DISCOVERY_QUERIES:
            break
    return deduped


def _external_id(result: dict) -> str:
    return (
        str(result.get("work_key") or "").strip()
        or str(result.get("edition_key") or "").strip()
        or str(result.get("isbn_uid") or "").strip()
        or f"external:{_normalize_text(result.get('title'))}:{_normalize_text(_result_author(result))}"
    )


def _result_to_row(result: dict) -> dict:
    external_id = _external_id(result)
    return {
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
    }


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


def discovery_candidate_rows(
    db: Session,
    user_id: UUID,
    library_books: list[Book],
    *,
    limit: int = 40,
) -> tuple[list[dict], DiscoveryDiagnostics]:
    started = time.perf_counter()
    diagnostics = DiscoveryDiagnostics()
    queries = _discovery_queries(library_books)
    diagnostics.queries = queries
    if not queries:
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

    for query in queries:
        aggregation = _run_aggregation(query, local_candidates)
        external_outcomes = [outcome for outcome in aggregation.outcomes if outcome.source != "local"]
        diagnostics.external_provider_attempts += len(external_outcomes)
        diagnostics.external_provider_successes += sum(1 for outcome in external_outcomes if outcome.success)
        diagnostics.provider_failures.extend(
            {
                "source": outcome.source,
                "outcome": outcome.outcome,
                "error_type": outcome.error_type,
            }
            for outcome in external_outcomes
            if not outcome.success and outcome.outcome not in {"disabled", "not_configured", "empty_success"}
        )

        for result in aggregation.results[:MAX_DISCOVERY_RESULTS_PER_QUERY]:
            if result.get("already_in_library") or _result_duplicates_library(result, identities):
                deduped_count += 1
                continue
            if float(result.get("confidence_score") or 0.0) < MIN_DISCOVERY_CONFIDENCE:
                continue
            key = _external_duplicate_key(result)
            if key in by_key:
                by_key[key] = _stronger_result(by_key[key], result)
                deduped_count += 1
            else:
                by_key[key] = result

    rows = [_result_to_row(result) for result in by_key.values()]
    rows = rows[:limit]
    diagnostics.external_candidate_count = len(rows)
    diagnostics.deduplicated_external_count = deduped_count
    diagnostics.elapsed_ms = (time.perf_counter() - started) * 1000
    logger.info("recommendation_discovery_diagnostics %s", diagnostics.to_dict())
    return rows, diagnostics
