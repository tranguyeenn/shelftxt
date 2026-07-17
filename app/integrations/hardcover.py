"""Hardcover GraphQL metadata provider for recommendation discovery."""

from __future__ import annotations

import asyncio
import hashlib
import os
import re
import time
from typing import Any

import httpx

from backend.services.metadata_providers import MetadataProvider, ProviderSearchError

DEFAULT_API_URL = "https://api.hardcover.app/v1/graphql"
DEFAULT_TIMEOUT_SECONDS = 2.5
DEFAULT_MAX_RESULTS_PER_QUERY = 12
DEFAULT_MAX_QUERIES_PER_CLUSTER = 1
RESULT_CACHE_SECONDS = 60 * 60
MAX_CACHE_ENTRIES = 256


def hardcover_enabled() -> bool:
    raw = str(os.getenv("HARDCOVER_ENABLED", "")).strip().casefold()
    if raw in {"0", "false", "no", "off"}:
        return False
    return bool(_token())


def hardcover_api_url() -> str:
    return (os.getenv("HARDCOVER_API_URL") or DEFAULT_API_URL).strip() or DEFAULT_API_URL


def _token() -> str | None:
    return (os.getenv("HARDCOVER_API_TOKEN") or "").strip() or None


def hardcover_timeout_seconds() -> float:
    try:
        value = float(os.getenv("HARDCOVER_TIMEOUT_SECONDS", str(DEFAULT_TIMEOUT_SECONDS)))
    except (TypeError, ValueError):
        return DEFAULT_TIMEOUT_SECONDS
    return max(0.25, min(8.0, value))


def hardcover_max_results_per_query() -> int:
    try:
        value = int(os.getenv("HARDCOVER_MAX_RESULTS_PER_QUERY", str(DEFAULT_MAX_RESULTS_PER_QUERY)))
    except (TypeError, ValueError):
        return DEFAULT_MAX_RESULTS_PER_QUERY
    return max(1, min(25, value))


def hardcover_max_queries_per_cluster() -> int:
    try:
        value = int(os.getenv("HARDCOVER_MAX_QUERIES_PER_CLUSTER", str(DEFAULT_MAX_QUERIES_PER_CLUSTER)))
    except (TypeError, ValueError):
        return DEFAULT_MAX_QUERIES_PER_CLUSTER
    return max(1, min(3, value))


SEARCH_QUERY = """
query ShelfTxtHardcoverSearch($query: String!, $limit: Int!) {
  search(query: $query, query_type: "Book", page: 1, per_page: $limit) {
    ids
    results
  }
}
"""


BOOK_DETAILS_QUERY = """
query ShelfTxtHardcoverBookDetails($ids: [Int!], $limit: Int!) {
  books(where: {id: {_in: $ids}}, limit: $limit) {
    id
    title
    subtitle
    slug
    description
    headline
    cached_tags
    cached_contributors
    cached_image
    rating
    ratings_count
    users_count
    activities_count
    release_date
    pages
    image { url }
    contributions(limit: 8) {
      contribution
      author { id name }
    }
    book_series(limit: 4) {
      position
      series { id name slug }
    }
    editions(limit: 8) {
      id
      title
      isbn_10
      isbn_13
      release_date
      release_year
      pages
      cached_image
      image { url }
      language { code2 code3 language }
      publisher { name }
    }
  }
}
"""

_result_cache: dict[str, tuple[float, list[dict]]] = {}


def clear_hardcover_cache() -> None:
    _result_cache.clear()


def _cache_key(query: str, limit: int) -> str:
    return hashlib.sha256(f"{query.strip().casefold()}|{limit}".encode("utf-8")).hexdigest()


def _cache_get(query: str, limit: int) -> list[dict] | None:
    key = _cache_key(query, limit)
    cached = _result_cache.get(key)
    if not cached:
        return None
    cached_at, results = cached
    if time.monotonic() - cached_at >= RESULT_CACHE_SECONDS:
        _result_cache.pop(key, None)
        return None
    return [dict(result, cache_hit=True) for result in results]


