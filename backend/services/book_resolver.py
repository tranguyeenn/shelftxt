"""Deterministic multi-provider resolution for explicit/background metadata work."""

from __future__ import annotations

import copy
import logging
import re
import threading
import time
from collections import OrderedDict
from concurrent.futures import Future, ThreadPoolExecutor, TimeoutError as FutureTimeout
from dataclasses import asdict, dataclass, field
from difflib import SequenceMatcher
from typing import Callable

from app.integrations import librarything

logger = logging.getLogger(__name__)

PROVIDER_TIMEOUT_SECONDS = 4.0
LIBRARYTHING_ENRICHMENT_TIMEOUT_SECONDS = 2.25
QUERY_CACHE_SECONDS = 300
ISBN_CACHE_SECONDS = 3600
NEGATIVE_CACHE_SECONDS = 30
MAX_CACHE_ENTRIES = 512
MIN_GOOD_MATCH_SCORE = 20


@dataclass(frozen=True)
class BookCandidate:
    title: str
    authors: tuple[str, ...] = ()
    isbn: str | None = None
    description: str | None = None
    cover_url: str | None = None
    total_pages: int | None = None
    subjects: tuple[str, ...] = ()
    genres: tuple[str, ...] = ()
    first_publish_year: int | None = None
    work_key: str | None = None
    edition_key: str | None = None
    language: str | None = None
    source: str = "unknown"
    publisher: str | None = None
    publish_date: str | None = None


@dataclass(frozen=True)
class CanonicalBook:
    title: str
    authors: tuple[str, ...] = ()
    isbn: str | None = None
    description: str | None = None
    cover_url: str | None = None
    total_pages: int | None = None
    subjects: tuple[str, ...] = ()
    genres: tuple[str, ...] = ()
    first_publish_year: int | None = None
    work_key: str | None = None
    edition_key: str | None = None
    language: str | None = None
    source: str = "unknown"
    publisher: str | None = None
    publish_date: str | None = None
    related_isbns: tuple[str, ...] = field(default_factory=tuple)

    def to_dict(self) -> dict:
        data = asdict(self)
        for key in ("authors", "subjects", "genres", "related_isbns"):
            data[key] = list(data[key])
        return data


_cache: OrderedDict[str, tuple[float, CanonicalBook | None]] = OrderedDict()
_inflight: dict[str, Future] = {}
_lock = threading.Lock()


def _normalized_text(value: object) -> str:
    return " ".join(re.sub(r"[^a-z0-9]+", " ", str(value or "").casefold()).split())


def _normalize_isbn(value: object) -> str | None:
    cleaned = re.sub(r"[^0-9Xx]", "", str(value or "")).upper()
    return cleaned if len(cleaned) in {10, 13} else None


def _candidate_from_result(result: dict) -> BookCandidate | None:
    title = str(result.get("title") or "").strip()
    if not title:
        return None
    return BookCandidate(
        title=title,
        authors=tuple(str(value).strip() for value in result.get("authors") or [] if str(value).strip()),
        isbn=_normalize_isbn(result.get("isbn_uid") or result.get("isbn")),
        description=result.get("description") or None,
        cover_url=result.get("cover_url") or None,
        total_pages=result.get("total_pages") if isinstance(result.get("total_pages"), int) else None,
        subjects=tuple(dict.fromkeys(result.get("subjects") or [])),
        genres=tuple(dict.fromkeys(result.get("genres") or [])),
        first_publish_year=result.get("first_publish_year")
        if isinstance(result.get("first_publish_year"), int)
        else None,
        work_key=result.get("work_key") or None,
        edition_key=result.get("edition_key") or None,
        language=result.get("language") or None,
        source=result.get("metadata_source") or result.get("source") or "unknown",
        publisher=result.get("publisher") or None,
        publish_date=result.get("publish_date") or None,
    )


def score_candidate(
    candidate: BookCandidate,
    *,
    query: str,
    isbn: str | None = None,
    author: str | None = None,
) -> float:
    score = 0.0
    if isbn and candidate.isbn == isbn:
        score += 50

    query_key = _normalized_text(query)
    title_key = _normalized_text(candidate.title)
    if title_key and (title_key == query_key or title_key in query_key):
        score += 30
    elif title_key and SequenceMatcher(None, title_key, query_key).ratio() >= 0.78:
        score += 30

    author_key = _normalized_text(author)
    candidate_authors = [_normalized_text(value) for value in candidate.authors]
    if author_key and any(author_key == value or author_key in value or value in author_key for value in candidate_authors):
        score += 20
    elif not author_key and any(value and value in query_key for value in candidate_authors):
        score += 20
    if candidate.cover_url:
        score += 10
    if candidate.total_pages:
        score += 10
    if candidate.description:
        score += 10
    if candidate.language and _normalized_text(candidate.language) not in {"en", "eng", "english"}:
        score -= 5
    return score


