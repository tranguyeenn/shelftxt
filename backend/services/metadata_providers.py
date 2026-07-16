"""Provider orchestration primitives for resilient metadata search."""

from __future__ import annotations

import asyncio
import logging
import os
import time
from abc import ABC, abstractmethod
from dataclasses import asdict, dataclass
from typing import Any, Literal

import httpx

logger = logging.getLogger(__name__)


TRANSIENT_STATUS_CODES = {408, 425, 429, 500, 502, 503, 504}
ProviderOutcome = Literal[
    "success",
    "success_with_results",
    "empty_success",
    "disabled",
    "not_configured",
    "blocked",
    "http_failure",
    "http_error",
    "network_failure",
    "timeout",
    "parsing_failure",
    "parse_failure",
    "provider_failure",
    "unexpected_error",
]


@dataclass
class ProviderHealth:
    name: str
    healthy: bool = True
    consecutive_failures: int = 0
    last_success_at: float | None = None
    last_failure_at: float | None = None
    last_latency_ms: float | None = None
    last_error_type: str | None = None


@dataclass
class ProviderDiagnostic:
    provider: str
    outcome: ProviderOutcome
    elapsed_ms: float
    http_status: int | None = None
    request_url: str | None = None
    response_body: str | None = None
    exception_type: str | None = None
    result_count: int = 0

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class ProviderSearchResult:
    provider: str
    results: list[dict]
    diagnostic: ProviderDiagnostic


class ProviderSearchError(Exception):
    def __init__(
        self,
        message: str,
        *,
        provider: str,
        outcome: ProviderOutcome,
        elapsed_ms: float = 0.0,
        http_status: int | None = None,
        request_url: str | None = None,
        response_body: str | None = None,
        exception_type: str | None = None,
    ) -> None:
        super().__init__(message)
        self.provider = provider
        self.outcome = outcome
        self.elapsed_ms = elapsed_ms
        self.http_status = http_status
        self.request_url = request_url
        self.response_body = response_body
        self.exception_type = exception_type

    def diagnostic(self, fallback_elapsed_ms: float) -> ProviderDiagnostic:
        return ProviderDiagnostic(
            provider=self.provider,
            outcome=self.outcome,
            elapsed_ms=round(self.elapsed_ms or fallback_elapsed_ms, 2),
            http_status=self.http_status,
            request_url=self.request_url,
            response_body=self.response_body,
            exception_type=self.exception_type,
        )


class ProviderHealthTracker:
    def __init__(self) -> None:
        self._health: dict[str, ProviderHealth] = {}
        self._lock = asyncio.Lock()

    async def record_success(self, name: str, latency_ms: float) -> None:
        async with self._lock:
            current = self._health.setdefault(name, ProviderHealth(name=name))
            current.healthy = True
            current.consecutive_failures = 0
            current.last_success_at = time.time()
            current.last_latency_ms = latency_ms
            current.last_error_type = None

    async def record_failure(self, name: str, latency_ms: float, exc: BaseException) -> None:
        async with self._lock:
            current = self._health.setdefault(name, ProviderHealth(name=name))
            current.healthy = False
            current.consecutive_failures += 1
            current.last_failure_at = time.time()
            current.last_latency_ms = latency_ms
            current.last_error_type = type(exc).__name__

    def snapshot(self) -> dict[str, dict[str, Any]]:
        return {name: asdict(value) for name, value in self._health.items()}


provider_health_tracker = ProviderHealthTracker()

FAILURE_CACHE_OUTCOMES = {"timeout", "network_failure"}
DEFAULT_PROVIDER_FAILURE_CACHE_TTL_SECONDS = 300
_provider_failure_cache: dict[tuple[str, str], tuple[float, ProviderDiagnostic]] = {}


def _failure_cache_ttl_seconds() -> int:
    try:
        value = int(os.getenv("PROVIDER_FAILURE_CACHE_TTL_SECONDS", str(DEFAULT_PROVIDER_FAILURE_CACHE_TTL_SECONDS)))
    except (TypeError, ValueError):
        return DEFAULT_PROVIDER_FAILURE_CACHE_TTL_SECONDS
    return max(0, min(1800, value))


def _cache_key(provider: str, query: str) -> tuple[str, str]:
    return (provider, " ".join(str(query or "").casefold().split()))


def _cached_failure(provider: str, query: str) -> ProviderDiagnostic | None:
    ttl = _failure_cache_ttl_seconds()
    if ttl <= 0:
        return None
    key = _cache_key(provider, query)
    cached = _provider_failure_cache.get(key)
    if cached is None:
        return None
    cached_at, diagnostic = cached
    if time.monotonic() - cached_at >= ttl:
        _provider_failure_cache.pop(key, None)
        return None
    return ProviderDiagnostic(
        provider=diagnostic.provider,
        outcome=diagnostic.outcome,
        elapsed_ms=0.0,
        http_status=diagnostic.http_status,
        request_url=diagnostic.request_url,
        response_body=diagnostic.response_body,
        exception_type="CachedProviderFailure",
        result_count=0,
    )


def _remember_failure(provider: str, query: str, diagnostic: ProviderDiagnostic) -> None:
    if diagnostic.outcome in FAILURE_CACHE_OUTCOMES and _failure_cache_ttl_seconds() > 0:
        _provider_failure_cache[_cache_key(provider, query)] = (time.monotonic(), diagnostic)


def clear_provider_failure_cache() -> None:
    _provider_failure_cache.clear()


class MetadataProvider(ABC):
    name: str
    timeout_seconds: float = 3.0
    max_retries: int = 1

    @abstractmethod
    async def search(self, query: str) -> list[dict]:
        """Return normalized provider records for a search query."""