def _cache_set(query: str, limit: int, results: list[dict]) -> None:
    if len(_result_cache) >= MAX_CACHE_ENTRIES:
        oldest = min(_result_cache, key=lambda key: _result_cache[key][0])
        _result_cache.pop(oldest, None)
    _result_cache[_cache_key(query, limit)] = (time.monotonic(), [dict(result) for result in results])


def _clean_text(value: object) -> str | None:
    text = str(value or "").strip()
    return text or None


def _positive_int(value: object) -> int | None:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return None
    return parsed if parsed > 0 else None


def _normalize_isbn(value: object) -> str | None:
    cleaned = re.sub(r"[^0-9Xx]", "", str(value or "")).upper()
    return cleaned if len(cleaned) in {10, 13} else None


def _year_from_date(value: object) -> int | None:
    match = re.match(r"^(\d{4})", str(value or ""))
    if not match:
        return None
    parsed = int(match.group(1))
    return parsed if 1000 <= parsed <= 9999 else None


def _json_strings(value: object) -> list[str]:
    found: list[str] = []

    def walk(item: object) -> None:
        if isinstance(item, dict):
            for key, nested in item.items():
                if str(key).casefold() in {"tag", "name", "genre", "mood", "category"}:
                    walk(nested)
                elif isinstance(nested, (dict, list, tuple)):
                    walk(nested)
            return
        if isinstance(item, (list, tuple)):
            for nested in item:
                walk(nested)
            return
        text = _clean_text(item)
        if text and 2 <= len(text) <= 80:
            found.append(text)

    walk(value)
    return list(dict.fromkeys(found))


def _authors(book: dict) -> list[str]:
    contributors = _json_strings(book.get("cached_contributors"))
    contribution_authors = [
        author
        for item in book.get("contributions") or []
        if isinstance(item, dict)
        for author in [_clean_text(((item.get("author") or {}) if isinstance(item.get("author"), dict) else {}).get("name"))]
        if author
    ]
    return list(dict.fromkeys([*contribution_authors, *contributors]))[:5]


def _cover_url(book: dict) -> str | None:
    image = book.get("image") if isinstance(book.get("image"), dict) else {}
    if image.get("url"):
        return _clean_text(image.get("url"))
    cached = book.get("cached_image") if isinstance(book.get("cached_image"), dict) else {}
    if cached.get("url"):
        return _clean_text(cached.get("url"))
    for edition in book.get("editions") or []:
        edition_image = edition.get("image") if isinstance(edition.get("image"), dict) else {}
        if edition_image.get("url"):
            return _clean_text(edition_image.get("url"))
        cached_edition = edition.get("cached_image") if isinstance(edition.get("cached_image"), dict) else {}
        if cached_edition.get("url"):
            return _clean_text(cached_edition.get("url"))
    return None


def _edition_values(book: dict) -> tuple[
    str | None,
    list[str],
    int | None,
    str | None,
    str | None,
    str | None,
    list[str],
    list[int],
    str,
]:
    related_isbns: list[str] = []
    work_release_date = _clean_text(book.get("release_date"))
    first_year = _year_from_date(work_release_date)
    isbn_uid = None
    language = None
    publisher = None
    publish_date = work_release_date
    edition_release_dates: list[str] = []
    edition_release_years: list[int] = []
    for edition in book.get("editions") or []:
        for key in ("isbn_13", "isbn_10"):
            isbn = _normalize_isbn(edition.get(key))
            if isbn and isbn not in related_isbns:
                related_isbns.append(isbn)
            if isbn and isbn_uid is None:
                isbn_uid = isbn
        edition_date = _clean_text(edition.get("release_date"))
        edition_year = _positive_int(edition.get("release_year")) or _year_from_date(edition_date)
        if edition_date and edition_date not in edition_release_dates:
            edition_release_dates.append(edition_date)
        if edition_year and edition_year not in edition_release_years:
            edition_release_years.append(edition_year)
        first_year = first_year or edition_year
        publish_date = publish_date or edition_date
        lang = edition.get("language") if isinstance(edition.get("language"), dict) else {}
        language = language or _clean_text(lang.get("code3") or lang.get("code2") or lang.get("language"))
        pub = edition.get("publisher") if isinstance(edition.get("publisher"), dict) else {}
        publisher = publisher or _clean_text(pub.get("name"))
    year_source = "work" if first_year and _year_from_date(work_release_date) else "edition" if first_year else "unknown"
    return (
        isbn_uid,
        related_isbns,
        first_year,
        language,
        publisher,
        publish_date,
        edition_release_dates,
        edition_release_years,
        year_source,
    )


