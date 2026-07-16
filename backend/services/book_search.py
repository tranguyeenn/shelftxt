"""Normalized, resilient book search across metadata providers and local books."""

import asyncio
import logging
import os
import re
import threading
import time
from concurrent.futures import Future
from difflib import SequenceMatcher
from typing import Any

import httpx
from sqlalchemy.orm import Session

from backend.db.models import Book
from backend.services.metadata_normalization import (
    filter_specific_subjects,
    subjects_to_genres,
)
from backend.services.open_library_editions import (
    edition_fields,
    normalize_title,
    select_best_open_library_edition,
)
from backend.services.metadata_aggregation import (
    LocalCatalogSource,
    MetadataAggregationService,
)
from backend.services.metadata_providers import (
    ProviderSearchError,
    is_transient_error,
    provider_outcome_for_exception,
)
from backend.services.book_scraping.domains import is_trusted_domain, normalize_domain
from backend.services.book_scraping.service import scrape_book_metadata
from backend.services.work_grouping import group_search_results
from backend.services.series_metadata import normalize_series_metadata
from backend.services.request_timing import add_timing

logger = logging.getLogger(__name__)

OPEN_LIBRARY_SEARCH_TIMEOUT_SECONDS = 3.0
OPEN_LIBRARY_EDITION_LIMIT = 20
OPEN_LIBRARY_EDITION_CACHE_TTL_SECONDS = 24 * 60 * 60
LIBRARYTHING_ENRICHMENT_TIMEOUT_SECONDS = 2.25
SEARCH_RESULT_LIMIT = 12
PROVIDER_HTTP_MAX_RETRIES = 1
PROVIDER_HTTP_TIMEOUT = httpx.Timeout(4.0, connect=2.0, read=4.0, write=4.0, pool=2.0)
DEFAULT_EXTERNAL_PROVIDER_LIMIT = 2
_edition_cache: dict[tuple[str, int], tuple[float, dict]] = {}
_edition_inflight: dict[tuple[str, int], Future] = {}
_edition_lock = threading.Lock()


def _clean_text(value: Any) -> str | None:
    return value.strip() if isinstance(value, str) and value.strip() else None


def _positive_int(value: Any) -> int | None:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return None
    return parsed if parsed > 0 else None


def _normalize_isbn(value: Any) -> str | None:
    cleaned = re.sub(r"[^0-9Xx]", "", str(value or "")).upper()
    return cleaned if len(cleaned) in {10, 13} else None


