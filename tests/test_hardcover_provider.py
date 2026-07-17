import asyncio
from pathlib import Path

import pytest

from app.integrations.hardcover import HardcoverProvider, clear_hardcover_cache
from backend.services.metadata_aggregation import MetadataAggregationService
from backend.services.metadata_providers import ProviderSearchError
from backend.services.recommendation_discovery import _prepare_external_result


class _Source:
    timeout_seconds = 0.1

    def __init__(self, name, results=None, error=None, calls=None):
        self.name = name
        self._results = results or []
        self._error = error
        self._calls = calls if calls is not None else []

    async def search(self, query):
        self._calls.append((self.name, query))
        if self._error:
            raise self._error
        return self._results


def _book(id_=1, *, title="Queer Hearts", author="A. Writer", year=2022):
    return {
        "id": id_,
        "title": title,
        "slug": title.casefold().replace(" ", "-"),
        "description": "A specific recommendation candidate.",
        "cached_tags": {"Genre": [{"tag": "young adult"}, {"tag": "romance"}], "Mood": [{"tag": "hopeful"}]},
        "cached_contributors": [{"name": author}],
        "rating": 4.2,
        "ratings_count": 120,
        "users_count": 400,
        "activities_count": 25,
        "release_date": f"{year}-01-01",
        "pages": 320,
        "image": {"url": "https://img.example/book.jpg"},
        "contributions": [{"author": {"id": 1, "name": author}, "contribution": "Author"}],
        "book_series": [],
        "editions": [
            {
                "id": 11,
                "isbn_13": "9781234567890",
                "release_year": year,
                "language": {"code3": "eng", "code2": "en", "language": "English"},
                "publisher": {"name": "Publisher"},
            }
        ],
    }


def test_hardcover_normalized_books_enter_provider_pipeline(monkeypatch):
    clear_hardcover_cache()
    monkeypatch.setenv("HARDCOVER_ENABLED", "true")
    monkeypatch.setenv("HARDCOVER_API_TOKEN", "test-token")
    calls = []

    async def fake_graphql(_self, _client, query, variables, _headers):
        calls.append(query)
        if "HardcoverSearch" in query:
            return {"search": {"ids": [1]}}
        return {"books": [_book()]}

    monkeypatch.setattr(HardcoverProvider, "_graphql", fake_graphql)

    result = asyncio.run(HardcoverProvider().search("queer teen graphic romance"))

    assert len(result) == 1
    assert result[0]["metadata_source"] == "hardcover"
    assert result[0]["title"] == "Queer Hearts"
    assert result[0]["authors"] == ["A. Writer"]
    assert result[0]["isbn_uid"] == "9781234567890"
    assert result[0]["publication_year"] == 2022
    assert result[0]["work_publication_year"] == 2022
    assert result[0]["work_publication_date"] == "2022-01-01"
    assert result[0]["edition_release_years"] == [2022]
    assert result[0]["publication_year_source"] == "work"
    assert result[0]["provider_rating_count"] == 120
    assert len(calls) == 2


def test_hardcover_graphql_errors_are_handled(monkeypatch):
    clear_hardcover_cache()
    monkeypatch.setenv("HARDCOVER_ENABLED", "true")
    monkeypatch.setenv("HARDCOVER_API_TOKEN", "test-token")

    async def fake_graphql(_self, _client, _query, _variables, _headers):
        raise ProviderSearchError(
            "GraphQL error",
            provider="hardcover",
            outcome="provider_failure",
            exception_type="GraphQLError",
        )

    monkeypatch.setattr(HardcoverProvider, "_graphql", fake_graphql)

    with pytest.raises(ProviderSearchError) as exc:
        asyncio.run(HardcoverProvider().search("query"))

    assert exc.value.provider == "hardcover"
    assert exc.value.exception_type == "GraphQLError"


def test_hardcover_malformed_response_is_handled(monkeypatch):
    clear_hardcover_cache()
    monkeypatch.setenv("HARDCOVER_ENABLED", "true")
    monkeypatch.setenv("HARDCOVER_API_TOKEN", "test-token")

    async def fake_graphql(_self, _client, query, _variables, _headers):
        if "HardcoverSearch" in query:
            return {"search": {"ids": [1]}}
        return {"not_books": []}

    monkeypatch.setattr(HardcoverProvider, "_graphql", fake_graphql)

    with pytest.raises(ProviderSearchError) as exc:
        asyncio.run(HardcoverProvider().search("query"))

    assert exc.value.exception_type == "MissingBooks"


