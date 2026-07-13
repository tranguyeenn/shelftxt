import asyncio
from uuid import uuid4
from unittest.mock import AsyncMock, patch

import httpx
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.integrations.openlibrary import OpenLibraryProvider
from backend.db.database import Base
from backend.db.models import Book, Profile
from backend.services.book_search import search_books
from backend.services.book_search import load_open_library_work_editions
from backend.services import book_search as book_search_module
from backend.services.book_scraping.models import ScrapeDiagnostic, ScrapeResult, ScrapedBookMetadata
from backend.services.metadata_discovery import (
    TrustedUrlDiscoveryProvider,
    discover_books,
    likely_manual_duplicates,
    normalize_manual_metadata,
)
from backend.services.metadata_providers import MetadataProvider, search_provider


def _session():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine)()


def test_search_normalizes_and_merges_provider_results():
    db = _session()
    user_id = uuid4()
    db.add(Profile(id=user_id, email="reader@example.com", username="reader"))
    db.commit()

    open_library = {
        "title": "Kindred",
        "authors": ["Octavia E. Butler"],
        "isbn_uid": "9780807083697",
        "description": None,
        "cover_url": None,
        "total_pages": 264,
        "subjects": ["time travel"],
        "genres": ["science fiction"],
        "first_publish_year": 1979,
        "metadata_source": "open_library",
        "work_key": "/works/OL123W",
        "edition_key": "OL123M",
        "related_isbns": [],
        "already_in_library": False,
    }
    open_library["source_urls"] = ["https://www.penguinrandomhouse.com/books/123/kindred/"]
    scraped = ScrapeResult(
        status="success",
        metadata=ScrapedBookMetadata(
            title="Kindred",
            authors=["Octavia E. Butler"],
            isbn_uid="9780807083697",
            description="A modern classic.",
            source_url="https://www.penguinrandomhouse.com/books/123/kindred/",
            source_domain="penguinrandomhouse.com",
            confidence_score=0.95,
        ),
        diagnostics=ScrapeDiagnostic(
            domain="penguinrandomhouse.com",
            outcome="success",
            parser_used="jsonld",
            fields_extracted=["title", "authors", "isbn_uid", "description"],
        ),
    )
    with (
        patch("backend.services.book_search._open_library_results", return_value=[open_library]),
        patch("backend.services.book_search.scrape_book_metadata", new=AsyncMock(return_value=scraped)),
        patch("app.integrations.librarything.fetch_related_isbns", return_value=["0807083690"]),
    ):
        response = search_books(db, user_id, "Kindred")

    results = response["results"]
    assert response["status"] == "ok"
    assert len(results) == 1
    assert results[0]["metadata_source"] == "scraped"
    assert results[0]["description"] == "A modern classic."
    assert results[0]["related_isbns"] == ["0807083690"]
    assert set(results[0]) >= {
        "title", "authors", "isbn_uid", "description", "cover_url", "total_pages",
        "subjects", "genres", "first_publish_year", "metadata_source", "work_key",
        "edition_key", "publisher", "publish_date", "language", "related_isbns", "already_in_library",
        "confidence_score",
    }


def test_search_uses_open_library_without_scraper_urls():
    db = _session()
    user_id = uuid4()
    db.add(Profile(id=user_id, email="reader@example.com", username="reader"))
    db.commit()

    open_library = {
        "title": "Kindred",
        "authors": ["Octavia E. Butler"],
        "isbn_uid": "9780807083697",
        "description": "A modern classic.",
        "metadata_source": "open_library",
    }
    with (
        patch("backend.services.book_search._open_library_results", return_value=[open_library]),
        patch("app.integrations.librarything.fetch_related_isbns", return_value=["0807083690"]),
    ):
        response = search_books(db, user_id, "Kindred")

    results = response["results"]
    assert response["status"] == "ok"
    assert len(results) == 1
    assert results[0]["metadata_source"] == "open_library"
    assert results[0]["description"] == "A modern classic."