def _http_get_json(
    provider: str,
    url: str,
    *,
    params: dict[str, Any] | None = None,
    timeout: float,
    follow_redirects: bool = False,
) -> dict:
    bounded_timeout = max(0.25, float(timeout or OPEN_LIBRARY_SEARCH_TIMEOUT_SECONDS))
    http_timeout = httpx.Timeout(
        bounded_timeout,
        connect=min(2.0, bounded_timeout),
        read=bounded_timeout,
        write=min(2.0, bounded_timeout),
        pool=min(2.0, bounded_timeout),
    )
    for attempt in range(1, PROVIDER_HTTP_MAX_RETRIES + 2):
        started = time.perf_counter()
        request_url = url
        try:
            response = httpx.get(
                url,
                params=params,
                timeout=http_timeout,
                follow_redirects=follow_redirects,
            )
            request_url = str(response.request.url)
            response.raise_for_status()
            try:
                payload = response.json()
                if not isinstance(payload, dict):
                    raise ValueError("expected JSON object")
                return payload
            except ValueError as exc:
                elapsed_ms = (time.perf_counter() - started) * 1000
                logger.warning(
                    "metadata_provider_parsing_failed "
                    "provider=%s attempt=%s elapsed_ms=%.2f "
                    "http_status=%s request_url=%s "
                    "exception_type=%s response_body=%r",
                    provider,
                    attempt,
                    elapsed_ms,
                    response.status_code,
                    request_url,
                    type(exc).__name__,
                    response.text[:1000],
                )
                raise ProviderSearchError(
                    "Provider response parsing failed",
                    provider=provider,
                    outcome="parsing_failure",
                    elapsed_ms=elapsed_ms,
                    http_status=response.status_code,
                    request_url=request_url,
                    response_body=response.text[:1000],
                    exception_type=type(exc).__name__,
                ) from exc
        except (httpx.HTTPError, ValueError) as exc:
            elapsed_ms = (time.perf_counter() - started) * 1000
            response = exc.response if isinstance(exc, httpx.HTTPStatusError) else None
            request = exc.request if isinstance(exc, httpx.RequestError) else None
            request_url = str((response.request if response is not None else request).url) if (
                response is not None or request is not None
            ) else request_url
            response_body = response.text[:1000] if response is not None else None
            outcome = provider_outcome_for_exception(exc)
            transient = is_transient_error(exc)
            logger.warning(
                "metadata_provider_http_request_failed "
                "provider=%s attempt=%s elapsed_ms=%.2f "
                "http_status=%s request_url=%s "
                "exception_type=%s outcome=%s transient=%s "
                "response_body=%r",
                provider,
                attempt,
                elapsed_ms,
                response.status_code if response is not None else None,
                request_url,
                type(exc).__name__,
                outcome,
                transient,
                response_body[:1000] if response_body else None,
            )
            if attempt > PROVIDER_HTTP_MAX_RETRIES or not transient:
                raise ProviderSearchError(
                    "Provider HTTP request failed",
                    provider=provider,
                    outcome=outcome,
                    elapsed_ms=elapsed_ms,
                    http_status=response.status_code if response is not None else None,
                    request_url=request_url,
                    response_body=response_body,
                    exception_type=type(exc).__name__,
                ) from exc
    raise RuntimeError("unreachable provider retry state")


def _normalized_result(**values: Any) -> dict:
    authors = values.get("authors") or []
    if isinstance(authors, str):
        authors = [authors]
    series = normalize_series_metadata(values.get("series") if isinstance(values.get("series"), dict) else values)
    result = {
        "title": _clean_text(values.get("title")) or "Untitled",
        "authors": [str(author).strip() for author in authors if str(author).strip()],
        "isbn_uid": _normalize_isbn(values.get("isbn_uid")),
        "description": _clean_text(values.get("description")),
        "cover_url": _clean_text(values.get("cover_url")),
        "total_pages": _positive_int(values.get("total_pages")),
        "subjects": list(dict.fromkeys(values.get("subjects") or [])),
        "genres": list(dict.fromkeys(values.get("genres") or [])),
        "first_publish_year": _positive_int(values.get("first_publish_year")),
        "metadata_source": values.get("metadata_source") or "local",
        "work_key": _clean_text(values.get("work_key")),
        "edition_key": _clean_text(values.get("edition_key")),
        "publisher": _clean_text(values.get("publisher")),
        "publish_date": _clean_text(values.get("publish_date")),
        "language": _clean_text(values.get("language")),
        "related_isbns": list(
            dict.fromkeys(
                isbn
                for value in values.get("related_isbns") or []
                if (isbn := _normalize_isbn(value))
            )
        ),
        "source_urls": list(dict.fromkeys(str(value) for value in values.get("source_urls") or [] if str(value).strip())),
        "already_in_library": bool(values.get("already_in_library", False)),
        "confidence_score": float(values.get("confidence_score") or 0.0),
        "editions_loaded": bool(values.get("editions_loaded", False)),
    }
    if series:
        result.update(series)
        result["series"] = series
    return result


def _fetch_open_library_exact_edition(isbn: str) -> dict | None:
    try:
        return _http_get_json(
            "open_library",
            f"https://openlibrary.org/isbn/{isbn}.json",
            timeout=OPEN_LIBRARY_SEARCH_TIMEOUT_SECONDS,
            follow_redirects=True,
        )
    except ProviderSearchError:
        raise
    except (httpx.HTTPError, ValueError) as exc:
        logger.warning("Open Library exact edition lookup failed: error=%s", type(exc).__name__)
        return None