def test_hardcover_cache_prevents_repeat_calls(monkeypatch):
    clear_hardcover_cache()
    monkeypatch.setenv("HARDCOVER_ENABLED", "true")
    monkeypatch.setenv("HARDCOVER_API_TOKEN", "test-token")
    calls = {"count": 0}

    async def fake_graphql(_self, _client, query, _variables, _headers):
        calls["count"] += 1
        if "HardcoverSearch" in query:
            return {"search": {"ids": [1]}}
        return {"books": [_book()]}

    monkeypatch.setattr(HardcoverProvider, "_graphql", fake_graphql)

    first = asyncio.run(HardcoverProvider().search("queer teen graphic romance"))
    second = asyncio.run(HardcoverProvider().search("queer teen graphic romance"))

    assert first[0]["title"] == second[0]["title"]
    assert second[0]["cache_hit"] is True
    assert calls["count"] == 2


def test_hardcover_primary_skips_open_library_when_enough_results():
    calls = []
    service = MetadataAggregationService(
            [
                _Source("local", calls=calls),
                _Source(
                    "hardcover",
                    [
                        {"title": "HC 1", "authors": ["A"], "genres": ["dystopian"]},
                        {"title": "HC 2", "authors": ["B"], "genres": ["dystopian"]},
                        {"title": "HC 3", "authors": ["C"], "genres": ["dystopian"]},
                    ],
                    calls=calls,
                ),
                _Source("open_library", [{"title": "Open Library", "authors": ["D"], "genres": ["dystopian"]}], calls=calls),
        ],
        limit=3,
    )

    result = asyncio.run(service.aggregate("YA survival dystopia"))

    assert [call[0] for call in calls] == ["local", "hardcover"]
    assert len(result.results) == 3
    assert all(outcome.source != "open_library" for outcome in result.outcomes)


def test_open_library_used_when_hardcover_fails():
    calls = []
    service = MetadataAggregationService(
        [
            _Source("local", calls=calls),
            _Source("hardcover", error=TimeoutError("timeout"), calls=calls),
            _Source("open_library", [{"title": "Open Library", "authors": ["D"], "genres": ["dystopian"]}], calls=calls),
        ],
        limit=3,
    )

    result = asyncio.run(service.aggregate("YA survival dystopia"))

    assert [call[0] for call in calls] == ["local", "hardcover", "open_library"]
    assert any(item["title"] == "Open Library" for item in result.results)
    assert any(outcome.source == "hardcover" and not outcome.success for outcome in result.outcomes)


def test_all_external_calls_are_bounded():
    service = MetadataAggregationService(
        [
            _Source("local"),
            _Source("hardcover", [{"title": f"HC {index}", "authors": [f"A{index}"], "genres": ["dystopian"]} for index in range(10)]),
            _Source("open_library", [{"title": "Open Library", "authors": ["D"], "genres": ["dystopian"]}]),
        ],
        limit=3,
    )

    result = asyncio.run(service.aggregate("bounded query"))

    assert len(result.results) == 3
    assert all(outcome.source != "open_library" for outcome in result.outcomes)


def test_recommendation_discovery_does_not_reference_google_books():
    checked = [
        Path("backend/services/recommendation_discovery.py"),
        Path("backend/services/book_search.py"),
        Path("backend/services/metadata_aggregation.py"),
        Path("app/integrations/hardcover.py"),
        Path("app/integrations/openlibrary.py"),
    ]

    text = "\n".join(path.read_text() for path in checked)

    assert "google" not in text.casefold()


def test_modern_cluster_candidates_receive_soft_publication_year_preference():
    result = _prepare_external_result(
        {
            "title": "Modern YA",
            "authors": ["A"],
            "genres": ["young adult", "dystopian"],
            "first_publish_year": 2021,
            "confidence_score": 0.7,
            "metadata_source": "hardcover",
            "discovery_cluster_id": "ya-dystopian-speculative",
        },
        [],
    )

    assert result["confidence_score"] == pytest.approx(0.74)
    assert result["modern_candidate_preference"] == "boosted"


def test_exact_series_continuation_is_not_age_penalized():
    result = _prepare_external_result(
        {
            "title": "Older Sequel",
            "authors": ["A"],
            "genres": ["young adult", "dystopian"],
            "first_publish_year": 2008,
            "confidence_score": 0.7,
            "metadata_source": "hardcover",
            "discovery_cluster_id": "ya-dystopian-speculative",
            "series_name": "Series",
        },
        [],
    )

    assert result["confidence_score"] == pytest.approx(0.7)
    assert "modern_candidate_preference" not in result


def test_literary_classics_are_exempt_from_modern_preference():
    result = _prepare_external_result(
        {
            "title": "Classic",
            "authors": ["A"],
            "genres": ["classic"],
            "first_publish_year": 1880,
            "confidence_score": 0.7,
            "metadata_source": "hardcover",
            "discovery_cluster_id": "literary-classics",
        },
        [],
    )

    assert result["confidence_score"] == pytest.approx(0.7)
    assert "modern_candidate_preference" not in result
