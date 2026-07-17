"""New York Times Books API integration for weekly bestseller discovery."""

from __future__ import annotations

from dataclasses import dataclass
import os
import re
import threading
import time
from typing import Any

import httpx

DEFAULT_API_URL = "https://api.nytimes.com/svc/books/v3"
DEFAULT_TIMEOUT_SECONDS = 3.0
DEFAULT_CACHE_SECONDS = 6 * 60 * 60

_cache_lock = threading.Lock()
_overview_cache: tuple[float, list[dict]] | None = None


@dataclass(frozen=True)
class ProviderStatus:
    enabled: bool
    available: bool
    cached: bool = False
    request_count: int = 0
    error: str | None = None

    def to_dict(self) -> dict:
        payload = {
            "enabled": self.enabled,
            "available": self.available,
            "cached": self.cached,
            "request_count": self.request_count,
        }
        if self.error:
            payload["error"] = self.error
        return payload


def nyt_books_enabled() -> bool:
    raw = str(os.getenv("NYT_BOOKS_ENABLED", "")).strip().casefold()
    if raw in {"0", "false", "no", "off"}:
        return False
    return bool(nyt_books_api_key())


def nyt_books_api_url() -> str:
    return (os.getenv("NYT_BOOKS_API_URL") or DEFAULT_API_URL).strip().rstrip("/") or DEFAULT_API_URL


def nyt_books_api_key() -> str | None:
    return (os.getenv("NYT_BOOKS_API_KEY") or "").strip() or None


def nyt_books_timeout_seconds() -> float:
    try:
        value = float(os.getenv("NYT_BOOKS_TIMEOUT_SECONDS", str(DEFAULT_TIMEOUT_SECONDS)))
    except (TypeError, ValueError):
        return DEFAULT_TIMEOUT_SECONDS
    return max(0.5, min(10.0, value))


def nyt_books_cache_seconds() -> int:
    try:
        value = int(os.getenv("NYT_BOOKS_CACHE_SECONDS", str(DEFAULT_CACHE_SECONDS)))
    except (TypeError, ValueError):
        return DEFAULT_CACHE_SECONDS
    return max(60, min(24 * 60 * 60, value))


def clear_nyt_books_cache() -> None:
    global _overview_cache
    with _cache_lock:
        _overview_cache = None


def nyt_broad_genre(list_name: object) -> str | None:
    normalized = re.sub(r"[^a-z0-9]+", " ", str(list_name or "").casefold()).strip()
    if not normalized:
        return None
    if "graphic" in normalized or "manga" in normalized:
        return "Graphic / Manga"
    if "young adult" in normalized or "children" in normalized or "middle grade" in normalized:
        return "Young Adult"
    if "romance" in normalized:
        return "Romance"
    if any(term in normalized for term in ("mystery", "thriller", "crime")):
        return "Mystery / Thriller"
    if any(term in normalized for term in ("fantasy", "science fiction", "sci fi")):
        return "Fantasy / Science Fiction"
    if "nonfiction" in normalized or "advice" in normalized or "how to" in normalized or "business" in normalized:
        return "Nonfiction"
    if "fiction" in normalized:
        return "Fiction"
    return None


def current_overview() -> tuple[list[dict], ProviderStatus]:
    global _overview_cache
    if not nyt_books_enabled():
        return [], ProviderStatus(enabled=False, available=False, error="not_configured")

    now = time.monotonic()
    ttl = nyt_books_cache_seconds()
    with _cache_lock:
        if _overview_cache and now - _overview_cache[0] < ttl:
            return [dict(item) for item in _overview_cache[1]], ProviderStatus(
                enabled=True,
                available=True,
                cached=True,
                request_count=0,
            )

    key = nyt_books_api_key()
    if not key:
        return [], ProviderStatus(enabled=False, available=False, error="not_configured")

    url = f"{nyt_books_api_url()}/lists/overview.json"
    try:
        with httpx.Client(timeout=nyt_books_timeout_seconds(), follow_redirects=True) as client:
            response = client.get(url, params={"api-key": key})
            response.raise_for_status()
            payload = response.json()
    except Exception as exc:
        return [], ProviderStatus(enabled=True, available=False, request_count=1, error=type(exc).__name__)

    normalized = _normalize_overview(payload)
    with _cache_lock:
        _overview_cache = (time.monotonic(), [dict(item) for item in normalized])
    return normalized, ProviderStatus(enabled=True, available=True, cached=False, request_count=1)