def _fetch_open_library_work_editions(work_key: str | None, *, limit: int = OPEN_LIBRARY_EDITION_LIMIT) -> list[dict]:
    key = str(work_key or "").strip().removeprefix("/works/")
    if not key:
        return []
    started = time.perf_counter()
    try:
        payload = _http_get_json(
            "open_library",
            f"https://openlibrary.org/works/{key}/editions.json",
            params={"limit": limit},
            timeout=OPEN_LIBRARY_SEARCH_TIMEOUT_SECONDS,
            follow_redirects=True,
        )
    except ProviderSearchError:
        raise
    except (httpx.HTTPError, ValueError) as exc:
        logger.warning("Open Library work editions lookup failed: error=%s", type(exc).__name__)
        return []
    finally:
        logger.info(
            "open_library_edition_lookup duration_ms=%.2f work_id=%s limit=%s",
            (time.perf_counter() - started) * 1000,
            key,
            limit,
        )
    entries = payload.get("entries", []) if isinstance(payload, dict) else []
    return [entry for entry in entries if isinstance(entry, dict)] if isinstance(entries, list) else []


def _open_library_results(query: str, *, limit: int = 8) -> list[dict]:
    exact_isbn = _normalize_isbn(query)
    exact_edition = _fetch_open_library_exact_edition(exact_isbn) if exact_isbn else None
    try:
        payload = _http_get_json(
            "open_library",
            "https://openlibrary.org/search.json",
            params={
                "q": f"isbn:{exact_isbn}" if exact_isbn else query,
                "limit": limit,
                "fields": (
                    "title,author_name,subject,key,description,first_publish_year"
                ),
            },
            timeout=OPEN_LIBRARY_SEARCH_TIMEOUT_SECONDS,
        )
    except ProviderSearchError:
        raise
    except (httpx.HTTPError, ValueError) as exc:
        logger.warning("Open Library search failed: error=%s", type(exc).__name__)
        return []

    docs = payload.get("docs", []) if isinstance(payload, dict) else []
    if exact_edition and not docs:
        work_key = None
        works = exact_edition.get("works")
        if isinstance(works, list) and works and isinstance(works[0], dict):
            work_key = works[0].get("key")
        return [
            _normalized_result(
                title=exact_edition.get("title"),
                authors=[],
                metadata_source="open_library",
                work_key=work_key,
                **edition_fields(exact_edition),
            )
        ]

    if exact_edition and isinstance(docs, list):
        works = exact_edition.get("works")
        exact_work_key = (
            works[0].get("key")
            if isinstance(works, list) and works and isinstance(works[0], dict)
            else None
        )
        matching_docs = [doc for doc in docs if isinstance(doc, dict) and doc.get("key") == exact_work_key]
        docs = matching_docs[:1] or docs[:1]

    seen_work_keys: set[str] = set()
    duplicate_work_keys = 0
    results: list[dict] = []
    for index, doc in enumerate(docs if isinstance(docs, list) else []):
        if not isinstance(doc, dict) or not _clean_text(doc.get("title")):
            continue
        work_key = _clean_text(doc.get("key"))
        if work_key and work_key in seen_work_keys:
            duplicate_work_keys += 1
            continue
        if work_key:
            seen_work_keys.add(work_key)
        subjects = filter_specific_subjects(doc.get("subject"))
        selected_edition = exact_edition if exact_isbn else None
        displayed_title = str(doc.get("title") or "")
        query_title = normalize_title(query)
        displayed_title_normalized = normalize_title(displayed_title)
        likely_title_author_query = (
            bool(work_key)
            and bool(displayed_title_normalized)
            and displayed_title_normalized in query_title
            and query_title != displayed_title_normalized
        )
        if selected_edition is None and likely_title_author_query:
            try:
                editions = _fetch_open_library_work_editions(work_key, limit=OPEN_LIBRARY_EDITION_LIMIT)
            except ProviderSearchError:
                editions = []
            selected_edition = select_best_open_library_edition(
                editions,
                query=query,
                displayed_title=displayed_title,
                author_work_match=bool(doc.get("author_name")),
            )
        selected_fields = edition_fields(selected_edition)
        results.append(
            _normalized_result(
                title=(selected_edition or {}).get("title") if exact_isbn else doc.get("title"),
                authors=doc.get("author_name") or [],
                description=doc.get("description"),
                subjects=subjects,
                genres=subjects_to_genres(subjects),
                first_publish_year=doc.get("first_publish_year"),
                metadata_source="open_library",
                work_key=work_key,
                editions_loaded=bool(selected_edition),
                **selected_fields,
            )
        )
    logger.info(
        "open_library_work_search_completed unique_work_ids=%s duplicate_work_ids_removed=%s result_count=%s",
        len(seen_work_keys),
        duplicate_work_keys,
        len(results),
    )
    return results