def _series_values(book: dict) -> dict:
    for entry in book.get("book_series") or []:
        series = entry.get("series") if isinstance(entry.get("series"), dict) else {}
        name = _clean_text(series.get("name"))
        if not name:
            continue
        return {
            "series_name": name,
            "series_position": entry.get("position"),
            "series_type": "main",
            "series_source": "hardcover",
            "series_confidence": 0.86,
        }
    return {}


def _normalize_book(book: dict, *, query: str) -> dict | None:
    title = _clean_text(book.get("title"))
    authors = _authors(book)
    if not title or not authors:
        return None
    (
        isbn_uid,
        related_isbns,
        first_year,
        language,
        publisher,
        publish_date,
        edition_release_dates,
        edition_release_years,
        year_source,
    ) = _edition_values(book)
    tags = _json_strings(book.get("cached_tags"))
    genres = tags[:8]
    subjects = tags[8:24]
    description = _clean_text(book.get("description") or book.get("headline"))
    if not (genres or subjects or description or _series_values(book)):
        return None
    book_id = _positive_int(book.get("id"))
    slug = _clean_text(book.get("slug"))
    source_url = f"https://hardcover.app/books/{slug}" if slug else f"https://hardcover.app/books/{book_id}" if book_id else None
    result = {
        "title": title,
        "subtitle": _clean_text(book.get("subtitle")),
        "headline": _clean_text(book.get("headline")),
        "authors": authors,
        "isbn_uid": isbn_uid,
        "description": description,
        "cover_url": _cover_url(book),
        "total_pages": _positive_int(book.get("pages")),
        "subjects": subjects,
        "genres": genres,
        "first_publish_year": first_year,
        "publication_year": first_year,
        "publication_year_source": year_source,
        "release_date": _clean_text(book.get("release_date")),
        "work_publication_date": _clean_text(book.get("release_date")),
        "work_publication_year": _year_from_date(book.get("release_date")),
        "edition_release_dates": edition_release_dates,
        "edition_release_years": edition_release_years,
        "metadata_source": "hardcover",
        "work_key": f"hardcover:book:{book_id}" if book_id else None,
        "edition_key": f"hardcover:edition:{book_id}" if book_id else None,
        "publisher": publisher,
        "publish_date": publish_date,
        "language": language,
        "related_isbns": related_isbns,
        "cached_tags": tags,
        "source_urls": [source_url] if source_url else [],
        "confidence_score": 0.72,
        "provider_rating": float(book.get("rating")) if book.get("rating") is not None else None,
        "provider_rating_count": _positive_int(book.get("ratings_count")),
        "provider_user_count": _positive_int(book.get("users_count")),
        "provider_activity_count": _positive_int(book.get("activities_count")),
        "discovery_reason": f"Hardcover search for {query}",
    }
    result.update(_series_values(book))
    return result


def _ids_from_search(search_payload: dict) -> list[int]:
    ids = search_payload.get("ids") if isinstance(search_payload, dict) else []
    parsed: list[int] = []
    for value in ids or []:
        integer = _positive_int(value)
        if integer and integer not in parsed:
            parsed.append(integer)
    return parsed