def select_canonical_candidate(
    candidates: list[BookCandidate],
    *,
    query: str,
    isbn: str | None = None,
    author: str | None = None,
) -> tuple[BookCandidate, list[BookCandidate]] | None:
    ranked = sorted(
        enumerate(candidates),
        key=lambda item: (
            -score_candidate(item[1], query=query, isbn=isbn, author=author),
            0 if item[1].source == "open_library" else 1,
            item[0],
        ),
    )
    if not ranked:
        return None
    best_score = score_candidate(ranked[0][1], query=query, isbn=isbn, author=author)
    if best_score < MIN_GOOD_MATCH_SCORE:
        return None
    ordered = [candidate for _index, candidate in ranked]
    return ordered[0], ordered[1:]


def merge_canonical_candidate(primary: BookCandidate, others: list[BookCandidate]) -> CanonicalBook:
    data = asdict(primary)
    list_fields = ("subjects", "genres")
    fillable_fields = (
        "description",
        "first_publish_year",
        "work_key",
        "language",
    )
    edition_fields = ("isbn", "cover_url", "total_pages", "edition_key", "publisher", "publish_date")

    for candidate in others:
        incoming = asdict(candidate)
        if not data.get("authors") and incoming.get("authors"):
            data["authors"] = incoming["authors"]
        for name in fillable_fields:
            if not data.get(name) and incoming.get(name):
                data[name] = incoming[name]
        for name in list_fields:
            data[name] = tuple(dict.fromkeys((*data.get(name, ()), *incoming.get(name, ()))))

        # Edition data is adopted only as a complete bundle from one candidate;
        # individual cover/page/ISBN fields are never borrowed independently.
        if not (data.get("isbn") or data.get("edition_key")) and (
            incoming.get("isbn") or incoming.get("edition_key")
        ):
            for name in edition_fields:
                data[name] = incoming.get(name)

    return CanonicalBook(**data)


def _provider_fetchers() -> tuple[Callable[[str], list[dict]], Callable[[str], list[dict]]]:
    from app.integrations.google_books import search_candidates as google_books
    from app.integrations.openlibrary import search_candidates as open_library

    return open_library, google_books


def _resolve_uncached(query: str, author: str | None, isbn: str | None) -> CanonicalBook | None:
    open_library, google_books = _provider_fetchers()
    provider_results: list[dict] = []
    executor = ThreadPoolExecutor(max_workers=2, thread_name_prefix="book-resolver")
    try:
        futures = [executor.submit(open_library, isbn or query), executor.submit(google_books, isbn or query)]
        for future in futures:
            try:
                provider_results.extend(future.result(timeout=PROVIDER_TIMEOUT_SECONDS) or [])
            except (FutureTimeout, Exception) as exc:
                logger.warning("Book resolver provider failed: error=%s", type(exc).__name__)
    finally:
        executor.shutdown(wait=False, cancel_futures=True)

    candidates = [candidate for result in provider_results if (candidate := _candidate_from_result(result))]
    selected = select_canonical_candidate(candidates, query=query, isbn=isbn, author=author)
    if selected is None:
        return None
    primary, others = selected
    canonical = merge_canonical_candidate(primary, others)

    if canonical.isbn:
        executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="librarything-enrichment")
        try:
            future = executor.submit(librarything.fetch_related_isbns, canonical.isbn)
            try:
                related = tuple(dict.fromkeys(future.result(timeout=LIBRARYTHING_ENRICHMENT_TIMEOUT_SECONDS) or []))
                canonical = CanonicalBook(**{**asdict(canonical), "related_isbns": related})
            except (FutureTimeout, Exception) as exc:
                logger.warning("LibraryThing resolver enrichment skipped: error=%s", type(exc).__name__)
        finally:
            executor.shutdown(wait=False, cancel_futures=True)
    return canonical


def resolve_book(query: str, author: str | None = None) -> CanonicalBook | None:
    clean_query = str(query or "").strip()
    if not clean_query:
        return None
    isbn = _normalize_isbn(clean_query)
    key = f"isbn:{isbn}" if isbn else f"query:{_normalized_text(clean_query)}|{_normalized_text(author)}"
    ttl = ISBN_CACHE_SECONDS if isbn else QUERY_CACHE_SECONDS
    now = time.monotonic()

    with _lock:
        cached = _cache.get(key)
        cached_ttl = NEGATIVE_CACHE_SECONDS if cached and cached[1] is None else ttl
        if cached and now - cached[0] < cached_ttl:
            _cache.move_to_end(key)
            return copy.deepcopy(cached[1])
        future = _inflight.get(key)
        leader = future is None
        if leader:
            future = Future()
            _inflight[key] = future

    if not leader:
        return copy.deepcopy(future.result())

    try:
        result = _resolve_uncached(clean_query, author, isbn)
        with _lock:
            _cache[key] = (time.monotonic(), result)
            _cache.move_to_end(key)
            while len(_cache) > MAX_CACHE_ENTRIES:
                _cache.popitem(last=False)
        future.set_result(result)
        return copy.deepcopy(result)
    except Exception as exc:
        logger.exception("Book resolver failed: error=%s", type(exc).__name__)
        future.set_result(None)
        return None
    finally:
        with _lock:
            _inflight.pop(key, None)


def clear_resolver_cache() -> None:
    with _lock:
        _cache.clear()