def is_transient_error(exc: BaseException) -> bool:
    if isinstance(
        exc,
        (
            httpx.ConnectError,
            httpx.ConnectTimeout,
            httpx.NetworkError,
            httpx.PoolTimeout,
            httpx.ReadError,
            httpx.ReadTimeout,
            httpx.RemoteProtocolError,
            httpx.TimeoutException,
            asyncio.TimeoutError,
        ),
    ):
        return True
    if isinstance(exc, httpx.HTTPStatusError):
        return exc.response.status_code in TRANSIENT_STATUS_CODES
    return False


def provider_outcome_for_exception(exc: BaseException) -> ProviderOutcome:
    if isinstance(exc, ProviderSearchError):
        return exc.outcome
    if isinstance(exc, (httpx.TimeoutException, asyncio.TimeoutError)):
        return "timeout"
    if isinstance(exc, httpx.HTTPStatusError):
        return "http_failure"
    if isinstance(exc, httpx.RequestError):
        return "network_failure"
    if isinstance(exc, ValueError):
        return "parsing_failure"
    return "provider_failure"


def diagnostic_for_exception(
    provider: str,
    exc: BaseException,
    *,
    elapsed_ms: float,
) -> ProviderDiagnostic:
    if isinstance(exc, ProviderSearchError):
        return exc.diagnostic(elapsed_ms)
    response = exc.response if isinstance(exc, httpx.HTTPStatusError) else None
    request = exc.request if isinstance(exc, httpx.RequestError) else None
    body = None
    if response is not None:
        try:
            body = response.text[:1000]
        except Exception:
            body = None
    return ProviderDiagnostic(
        provider=provider,
        outcome=provider_outcome_for_exception(exc),
        elapsed_ms=round(elapsed_ms, 2),
        http_status=response.status_code if response is not None else None,
        request_url=str((response.request if response is not None else request).url)
        if (response is not None or request is not None)
        else None,
        response_body=body,
        exception_type=type(exc).__name__,
    )


async def search_provider(provider: MetadataProvider, query: str) -> ProviderSearchResult:
    """Run one provider with timeout, transient retry, health, and fail-open behavior."""
    cached = _cached_failure(provider.name, query)
    if cached is not None:
        logger.info(
            "metadata_provider_failure_cache_hit",
            extra={"provider": provider.name, "outcome": cached.outcome},
        )
        return ProviderSearchResult(provider=provider.name, results=[], diagnostic=cached)

    attempts = provider.max_retries + 1
    last_diagnostic: ProviderDiagnostic | None = None
    for attempt in range(1, attempts + 1):
        started = time.perf_counter()
        try:
            results = await asyncio.wait_for(
                provider.search(query),
                timeout=provider.timeout_seconds,
            )
            latency_ms = (time.perf_counter() - started) * 1000
            await provider_health_tracker.record_success(provider.name, latency_ms)
            logger.info(
                "metadata_provider_search_success",
                extra={
                    "provider": provider.name,
                    "attempt": attempt,
                    "latency_ms": round(latency_ms, 2),
                    "result_count": len(results),
                },
            )
            outcome: ProviderOutcome = "success" if results else "empty_success"
            diagnostic = ProviderDiagnostic(
                provider=provider.name,
                outcome=outcome,
                elapsed_ms=round(latency_ms, 2),
                result_count=len(results),
            )
            logger.info(
                "metadata_provider_search_completed",
                extra=diagnostic.to_dict(),
            )
            return ProviderSearchResult(
                provider=provider.name,
                results=results,
                diagnostic=diagnostic,
            )
        except Exception as exc:
            latency_ms = (time.perf_counter() - started) * 1000
            await provider_health_tracker.record_failure(provider.name, latency_ms, exc)
            last_diagnostic = diagnostic_for_exception(provider.name, exc, elapsed_ms=latency_ms)
            logger.warning(
                "metadata_provider_search_failed",
                extra={
                    "provider": provider.name,
                    "attempt": attempt,
                    "latency_ms": round(latency_ms, 2),
                    "outcome": last_diagnostic.outcome,
                    "http_status": last_diagnostic.http_status,
                    "request_url": last_diagnostic.request_url,
                    "response_body": last_diagnostic.response_body,
                    "error_type": type(exc).__name__,
                    "transient": is_transient_error(exc),
                },
            )
            if attempt >= attempts or not is_transient_error(exc):
                _remember_failure(provider.name, query, last_diagnostic)
                return ProviderSearchResult(
                    provider=provider.name,
                    results=[],
                    diagnostic=last_diagnostic,
                )
            await asyncio.sleep(0.1 * attempt)
    fallback = last_diagnostic or ProviderDiagnostic(
        provider=provider.name,
        outcome="provider_failure",
        elapsed_ms=0.0,
    )
    return ProviderSearchResult(provider=provider.name, results=[], diagnostic=fallback)


async def search_all_providers(query: str, providers: list[MetadataProvider]) -> list[ProviderSearchResult]:
    """Search every provider independently and keep per-provider diagnostics."""
    provider_results = await asyncio.gather(
        *(search_provider(provider, query) for provider in providers),
        return_exceptions=True,
    )
    normalized: list[ProviderSearchResult] = []
    for provider, result in zip(providers, provider_results, strict=False):
        if isinstance(result, Exception):
            normalized.append(
                ProviderSearchResult(
                    provider=provider.name,
                    results=[],
                    diagnostic=diagnostic_for_exception(provider.name, result, elapsed_ms=0.0),
                )
            )
        else:
            normalized.append(result)
    return normalized


def provider_health_snapshot() -> dict[str, dict[str, Any]]:
    return provider_health_tracker.snapshot()
