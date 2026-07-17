"""Concurrent aggregation and ranking for book metadata candidates."""

from __future__ import annotations

import asyncio
import logging
import re
import time
from dataclasses import dataclass, field
from difflib import SequenceMatcher
from typing import Any, Protocol

from backend.services.metadata_providers import MetadataProvider, search_provider
from backend.services.series_metadata import normalize_series_metadata

logger = logging.getLogger(__name__)


class MetadataSource(Protocol):
    name: str
    timeout_seconds: float

    async def search(self, query: str) -> list[dict]:
        """Return normalized-ish metadata candidates for a query."""


@dataclass(frozen=True)
class SourceOutcome:
    source: str
    success: bool
    result_count: int = 0
    latency_ms: float = 0.0
    outcome: str = "success"
    http_status: int | None = None
    request_url: str | None = None
    response_body: str | None = None
    error_type: str | None = None


@dataclass(frozen=True)
class MetadataAggregationResult:
    results: list[dict]
    outcomes: tuple[SourceOutcome, ...] = field(default_factory=tuple)


class LocalCatalogSource:
    name = "local"
    timeout_seconds = 0.25

    def __init__(self, candidates: list[dict]) -> None:
        self._candidates = candidates

    async def search(self, _query: str) -> list[dict]:
        return self._candidates


class MetadataAggregationService:
    def __init__(
        self,
        sources: list[MetadataSource],
        *,
        limit: int = 12,
        timeout_seconds: float | None = None,
    ) -> None:
        self.sources = sources
        self.limit = limit
        self.timeout_seconds = timeout_seconds

    async def aggregate(self, query: str) -> MetadataAggregationResult:
        clean_query = str(query or "").strip()
        if not clean_query:
            return MetadataAggregationResult(results=[])

        if not any(source.name == "hardcover" for source in self.sources):
            tasks = {
                asyncio.create_task(self._search_source(source, clean_query)): source
                for source in self.sources
            }
            if self.timeout_seconds is None:
                collected = await asyncio.gather(*tasks.keys(), return_exceptions=False)
            else:
                done, pending = await asyncio.wait(tasks.keys(), timeout=max(0.0, self.timeout_seconds))
                for task in pending:
                    task.cancel()
                if pending:
                    await asyncio.gather(*pending, return_exceptions=True)
                collected = [task.result() for task in done]
                collected.extend(
                    (
                        SourceOutcome(
                            source=tasks[task].name,
                            success=False,
                            latency_ms=round(self.timeout_seconds * 1000, 2),
                            outcome="timeout",
                            error_type="TimeoutError",
                        ),
                        [],
                    )
                    for task in pending
                )
            candidates = [candidate for outcome, results in collected if outcome.success for candidate in results]
            ranked = _dedupe_and_rank(candidates, clean_query)[: self.limit]
            return MetadataAggregationResult(
                results=ranked,
                outcomes=tuple(outcome for outcome, _results in collected),
            )

        collected: list[tuple[SourceOutcome, list[dict]]] = []
        started = time.perf_counter()
        for source in self.sources:
            if self.timeout_seconds is not None and (time.perf_counter() - started) >= self.timeout_seconds:
                collected.append(
                    (
                        SourceOutcome(
                            source=source.name,
                            success=False,
                            latency_ms=round(self.timeout_seconds * 1000, 2),
                            outcome="timeout",
                            error_type="TimeoutError",
                        ),
                        [],
                    )
                )
                continue
            outcome, results = await self._search_source(source, clean_query)
            collected.append((outcome, results))
            if source.name == "local":
                continue
            if source.name == "hardcover" and outcome.success and len(results) >= self.limit:
                break
            current_results = [candidate for current_outcome, current in collected if current_outcome.success for candidate in current]
            if source.name == "hardcover" and outcome.success and len(current_results) >= max(3, min(self.limit, len(results))):
                break
        candidates = [candidate for outcome, results in collected if outcome.success for candidate in results]
        ranked = _dedupe_and_rank(candidates, clean_query)[: self.limit]
        return MetadataAggregationResult(
            results=ranked,
            outcomes=tuple(outcome for outcome, _results in collected),
        )

    async def _search_source(
        self,
        source: MetadataSource,
        query: str,
    ) -> tuple[SourceOutcome, list[dict]]:
        started = time.perf_counter()
        try:
            if isinstance(source, MetadataProvider):
                provider_result = await search_provider(source, query)
                diagnostic = provider_result.diagnostic
                results = provider_result.results
                success = diagnostic.outcome in {"success", "empty_success"}
                return (
                    SourceOutcome(
                        source=source.name,
                        success=success,
                        result_count=len(results),
                        latency_ms=diagnostic.elapsed_ms,
                        outcome=diagnostic.outcome,
                        http_status=diagnostic.http_status,
                        request_url=diagnostic.request_url,
                        response_body=diagnostic.response_body,
                        error_type=diagnostic.exception_type,
                    ),
                    results,
                )
            else:
                results = await asyncio.wait_for(source.search(query), timeout=source.timeout_seconds)
            latency_ms = (time.perf_counter() - started) * 1000
            logger.info(
                "metadata_aggregation_source_success",
                extra={
                    "source": source.name,
                    "latency_ms": round(latency_ms, 2),
                    "result_count": len(results),
                },
            )
            return (
                SourceOutcome(
                    source=source.name,
                    success=True,
                    result_count=len(results),
                    latency_ms=round(latency_ms, 2),
                    outcome="success" if results else "empty_success",
                ),
                results,
            )
        except Exception as exc:
            latency_ms = (time.perf_counter() - started) * 1000
            logger.warning(
                "metadata_aggregation_source_failed",
                extra={
                    "source": source.name,
                    "latency_ms": round(latency_ms, 2),
                    "error_type": type(exc).__name__,
                },
            )
            return (
                SourceOutcome(
                    source=source.name,
                    success=False,
                    latency_ms=round(latency_ms, 2),
                    outcome="timeout" if isinstance(exc, (TimeoutError, asyncio.TimeoutError)) else "provider_failure",
                    error_type=type(exc).__name__,
                ),
                [],
            )


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


