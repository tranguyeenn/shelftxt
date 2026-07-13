from __future__ import annotations

import asyncio
import re
import time
from dataclasses import asdict, dataclass
from typing import Any, Protocol
from urllib.parse import urlsplit

from sqlalchemy.orm import Session

from backend.db.models import Book
from backend.services.book_scraping.domains import is_trusted_domain, normalize_domain
from backend.services.book_scraping.service import scrape_book_metadata
from backend.services.book_search import (
    SEARCH_RESULT_LIMIT,
    _dedupe_results,
    _local_results,
    _mark_duplicates,
    _open_library_results,
)
from backend.services.work_grouping import group_search_results


@dataclass(frozen=True)
class DiscoveryDiagnostic:
    provider: str
    outcome: str
    request_attempted: bool
    result_count: int
    latency_ms: float
    http_status: int | None = None
    error_type: str | None = None
    transient: bool = False
    parser_version: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class MetadataDiscoveryProvider(Protocol):
    name: str

    async def search(self, query: str, *, limit: int) -> tuple[list[dict], DiscoveryDiagnostic]:
        ...


class OpenLibraryExtendedDiscoveryProvider:
    name = "open_library_extended"

    async def search(self, query: str, *, limit: int) -> tuple[list[dict], DiscoveryDiagnostic]:
        started = time.perf_counter()
        try:
            results = await asyncio.to_thread(_open_library_results, query, limit=limit)
            return results, DiscoveryDiagnostic(
                provider=self.name,
                outcome="success_with_results" if results else "empty_success",
                request_attempted=True,
                result_count=len(results),
                latency_ms=round((time.perf_counter() - started) * 1000, 2),
            )
        except TimeoutError as exc:
            return [], DiscoveryDiagnostic(
                provider=self.name,
                outcome="timeout",
                request_attempted=True,
                result_count=0,
                latency_ms=round((time.perf_counter() - started) * 1000, 2),
                error_type=type(exc).__name__,
                transient=True,
            )
        except Exception as exc:
            return [], DiscoveryDiagnostic(
                provider=self.name,
                outcome="unexpected_error",
                request_attempted=True,
                result_count=0,
                latency_ms=round((time.perf_counter() - started) * 1000, 2),
                error_type=type(exc).__name__,
            )


class TrustedUrlDiscoveryProvider:
    name = "trusted_url_scraper"

    async def search(self, query: str, *, limit: int) -> tuple[list[dict], DiscoveryDiagnostic]:
        started = time.perf_counter()
        url = _query_url(query)
        if url is None:
            return [], DiscoveryDiagnostic(
                provider=self.name,
                outcome="disabled",
                request_attempted=False,
                result_count=0,
                latency_ms=0.0,
            )
        domain = normalize_domain(url)
        if not is_trusted_domain(domain):
            return [], DiscoveryDiagnostic(
                provider=self.name,
                outcome="blocked",
                request_attempted=False,
                result_count=0,
                latency_ms=0.0,
            )

        result = await scrape_book_metadata(url, allow_unknown_domain=False)
        diagnostic = result.diagnostics
        if result.status == "success" and result.metadata is not None:
            records = [result.metadata.to_search_result()]
            outcome = "success_with_results"
        elif result.status == "empty":
            records = []
            outcome = "parse_failure" if diagnostic.outcome == "parsing_failure" else "empty_success"
        elif result.status == "blocked":
            records = []
            outcome = "blocked"
        elif diagnostic.outcome == "timeout":
            records = []
            outcome = "timeout"
        else:
            records = []
            outcome = "unexpected_error"

        return records[:limit], DiscoveryDiagnostic(
            provider=self.name,
            outcome=outcome,
            request_attempted=True,
            result_count=len(records),
            latency_ms=diagnostic.elapsed_ms or round((time.perf_counter() - started) * 1000, 2),
            http_status=diagnostic.http_status,
            error_type=diagnostic.exception_type,
            transient=outcome == "timeout",
            parser_version=diagnostic.parser_used,
        )


def _query_url(query: str) -> str | None:
    raw = str(query or "").strip()
    parsed = urlsplit(raw)
    if parsed.scheme in {"http", "https"} and parsed.netloc:
        return raw
    return None


def _manual_isbn(value: object) -> str | None:
    from backend.services.book_scraping.metadata import normalize_isbn

    return normalize_isbn(value)