def _normalize_overview(payload: Any) -> list[dict]:
    if not isinstance(payload, dict):
        return []
    results = payload.get("results")
    if not isinstance(results, dict):
        return []
    lists = results.get("lists")
    if not isinstance(lists, list):
        return []
    published_date = _clean_text(results.get("published_date"))
    bestsellers_date = _clean_text(results.get("bestsellers_date"))
    items: list[dict] = []
    for list_payload in lists:
        if not isinstance(list_payload, dict):
            continue
        list_name = _clean_text(list_payload.get("list_name") or list_payload.get("display_name"))
        display_name = _clean_text(list_payload.get("display_name") or list_name)
        list_name_encoded = _clean_text(list_payload.get("list_name_encoded"))
        broad_genre = nyt_broad_genre(list_name or display_name)
        books = list_payload.get("books")
        if not isinstance(books, list):
            continue
        for book in books:
            if not isinstance(book, dict):
                continue
            normalized = _normalize_book(
                book,
                list_name=list_name,
                display_name=display_name,
                list_name_encoded=list_name_encoded,
                broad_genre=broad_genre,
                published_date=published_date,
                bestsellers_date=bestsellers_date,
            )
            if normalized:
                items.append(normalized)
    return items


def _normalize_book(
    book: dict,
    *,
    list_name: str | None,
    display_name: str | None,
    list_name_encoded: str | None,
    broad_genre: str | None,
    published_date: str | None,
    bestsellers_date: str | None,
) -> dict | None:
    title = _clean_text(book.get("title"))
    author = _clean_text(book.get("author"))
    if not title or not author:
        return None
    isbn13 = _normalize_isbn(book.get("primary_isbn13"))
    isbn10 = _normalize_isbn(book.get("primary_isbn10"))
    source_url = _clean_text(book.get("amazon_product_url")) or _buy_link(book)
    external_id = f"nyt:{isbn13 or isbn10 or _slug(title)}:{_slug(author)}"
    return {
        "external_id": external_id,
        "work_key": external_id,
        "title": title.title() if title.isupper() else title,
        "authors": [author],
        "author": author,
        "contributor": _clean_text(book.get("contributor")),
        "publisher": _clean_text(book.get("publisher")),
        "description": _clean_text(book.get("description")),
        "isbn_uid": isbn13 or isbn10,
        "primary_isbn13": isbn13,
        "primary_isbn10": isbn10,
        "related_isbns": [value for value in (isbn13, isbn10) if value],
        "cover_url": _clean_text(book.get("book_image")),
        "source_url": source_url,
        "source_urls": [source_url] if source_url else [],
        "metadata_source": "nyt",
        "source": "nyt",
        "rank": _positive_int(book.get("rank")),
        "rank_last_week": _positive_int(book.get("rank_last_week")),
        "weeks_on_list": _positive_int(book.get("weeks_on_list")),
        "list_name": list_name,
        "display_name": display_name or list_name,
        "list_name_encoded": list_name_encoded,
        "published_date": published_date,
        "bestsellers_date": bestsellers_date,
        "genres": [broad_genre] if broad_genre else [],
        "subjects": [display_name or list_name] if (display_name or list_name) else [],
        "broad_genre": broad_genre,
    }


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


def _slug(value: object) -> str:
    return re.sub(r"[^a-z0-9]+", "-", str(value or "").casefold()).strip("-")


def _buy_link(book: dict) -> str | None:
    links = book.get("buy_links")
    if not isinstance(links, list):
        return None
    for link in links:
        if isinstance(link, dict) and _clean_text(link.get("url")):
            return _clean_text(link.get("url"))
    return None