def _open_library_edition_result(edition: dict, *, work_id: str, fallback_title: str | None = None, fallback_authors: list[str] | None = None) -> dict:
    fields = edition_fields(edition)
    return _normalized_result(
        title=edition.get("title") or fallback_title or "Untitled",
        authors=fallback_authors or [],
        metadata_source="open_library",
        work_key=f"/works/{work_id}",
        editions_loaded=True,
        **fields,
    )


def load_open_library_work_editions(
    work_id: str,
    *,
    query: str = "",
    title: str | None = None,
    authors: list[str] | None = None,
    limit: int = OPEN_LIBRARY_EDITION_LIMIT,
) -> dict:
    clean_work_id = str(work_id or "").strip().removeprefix("/works/")
    if not clean_work_id:
        return {
            "status": "empty",
            "work_id": clean_work_id,
            "edition_count": 0,
            "editions_loaded": True,
            "primary_edition": None,
            "editions": [],
            "message": "Work id is required.",
        }
    bounded_limit = min(50, max(1, int(limit or OPEN_LIBRARY_EDITION_LIMIT)))
    cache_key = (clean_work_id, bounded_limit)
    now = time.monotonic()
    with _edition_lock:
        cached = _edition_cache.get(cache_key)
        if cached and now - cached[0] < OPEN_LIBRARY_EDITION_CACHE_TTL_SECONDS:
            logger.info("open_library_edition_cache_hit work_id=%s limit=%s", clean_work_id, bounded_limit)
            return dict(cached[1])
        future = _edition_inflight.get(cache_key)
        leader = future is None
        if leader:
            future = Future()
            _edition_inflight[cache_key] = future
        else:
            logger.info("open_library_edition_inflight_join work_id=%s limit=%s", clean_work_id, bounded_limit)

    if not leader:
        return dict(future.result())

    try:
        logger.info("open_library_edition_cache_miss work_id=%s limit=%s", clean_work_id, bounded_limit)
        raw_editions = _fetch_open_library_work_editions(clean_work_id, limit=bounded_limit)
        edition_results = [
            _open_library_edition_result(
                edition,
                work_id=clean_work_id,
                fallback_title=title,
                fallback_authors=authors,
            )
            for edition in raw_editions
        ]
        grouped = group_search_results(edition_results, query or title or clean_work_id) if edition_results else []
        work = grouped[0] if grouped else None
        response = {
            "status": "ok" if raw_editions else "empty",
            "work_id": clean_work_id,
            "edition_count": len(raw_editions),
            "editions_loaded": True,
            "primary_edition": work["primary_edition"] if work else None,
            "editions": work["editions"] if work else [],
            "message": None if raw_editions else "No editions were found for this work.",
        }
        with _edition_lock:
            _edition_cache[cache_key] = (time.monotonic(), response)
        future.set_result(response)
        return dict(response)
    except Exception as exc:
        logger.warning(
            "open_library_edition_lookup_failed work_id=%s limit=%s error_type=%s",
            clean_work_id,
            bounded_limit,
            type(exc).__name__,
        )
        future.set_exception(exc)
        raise
    finally:
        with _edition_lock:
            _edition_inflight.pop(cache_key, None)