def test_search_marks_related_isbn_duplicate():
    db = _session()
    user_id = uuid4()
    db.add(Profile(id=user_id, email="reader@example.com", username="reader"))
    db.add(
        Book(
            user_id=user_id,
            title="Dune",
            authors="Frank Herbert",
            isbn_uid="0441172717",
            book_metadata={"librarything": {"related_isbns": ["9780441172719"]}},
        )
    )
    db.commit()
    candidate = {
        "title": "Dune",
        "authors": ["Frank Herbert"],
        "isbn_uid": "9780441172719",
        "description": None,
        "cover_url": None,
        "total_pages": 412,
        "subjects": [],
        "genres": [],
        "first_publish_year": 1965,
        "metadata_source": "open_library",
        "work_key": None,
        "edition_key": None,
        "related_isbns": [],
        "already_in_library": False,
    }
    with (
        patch("backend.services.book_search._open_library_results", return_value=[candidate]),
        patch("app.integrations.librarything.fetch_related_isbns", return_value=["0441172717"]),
    ):
        response = search_books(db, user_id, "Dune")

    results = response["results"]
    assert results[0]["already_in_library"] is True


def _open_library_response(status_code: int, payload: dict) -> httpx.Response:
    return httpx.Response(
        status_code,
        json=payload,
        request=httpx.Request("GET", "https://openlibrary.org/search.json?q=Dune"),
    )


def test_open_library_200_with_results():
    payload = {
        "docs": [
            {
                "title": "Dune",
                "author_name": ["Frank Herbert"],
                "key": "/works/OL893415W",
                "first_publish_year": 1965,
            }
        ]
    }

    with patch("backend.services.book_search.httpx.get", return_value=_open_library_response(200, payload)) as get:
        result = asyncio.run(search_provider(OpenLibraryProvider(), "Dune"))

    assert result.diagnostic.outcome == "success"
    assert result.results[0]["title"] == "Dune"
    assert result.results[0]["metadata_source"] == "open_library"
    assert result.results[0]["editions_loaded"] is False
    assert not any("/editions.json" in str(call.args[0]) for call in get.call_args_list)


def test_open_library_search_does_not_fetch_work_editions():
    payload = {
        "docs": [
            {
                "title": "Convenience Store Woman",
                "author_name": ["Sayaka Murata"],
                "key": "/works/OL19744024W",
                "first_publish_year": 2016,
            },
            {
                "title": "Convenience Store Woman",
                "author_name": ["Sayaka Murata"],
                "key": "/works/OL19744024W",
                "first_publish_year": 2016,
            },
        ]
    }

    with patch("backend.services.book_search.httpx.get", return_value=_open_library_response(200, payload)) as get:
        result = asyncio.run(search_provider(OpenLibraryProvider(), "convenience store woman"))

    assert result.diagnostic.outcome == "success"
    assert len(result.results) == 1
    assert result.results[0]["work_key"] == "/works/OL19744024W"
    assert result.results[0]["editions_loaded"] is False
    urls = [str(call.args[0]) for call in get.call_args_list]
    assert urls == ["https://openlibrary.org/search.json"]


def test_edition_timeout_does_not_retry_work_search():
    search_payload = {
        "docs": [
            {
                "title": "Convenience Store Woman",
                "author_name": ["Sayaka Murata"],
                "key": "/works/OL19744024W",
            }
        ]
    }

    def fake_get(url, **kwargs):
        if str(url).endswith("/search.json"):
            return _open_library_response(200, search_payload)
        raise httpx.ReadTimeout("edition timeout", request=httpx.Request("GET", str(url)))

    with patch("backend.services.book_search.httpx.get", side_effect=fake_get) as get:
        result = asyncio.run(search_provider(OpenLibraryProvider(), "convenience store woman"))

    assert result.diagnostic.outcome == "success"
    assert len(result.results) == 1
    assert sum(1 for call in get.call_args_list if str(call.args[0]).endswith("/search.json")) == 1
    assert not any("/editions.json" in str(call.args[0]) for call in get.call_args_list)