class HardcoverProvider(MetadataProvider):
    name = "hardcover"
    max_retries = 0

    @property
    def timeout_seconds(self) -> float:
        return hardcover_timeout_seconds()

    async def search(self, query: str) -> list[dict]:
        if not hardcover_enabled():
            raise ProviderSearchError(
                "Hardcover is disabled or not configured",
                provider=self.name,
                outcome="not_configured",
                exception_type="MissingConfiguration",
            )
        token = _token()
        if not token:
            raise ProviderSearchError(
                "Hardcover token is not configured",
                provider=self.name,
                outcome="not_configured",
                exception_type="MissingConfiguration",
            )
        limit = hardcover_max_results_per_query()
        cached = _cache_get(query, limit)
        if cached is not None:
            return cached
        timeout = httpx.Timeout(self.timeout_seconds, connect=min(1.0, self.timeout_seconds))
        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        }
        async with httpx.AsyncClient(timeout=timeout, follow_redirects=True) as client:
            ids = await self._search_ids(client, query, limit, headers)
            if not ids:
                _cache_set(query, limit, [])
                return []
            details = await self._book_details(client, ids[:limit], limit, headers)
        normalized = [
            result
            for book in details
            if (result := _normalize_book(book, query=query)) is not None
        ][:limit]
        _cache_set(query, limit, normalized)
        return normalized

    async def _graphql(self, client: httpx.AsyncClient, query: str, variables: dict, headers: dict) -> dict:
        try:
            response = await client.post(hardcover_api_url(), json={"query": query, "variables": variables}, headers=headers)
            response.raise_for_status()
            payload = response.json()
        except httpx.HTTPStatusError as exc:
            outcome = "http_error" if exc.response.status_code in {401, 403} else "http_failure"
            raise ProviderSearchError(
                "Hardcover GraphQL HTTP error",
                provider=self.name,
                outcome=outcome,
                http_status=exc.response.status_code,
                request_url=hardcover_api_url(),
                response_body=exc.response.text[:1000],
                exception_type=type(exc).__name__,
            ) from exc
        except ValueError as exc:
            raise ProviderSearchError(
                "Hardcover GraphQL malformed JSON response",
                provider=self.name,
                outcome="parsing_failure",
                request_url=hardcover_api_url(),
                exception_type=type(exc).__name__,
            ) from exc
        if not isinstance(payload, dict):
            raise ProviderSearchError(
                "Hardcover GraphQL malformed response",
                provider=self.name,
                outcome="parsing_failure",
                request_url=hardcover_api_url(),
                exception_type="MalformedResponse",
            )
        if payload.get("errors"):
            raise ProviderSearchError(
                "Hardcover GraphQL errors",
                provider=self.name,
                outcome="provider_failure",
                request_url=hardcover_api_url(),
                response_body=str(payload.get("errors"))[:1000],
                exception_type="GraphQLError",
            )
        data = payload.get("data")
        if not isinstance(data, dict):
            raise ProviderSearchError(
                "Hardcover GraphQL missing data",
                provider=self.name,
                outcome="parsing_failure",
                request_url=hardcover_api_url(),
                exception_type="MissingData",
            )
        return data

    async def _search_ids(self, client: httpx.AsyncClient, query: str, limit: int, headers: dict) -> list[int]:
        data = await self._graphql(client, SEARCH_QUERY, {"query": query, "limit": limit}, headers)
        return _ids_from_search(data.get("search") if isinstance(data.get("search"), dict) else {})

    async def _book_details(self, client: httpx.AsyncClient, ids: list[int], limit: int, headers: dict) -> list[dict]:
        data = await self._graphql(client, BOOK_DETAILS_QUERY, {"ids": ids, "limit": limit}, headers)
        books = data.get("books")
        if not isinstance(books, list):
            raise ProviderSearchError(
                "Hardcover GraphQL books response missing",
                provider=self.name,
                outcome="parsing_failure",
                request_url=hardcover_api_url(),
                exception_type="MissingBooks",
            )
        order = {book_id: index for index, book_id in enumerate(ids)}
        return sorted(
            [book for book in books if isinstance(book, dict)],
            key=lambda book: order.get(int(book.get("id") or 0), len(order)),
        )


def search_candidates(query: str) -> list[dict]:
    async def run() -> list[dict]:
        return await HardcoverProvider().search(query)

    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(run())
    raise RuntimeError("search_candidates cannot be called from an active event loop")