def _librarything_results(query: str) -> list[dict]:
    from app.integrations import librarything

    isbn = _normalize_isbn(query)
    if isbn:
        related = librarything.fetch_related_isbns(isbn)
        return [] if not related else [
            _normalized_result(
                title=query,
                authors=[],
                isbn_uid=isbn,
                related_isbns=related,
                metadata_source="librarything",
            )
        ]

    work = librarything.fetch_work_by_title(query)
    if not work:
        return []
    return [
        _normalized_result(
            title=work.get("title") or query,
            authors=[],
            related_isbns=work.get("related_isbns") or [],
            metadata_source="librarything",
        )
    ]


def _local_results(books: list[Book], query: str) -> list[dict]:
    terms = [term for term in query.casefold().split() if term]
    results: list[dict] = []
    for book in books:
        searchable = " ".join(
            [
                book.title or "",
                book.authors or "",
                book.isbn_uid or "",
                book.description or "",
                " ".join(book.subjects or []),
                " ".join(book.genres or []),
                book.work_key or "",
                book.edition_key or "",
                str(book.first_publish_year or ""),
                " ".join(
                    ((book.book_metadata or {}).get("librarything", {}) or {}).get(
                        "related_isbns", []
                    )
                ),
            ]
        ).casefold()
        if terms and not all(term in searchable for term in terms):
            continue
        lt_data = (book.book_metadata or {}).get("librarything", {})
        results.append(
            _normalized_result(
                title=book.title,
                authors=[value.strip() for value in (book.authors or "").split(",") if value.strip()],
                isbn_uid=book.isbn_uid,
                description=book.description,
                cover_url=book.cover_url,
                total_pages=book.total_pages,
                subjects=book.subjects or [],
                genres=book.genres or [],
                first_publish_year=book.first_publish_year,
                metadata_source="local",
                work_key=book.work_key,
                edition_key=book.edition_key,
                related_isbns=lt_data.get("related_isbns", []) if isinstance(lt_data, dict) else [],
                already_in_library=True,
            )
        )
    return results


def _normalized_match_text(value: object) -> str:
    return " ".join(re.sub(r"[^a-z0-9]+", " ", str(value or "").casefold()).split())


def _result_isbns(result: dict) -> set[str]:
    values = set(result.get("related_isbns") or [])
    if result.get("isbn_uid"):
        values.add(result["isbn_uid"])
    return {isbn for value in values if (isbn := _normalize_isbn(value))}


def _lead_author(result: dict) -> str:
    authors = result.get("authors") or []
    return str(authors[0]).strip() if authors else ""


def _title_author_match(left: dict, right: dict) -> bool:
    left_title = _normalized_match_text(left.get("title"))
    right_title = _normalized_match_text(right.get("title"))
    if not left_title or not right_title:
        return False
    title_ratio = SequenceMatcher(None, left_title, right_title).ratio()
    if title_ratio < 0.9 and left_title != right_title:
        return False

    left_author = _normalized_match_text(_lead_author(left))
    right_author = _normalized_match_text(_lead_author(right))
    if not left_author or not right_author:
        return title_ratio >= 0.96
    return SequenceMatcher(None, left_author, right_author).ratio() >= 0.82


def _confidence_score(result: dict, query: str) -> float:
    existing_score = float(result.get("confidence_score") or 0.0)
    query_isbn = _normalize_isbn(query)
    score = max(existing_score, 0.25)
    result_isbns = _result_isbns(result)
    if query_isbn and query_isbn in result_isbns:
        score += 0.4
    elif result.get("isbn_uid"):
        score += 0.2

    query_key = _normalized_match_text(query)
    title_key = _normalized_match_text(result.get("title"))
    if title_key and query_key:
        ratio = SequenceMatcher(None, title_key, query_key).ratio()
        if title_key in query_key or query_key in title_key:
            score += 0.2
        else:
            score += max(0.0, ratio - 0.65) * 0.35

    author_key = _normalized_match_text(_lead_author(result))
    if author_key and author_key in query_key:
        score += 0.12
    if result.get("cover_url"):
        score += 0.05
    if result.get("total_pages"):
        score += 0.05
    if result.get("description"):
        score += 0.05
    if result.get("metadata_source") == "local":
        score += 0.08
    return round(min(score, 1.0), 4)