def test_lazy_edition_lookup_fetches_one_work_with_default_limit_20():
    book_search_module._edition_cache.clear()
    book_search_module._edition_inflight.clear()
    response = httpx.Response(
        200,
        json={
            "entries": [
                {
                    "title": "Convenience Store Woman",
                    "key": "/books/OL1M",
                    "isbn_13": ["9780802150140"],
                    "number_of_pages": 176,
                    "covers": [123],
                    "publishers": ["Grove"],
                    "publish_date": "2018",
                    "languages": [{"key": "/languages/eng"}],
                }
            ]
        },
        request=httpx.Request(
            "GET",
            "https://openlibrary.org/works/OL19744024W/editions.json?limit=20",
        ),
    )

    with patch("backend.services.book_search.httpx.get", return_value=response) as get:
        result = load_open_library_work_editions(
            "OL19744024W",
            query="convenience store woman",
            title="Convenience Store Woman",
            authors=["Sayaka Murata"],
        )

    assert result["status"] == "ok"
    assert result["editions_loaded"] is True
    assert result["edition_count"] == 1
    assert result["primary_edition"]["isbn_uid"] == "9780802150140"
    assert get.call_count == 1
    assert get.call_args.kwargs["params"] == {"limit": 20}


def test_lazy_edition_lookup_uses_cache_for_duplicate_work_ids():
    book_search_module._edition_cache.clear()
    book_search_module._edition_inflight.clear()
    response = httpx.Response(
        200,
        json={"entries": [{"title": "Dune", "key": "/books/OL1M", "isbn_13": ["9780441172719"]}]},
        request=httpx.Request("GET", "https://openlibrary.org/works/OL893415W/editions.json?limit=20"),
    )

    with patch("backend.services.book_search.httpx.get", return_value=response) as get:
        first = load_open_library_work_editions("OL893415W", query="Dune", title="Dune", authors=["Frank Herbert"])
        second = load_open_library_work_editions("OL893415W", query="Dune", title="Dune", authors=["Frank Herbert"])

    assert first["edition_count"] == 1
    assert second["edition_count"] == 1
    assert get.call_count == 1


def test_extended_discovery_is_explicit_and_returns_grouped_results():
    db = _session()
    user_id = uuid4()
    db.add(Profile(id=user_id, email="reader@example.com", username="reader"))
    db.commit()
    candidate = {
        "title": "Small Rain",
        "authors": ["Garth Greenwell"],
        "metadata_source": "open_library",
        "work_key": "/works/OL1W",
    }

    with patch("backend.services.metadata_discovery._open_library_results", return_value=[candidate]) as extended:
        response = discover_books(db, user_id, "Small Rain")

    assert response["status"] == "ok"
    assert response["results"][0]["canonical_title"] == "Small Rain"
    assert extended.call_count == 1


def test_trusted_url_discovery_classifies_parse_failure():
    provider = TrustedUrlDiscoveryProvider()
    result = ScrapeResult(
        status="empty",
        metadata=None,
        diagnostics=ScrapeDiagnostic(
            domain="bookshop.org",
            outcome="parsing_failure",
            elapsed_ms=1.2,
            http_status=200,
            parser_used="jsonld",
        ),
    )

    with patch("backend.services.metadata_discovery.scrape_book_metadata", new=AsyncMock(return_value=result)):
        records, diagnostic = asyncio.run(provider.search("https://bookshop.org/p/books/example", limit=5))

    assert records == []
    assert diagnostic.outcome == "parse_failure"
    assert diagnostic.request_attempted is True
    assert diagnostic.parser_version == "jsonld"


def test_trusted_url_discovery_blocks_unapproved_domains():
    provider = TrustedUrlDiscoveryProvider()

    records, diagnostic = asyncio.run(provider.search("https://amazon.com/books/example", limit=5))

    assert records == []
    assert diagnostic.outcome == "blocked"
    assert diagnostic.request_attempted is False


def test_manual_metadata_normalization_uses_manual_source_and_ignores_invalid_isbn():
    metadata = normalize_manual_metadata(
        {
            "title": "Có hạnh phúc",
            "authors": ["Hari Won"],
            "isbn_13": "9780000000000",
            "publisher": "Manual Publisher",
            "publication_date": "2014-01-01",
            "page_count": 220,
            "language": "vi",
            "edition_type": "original",
        }
    )

    assert metadata["metadata_source"] == "manual"
    assert metadata["title"] == "Có hạnh phúc"
    assert metadata["isbn_uid"] is None
    assert metadata["publisher"] == "Manual Publisher"
    assert metadata["total_pages"] == 220