def normalize_manual_metadata(data: dict[str, Any]) -> dict[str, Any]:
    title = str(data.get("title") or "").strip()
    authors = data.get("authors")
    if isinstance(authors, str):
        author_values = [part.strip() for part in re.split(r"[,;|]", authors) if part.strip()]
    elif isinstance(authors, list):
        author_values = [str(part).strip() for part in authors if str(part).strip()]
    else:
        author_values = []
    isbn13 = _manual_isbn(data.get("isbn_13"))
    isbn10 = _manual_isbn(data.get("isbn_10"))
    page_count = data.get("page_count")
    try:
        total_pages = int(page_count) if page_count not in (None, "") else None
    except (TypeError, ValueError):
        total_pages = None
    if total_pages is not None and total_pages <= 0:
        total_pages = None
    publication_year = data.get("publication_year")
    if publication_year is None and data.get("publication_date"):
        match = re.search(r"\d{4}", str(data.get("publication_date")))
        publication_year = int(match.group(0)) if match else None
    return {
        "title": title,
        "authors": author_values,
        "isbn_uid": isbn13 or isbn10,
        "description": str(data.get("notes") or "").strip() or None,
        "cover_url": str(data.get("cover_url") or "").strip() or None,
        "total_pages": total_pages,
        "subjects": [],
        "genres": [],
        "first_publish_year": publication_year,
        "metadata_source": "manual",
        "work_key": str(data.get("work_id") or "").strip() or None,
        "edition_key": str(data.get("edition_id") or "").strip() or None,
        "publisher": str(data.get("publisher") or "").strip() or None,
        "publish_date": str(data.get("publication_date") or "").strip() or None,
        "language": str(data.get("language") or "").strip() or None,
        "related_isbns": [],
        "source_urls": [],
        "already_in_library": False,
        "confidence_score": 0.75 if (isbn13 or isbn10) else 0.45,
        "edition_type": str(data.get("edition_type") or "unknown").strip() or "unknown",
        "original_title": str(data.get("original_title") or "").strip() or None,
    }


def likely_manual_duplicates(db: Session, user_id, metadata: dict[str, Any]) -> list[dict[str, Any]]:
    books = db.query(Book).filter(Book.user_id == user_id).all()
    candidate = normalize_manual_metadata(metadata)
    isbn = candidate.get("isbn_uid")
    duplicates: list[dict[str, Any]] = []
    for book in books:
        if isbn and book.isbn_uid == isbn:
            duplicates.append({"id": book.isbn_uid, "title": book.title, "author": book.authors, "reason": "isbn"})
            continue
        if candidate.get("edition_key") and book.edition_key == candidate["edition_key"]:
            duplicates.append({"id": book.isbn_uid, "title": book.title, "author": book.authors, "reason": "edition_id"})
            continue
        if candidate.get("work_key") and book.work_key == candidate["work_key"]:
            duplicates.append({"id": book.isbn_uid, "title": book.title, "author": book.authors, "reason": "work_id"})
    return duplicates


async def _run_discovery(query: str, *, limit: int) -> tuple[list[dict], list[DiscoveryDiagnostic]]:
    providers: list[MetadataDiscoveryProvider] = [
        OpenLibraryExtendedDiscoveryProvider(),
        TrustedUrlDiscoveryProvider(),
    ]
    responses = await asyncio.gather(*(provider.search(query, limit=limit) for provider in providers))
    results: list[dict] = []
    diagnostics: list[DiscoveryDiagnostic] = []
    for provider_results, diagnostic in responses:
        results.extend(provider_results)
        diagnostics.append(diagnostic)
    return results, diagnostics


def discover_books(db: Session, user_id, query: str, *, limit: int = SEARCH_RESULT_LIMIT) -> dict:
    clean_query = str(query or "").strip()
    if not clean_query:
        return {"status": "empty", "results": [], "message": None, "diagnostics": []}
    books = db.query(Book).filter(Book.user_id == user_id).all()
    remote_results, diagnostics = asyncio.run(_run_discovery(clean_query, limit=limit))
    ranked = _dedupe_results([*_local_results(books, clean_query), *remote_results], clean_query)[:limit]
    _mark_duplicates(ranked, books)
    grouped = group_search_results(ranked, clean_query)
    has_results = bool(grouped)
    has_attempted_failure = any(
        item.request_attempted and item.outcome not in {"success_with_results", "empty_success", "disabled"}
        for item in diagnostics
    )
    return {
        "status": "ok" if has_results else "degraded" if has_attempted_failure else "empty",
        "results": grouped,
        "message": None if has_results else "No additional metadata source found a reliable match.",
        "diagnostics": [item.to_dict() for item in diagnostics],
    }