def _merge_search_results(base: dict, incoming: dict, query: str) -> dict:
    base_score = float(base.get("confidence_score") or 0.0)
    incoming_score = float(incoming.get("confidence_score") or 0.0)
    primary, secondary = (incoming, base) if incoming_score >= base_score else (base, incoming)
    merged = dict(primary)

    list_fields = {"authors", "subjects", "genres", "related_isbns"}
    for field in list_fields:
        merged[field] = list(dict.fromkeys([*(primary.get(field) or []), *(secondary.get(field) or [])]))

    for field in (
        "description",
        "cover_url",
        "total_pages",
        "first_publish_year",
        "work_key",
        "edition_key",
        "publisher",
        "publish_date",
        "language",
        "isbn_uid",
        "series_name",
        "series_position",
        "series_position_label",
        "series_type",
        "series_source",
        "series_confidence",
    ):
        if not merged.get(field) and secondary.get(field):
            merged[field] = secondary[field]
    for field in ("series_books", "series_publication_order", "series_chronological_order"):
        if not merged.get(field) and secondary.get(field):
            merged[field] = secondary[field]
    if not merged.get("series") and secondary.get("series"):
        merged["series"] = secondary["series"]

    merged["already_in_library"] = bool(primary.get("already_in_library") or secondary.get("already_in_library"))
    merged["confidence_score"] = _confidence_score(merged, query)
    return merged


def _dedupe_results(results: list[dict], query: str) -> list[dict]:
    merged: list[dict] = []
    for raw_result in results:
        result = _normalized_result(**raw_result)
        result["confidence_score"] = _confidence_score(result, query)
        result_isbns = _result_isbns(result)
        match_index: int | None = None
        for index, existing in enumerate(merged):
            existing_isbns = _result_isbns(existing)
            if (result_isbns and existing_isbns and result_isbns.intersection(existing_isbns)) or _title_author_match(existing, result):
                match_index = index
                break
        if match_index is None:
            merged.append(result)
        else:
            merged[match_index] = _merge_search_results(merged[match_index], result, query)
    return sorted(
        merged,
        key=lambda result: (
            bool(result.get("already_in_library")),
            -float(result.get("confidence_score") or 0.0),
            str(result.get("title") or "").casefold(),
        ),
    )


def _env_int(name: str, default: int, *, minimum: int, maximum: int) -> int:
    try:
        value = int(os.getenv(name, str(default)))
    except (TypeError, ValueError):
        return default
    return max(minimum, min(maximum, value))


def external_provider_limit() -> int:
    return _env_int("EXTERNAL_PROVIDER_LIMIT", DEFAULT_EXTERNAL_PROVIDER_LIMIT, minimum=1, maximum=3)


def _metadata_sources(local_candidates: list[dict], *, allow_external: bool = True):
    from app.integrations.librarything import LibraryThingProvider
    from app.integrations.openlibrary import OpenLibraryProvider

    sources = [LocalCatalogSource(local_candidates)]
    if allow_external:
        sources.extend([OpenLibraryProvider(), LibraryThingProvider()][:external_provider_limit()])
    return sources


async def _aggregate_results(
    query: str,
    local_candidates: list[dict],
    *,
    allow_external: bool = True,
    result_limit: int | None = None,
    timeout_seconds: float | None = None,
):
    service = MetadataAggregationService(
        _metadata_sources(local_candidates, allow_external=allow_external),
        limit=result_limit or SEARCH_RESULT_LIMIT,
        timeout_seconds=timeout_seconds,
    )
    return await service.aggregate(query)