def test_manual_duplicate_detection_uses_valid_isbn():
    db = _session()
    user_id = uuid4()
    db.add(Profile(id=user_id, email="reader@example.com", username="reader"))
    db.add(Book(user_id=user_id, title="Dune", authors="Frank Herbert", isbn_uid="9780441172719"))
    db.commit()

    duplicates = likely_manual_duplicates(
        db,
        user_id,
        {"title": "Dune", "authors": ["Frank Herbert"], "isbn_13": "978-0-441-17271-9"},
    )

    assert duplicates == [{"id": "9780441172719", "title": "Dune", "author": "Frank Herbert", "reason": "isbn"}]


def test_open_library_403_records_http_failure_diagnostics():
    with patch(
        "backend.services.book_search.httpx.get",
        return_value=_open_library_response(403, {"error": {"message": "forbidden"}}),
    ):
        result = asyncio.run(search_provider(OpenLibraryProvider(), "Dune"))

    assert result.results == []
    assert result.diagnostic.outcome == "http_failure"
    assert result.diagnostic.http_status == 403
    assert result.diagnostic.request_url is not None
    assert "forbidden" in (result.diagnostic.response_body or "")
    assert result.diagnostic.exception_type == "HTTPStatusError"


def test_open_library_429_records_http_failure_diagnostics():
    with patch(
        "backend.services.book_search.httpx.get",
        return_value=_open_library_response(429, {"error": {"message": "rate limited"}}),
    ):
        result = asyncio.run(search_provider(OpenLibraryProvider(), "Dune"))

    assert result.results == []
    assert result.diagnostic.outcome == "http_failure"
    assert result.diagnostic.http_status == 429
    assert "rate limited" in (result.diagnostic.response_body or "")


class SlowProvider(MetadataProvider):
    name = "slow"
    timeout_seconds = 0.01
    max_retries = 0

    async def search(self, _query: str) -> list[dict]:
        await asyncio.sleep(0.1)
        return [{"title": "Late"}]


def test_provider_timeout_records_timeout_diagnostics():
    result = asyncio.run(search_provider(SlowProvider(), "Dune"))

    assert result.results == []
    assert result.diagnostic.outcome == "timeout"
    assert result.diagnostic.exception_type == "TimeoutError"


def test_one_provider_fails_while_another_succeeds():
    db = _session()
    user_id = uuid4()
    db.add(Profile(id=user_id, email="reader@example.com", username="reader"))
    db.commit()

    with (
        patch("backend.services.book_search._open_library_results", side_effect=TimeoutError("down")),
        patch("app.integrations.librarything._token", return_value="token"),
        patch(
            "app.integrations.librarything.fetch_work_by_title",
            return_value={"title": "Dune", "related_isbns": ["9780441172719"]},
        ),
        patch("app.integrations.librarything.fetch_related_isbns", return_value=[]),
    ):
        response = search_books(db, user_id, "Dune", include_diagnostics=True)

    assert response["status"] == "degraded"
    assert response["results"][0]["title"] == "Dune"
    diagnostics = {item["source"]: item for item in response["diagnostics"]}
    assert diagnostics["open_library"]["success"] is False
    assert diagnostics["librarything"]["success"] is True
    assert "google_books" not in diagnostics


def test_all_external_providers_fail_returns_degraded_state():
    db = _session()
    user_id = uuid4()
    db.add(Profile(id=user_id, email="reader@example.com", username="reader"))
    db.commit()

    with (
        patch("backend.services.book_search._open_library_results", side_effect=TimeoutError("down")),
        patch("app.integrations.librarything._token", return_value="token"),
        patch("app.integrations.librarything.fetch_related_isbns", side_effect=TimeoutError("down")),
        patch("app.integrations.librarything.fetch_work_by_title", side_effect=TimeoutError("down")),
    ):
        response = search_books(db, user_id, "Dune", include_diagnostics=True)

    assert response["status"] == "degraded"
    assert response["results"] == []
    assert response["message"] == "All metadata providers failed. Search results may be incomplete."
    failed_sources = {
        item["source"]
        for item in response["diagnostics"]
        if item["source"] != "local" and not item["success"]
    }
    assert {"open_library", "librarything"}.issubset(failed_sources)
    assert "google_books" not in {item["source"] for item in response["diagnostics"]}