def _normalized_result(**values: Any) -> dict:
    authors = values.get("authors") or []
    if isinstance(authors, str):
        authors = [authors]
    series = normalize_series_metadata(values.get("series") if isinstance(values.get("series"), dict) else values)
    result = {
        "title": _clean_text(values.get("title")) or "Untitled",
        "authors": [str(author).strip() for author in authors if str(author).strip()],
        "isbn_uid": _normalize_isbn(values.get("isbn_uid") or values.get("isbn")),
        "description": _clean_text(values.get("description")),
        "cover_url": _clean_text(values.get("cover_url")),
        "total_pages": _positive_int(values.get("total_pages")),
        "subjects": list(dict.fromkeys(values.get("subjects") or [])),
        "genres": list(dict.fromkeys(values.get("genres") or [])),
        "first_publish_year": _positive_int(values.get("first_publish_year")),
        "metadata_source": values.get("metadata_source") or values.get("source") or "unknown",
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
        "provider_rating": values.get("provider_rating"),
        "provider_rating_count": _positive_int(values.get("provider_rating_count")),
        "provider_user_count": _positive_int(values.get("provider_user_count")),
        "provider_activity_count": _positive_int(values.get("provider_activity_count")),
        "discovery_reason": _clean_text(values.get("discovery_reason")),
    }
    if series:
        result.update(series)
        result["series"] = series
    return result


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


def _merge_results(base: dict, incoming: dict, query: str) -> dict:
    base_score = float(base.get("confidence_score") or 0.0)
    incoming_score = float(incoming.get("confidence_score") or 0.0)
    primary, secondary = (incoming, base) if incoming_score > base_score else (base, incoming)
    merged = dict(primary)

    for field_name in {"authors", "subjects", "genres", "related_isbns", "source_urls"}:
        merged[field_name] = list(
            dict.fromkeys([*(primary.get(field_name) or []), *(secondary.get(field_name) or [])])
        )

    for field_name in (
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
        "provider_rating",
        "provider_rating_count",
        "provider_user_count",
        "provider_activity_count",
        "discovery_reason",
    ):
        if not merged.get(field_name) and secondary.get(field_name):
            merged[field_name] = secondary[field_name]
    for field_name in ("series_books", "series_publication_order", "series_chronological_order"):
        if not merged.get(field_name) and secondary.get(field_name):
            merged[field_name] = secondary[field_name]
    if not merged.get("series") and secondary.get("series"):
        merged["series"] = secondary["series"]

    merged["already_in_library"] = bool(primary.get("already_in_library") or secondary.get("already_in_library"))
    merged["confidence_score"] = _confidence_score(merged, query)
    return merged


def _dedupe_and_rank(results: list[dict], query: str) -> list[dict]:
    merged: list[dict] = []
    for raw_result in results:
        result = _normalized_result(**raw_result)
        result["confidence_score"] = _confidence_score(result, query)
        result_isbns = _result_isbns(result)
        match_index: int | None = None
        for index, existing in enumerate(merged):
            existing_isbns = _result_isbns(existing)
            if (
                result_isbns
                and existing_isbns
                and result_isbns.intersection(existing_isbns)
            ) or _title_author_match(existing, result):
                match_index = index
                break
        if match_index is None:
            merged.append(result)
        else:
            merged[match_index] = _merge_results(merged[match_index], result, query)

    return sorted(
        merged,
        key=lambda result: (
            bool(result.get("already_in_library")),
            -float(result.get("confidence_score") or 0.0),
            str(result.get("title") or "").casefold(),
        ),
    )