def _run_aggregation(
    query: str,
    local_candidates: list[dict],
    *,
    allow_external: bool = True,
    result_limit: int | None = None,
    timeout_seconds: float | None = None,
):
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(
            _aggregate_results(
                query,
                local_candidates,
                allow_external=allow_external,
                result_limit=result_limit,
                timeout_seconds=timeout_seconds,
            )
        )

    # This path is for callers that invoke the sync service from an async context.
    # FastAPI currently runs this endpoint as a sync route in a worker thread.
    import concurrent.futures

    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
        return executor.submit(
            lambda: asyncio.run(
                _aggregate_results(
                    query,
                    local_candidates,
                    allow_external=allow_external,
                    result_limit=result_limit,
                    timeout_seconds=timeout_seconds,
                )
            )
        ).result()


def _trusted_source_urls(results: list[dict]) -> list[str]:
    urls: list[str] = []
    for result in results:
        for url in result.get("source_urls") or []:
            try:
                if is_trusted_domain(normalize_domain(url)) and url not in urls:
                    urls.append(url)
            except Exception:
                continue
    return urls[:3]


async def _scrape_urls(urls: list[str]) -> list:
    return await asyncio.gather(
        *(scrape_book_metadata(url, allow_unknown_domain=False) for url in urls),
        return_exceptions=True,
    )


def _run_scraping(urls: list[str]) -> list:
    if not urls:
        return []
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(_scrape_urls(urls))

    import concurrent.futures

    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
        return executor.submit(lambda: asyncio.run(_scrape_urls(urls))).result()


def _scraper_outcome(result) -> dict:
    if isinstance(result, Exception):
        return {
            "source": "scraper",
            "success": False,
            "result_count": 0,
            "latency_ms": 0.0,
            "outcome": "failed",
            "http_status": None,
            "request_url": None,
            "response_body": None,
            "error_type": type(result).__name__,
        }
    diagnostic = result.diagnostics
    return {
        "source": "scraper",
        "success": result.status == "success",
        "result_count": 1 if result.metadata else 0,
        "latency_ms": diagnostic.elapsed_ms,
        "outcome": diagnostic.outcome,
        "http_status": diagnostic.http_status,
        "request_url": diagnostic.request_url,
        "response_body": None,
        "error_type": diagnostic.exception_type,
    }


async def _enrich_related_isbns_async(results: list[dict]) -> None:
    from app.integrations import librarything

    async def fetch(result: dict) -> tuple[dict, list[str]]:
        isbn = _normalize_isbn(result.get("isbn_uid"))
        if not isbn:
            return result, []
        try:
            related = await asyncio.wait_for(
                asyncio.to_thread(librarything.fetch_related_isbns, isbn),
                timeout=LIBRARYTHING_ENRICHMENT_TIMEOUT_SECONDS,
            )
            return result, related
        except Exception as exc:
            logger.warning(
                "librarything_related_isbn_enrichment_failed",
                extra={"error_type": type(exc).__name__},
            )
            return result, []

    enriched = await asyncio.gather(*(fetch(result) for result in results))
    for result, related in enriched:
        if related:
            result["related_isbns"] = list(dict.fromkeys([*(result.get("related_isbns") or []), *related]))


def _enrich_related_isbns(results: list[dict]) -> None:
    if not results:
        return
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        asyncio.run(_enrich_related_isbns_async(results))
        return

    import concurrent.futures

    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
        executor.submit(lambda: asyncio.run(_enrich_related_isbns_async(results))).result()


def _mark_duplicates(results: list[dict], books: list[Book]) -> None:
    existing_isbns: set[str] = set()
    existing_work_keys: set[str] = set()
    existing_edition_keys: set[str] = set()
    for book in books:
        if isbn := _normalize_isbn(book.isbn_uid):
            existing_isbns.add(isbn)
        if book.work_key:
            existing_work_keys.add(book.work_key)
        if book.edition_key:
            existing_edition_keys.add(book.edition_key)
        lt_data = (book.book_metadata or {}).get("librarything", {})
        if isinstance(lt_data, dict):
            existing_isbns.update(
                isbn
                for value in lt_data.get("related_isbns", [])
                if (isbn := _normalize_isbn(value))
            )

    for result in results:
        candidate_isbns = set(result.get("related_isbns") or [])
        if result.get("isbn_uid"):
            candidate_isbns.add(result["isbn_uid"])
        result["already_in_library"] = bool(
            result.get("already_in_library")
            or candidate_isbns.intersection(existing_isbns)
            or (result.get("work_key") and result["work_key"] in existing_work_keys)
            or (result.get("edition_key") and result["edition_key"] in existing_edition_keys)
        )


def _search_status(results: list[dict], outcomes) -> tuple[str, str | None]:
    external = [outcome for outcome in outcomes if outcome.source not in {"local", "scraper"}]
    failed = [
        outcome
        for outcome in external
        if not outcome.success and getattr(outcome, "outcome", None) not in {"disabled", "not_configured"}
    ]
    successful = [outcome for outcome in external if outcome.success]
    if external and failed and not successful and not results:
        return "degraded", "All metadata providers failed. Search results may be incomplete."
    if failed:
        return "degraded", "Some metadata providers failed. Search results may be incomplete."
    if not results:
        return "empty", None
    return "ok", None


def search_books(
    db: Session,
    user_id,
    query: str,
    *,
    include_diagnostics: bool = False,
    allow_external: bool = True,
    include_enrichment: bool = True,
) -> dict:
    clean_query = query.strip()
    if not clean_query:
        return {"status": "empty", "results": [], "message": None, "diagnostics": [] if include_diagnostics else None}
    search_started = time.perf_counter()
    books = db.query(Book).filter(Book.user_id == user_id).all()

    aggregation_started = time.perf_counter()
    aggregation = _run_aggregation(
        clean_query,
        _local_results(books, clean_query),
        allow_external=allow_external,
        timeout_seconds=3.0 if allow_external else None,
    )
    aggregation_ms = (time.perf_counter() - aggregation_started) * 1000
    add_timing("book_search_aggregation", aggregation_ms)
    ranked = aggregation.results
    scrape_results = _run_scraping(_trusted_source_urls(ranked)) if include_enrichment else []
    scraped_candidates = [
        result.metadata.to_search_result()
        for result in scrape_results
        if not isinstance(result, Exception) and result.status == "success" and result.metadata is not None
    ]
    if scraped_candidates:
        ranked = _dedupe_results([*ranked, *scraped_candidates], clean_query)[:SEARCH_RESULT_LIMIT]
    if include_enrichment:
        _enrich_related_isbns(ranked)
    _mark_duplicates(ranked, books)
    grouped = group_search_results(ranked, clean_query)
    scrape_outcomes = [_scraper_outcome(result) for result in scrape_results]
    status, message = _search_status(
        grouped,
        [
            *aggregation.outcomes,
            *[
                type("Outcome", (), {"source": item["source"], "success": item["success"]})()
                for item in scrape_outcomes
            ],
        ],
    )
    total_ms = (time.perf_counter() - search_started) * 1000
    add_timing("book_search_total", total_ms)
    logger.info(
        "book_search_stage_timing query_length=%s allow_external=%s include_enrichment=%s "
        "aggregation_ms=%.2f total_ms=%.2f results=%s",
        len(clean_query),
        allow_external,
        include_enrichment,
        aggregation_ms,
        total_ms,
        len(grouped),
    )
    return {
        "status": status,
        "results": grouped,
        "message": message,
        "diagnostics": [
            {
                "source": outcome.source,
                "success": outcome.success,
                "result_count": outcome.result_count,
                "latency_ms": outcome.latency_ms,
                "outcome": outcome.outcome,
                "http_status": outcome.http_status,
                "request_url": outcome.request_url,
                "response_body": outcome.response_body,
                "error_type": outcome.error_type,
            }
            for outcome in aggregation.outcomes
        ] + scrape_outcomes if include_diagnostics else None,
    }
