import asyncio
import time

from backend.services.metadata_aggregation import (
    LocalCatalogSource,
    MetadataAggregationService,
)


class FakeSource:
    timeout_seconds = 0.25

    def __init__(self, name: str, results: list[dict], delay: float = 0.0) -> None:
        self.name = name
        self.results = results
        self.delay = delay

    async def search(self, _query: str) -> list[dict]:
        if self.delay:
            await asyncio.sleep(self.delay)
        return self.results


class FailingSource:
    name = "open_library"
    timeout_seconds = 0.25

    async def search(self, _query: str) -> list[dict]:
        raise TimeoutError("provider unavailable")


def test_aggregation_runs_sources_concurrently_and_collects_partial_successes():
    service = MetadataAggregationService(
        [
            FakeSource(
                "scraper",
                [{"title": "Dune", "authors": ["Frank Herbert"], "isbn_uid": "9780441172719"}],
                delay=0.1,
            ),
            FakeSource(
                "web_search",
                [{"title": "Kindred", "authors": ["Octavia E. Butler"], "isbn_uid": "9780807083697"}],
                delay=0.1,
            ),
            FailingSource(),
        ]
    )

    started = time.perf_counter()
    result = asyncio.run(service.aggregate("Dune"))
    elapsed = time.perf_counter() - started

    assert elapsed < 0.18
    assert [item["title"] for item in result.results] == ["Dune", "Kindred"]
    assert {outcome.source: outcome.success for outcome in result.outcomes} == {
        "scraper": True,
        "web_search": True,
        "open_library": False,
    }


def test_aggregation_dedupes_by_isbn_and_merges_sparse_fields():
    service = MetadataAggregationService(
        [
            FakeSource(
                "open_library",
                [
                    {
                        "title": "Kindred",
                        "authors": ["Octavia E. Butler"],
                        "isbn_uid": "9780807083697",
                        "total_pages": 264,
                    }
                ],
            ),
            FakeSource(
                "scraper",
                [
                    {
                        "title": "Kindred",
                        "authors": ["Octavia E. Butler"],
                        "isbn_uid": "9780807083697",
                        "description": "A modern classic.",
                    }
                ],
            ),
        ]
    )

    result = asyncio.run(service.aggregate("Kindred Octavia Butler"))

    assert len(result.results) == 1
    assert result.results[0]["description"] == "A modern classic."
    assert result.results[0]["total_pages"] == 264


def test_aggregation_dedupes_by_title_author_fallback():
    service = MetadataAggregationService(
        [
            FakeSource("web_search", [{"title": "Dune", "authors": ["Frank Herbert"]}]),
            FakeSource(
                "librarything",
                [{"title": "Dune", "authors": ["Frank Herbert"], "related_isbns": ["0441172717"]}],
            ),
        ]
    )

    result = asyncio.run(service.aggregate("Dune Frank Herbert"))

    assert len(result.results) == 1
    assert result.results[0]["related_isbns"] == ["0441172717"]


def test_aggregation_ranks_local_and_high_confidence_results_first():
    service = MetadataAggregationService(
        [
            LocalCatalogSource(
                [
                    {
                        "title": "Dune",
                        "authors": ["Frank Herbert"],
                        "isbn_uid": "0441172717",
                        "already_in_library": True,
                    }
                ]
            ),
            FakeSource(
                "scraper",
                [
                    {
                        "title": "Dune Messiah",
                        "authors": ["Frank Herbert"],
                        "isbn_uid": "9780593098233",
                        "confidence_score": 0.9,
                    }
                ],
            ),
        ],
        limit=2,
    )

    result = asyncio.run(service.aggregate("Dune Messiah Frank Herbert"))

    assert [item["title"] for item in result.results] == ["Dune Messiah", "Dune"]


def test_aggregation_reports_all_providers_failed():
    service = MetadataAggregationService([FailingSource()])

    result = asyncio.run(service.aggregate("Dune"))

    assert result.results == []
    assert len(result.outcomes) == 1
    assert result.outcomes[0].success is False
    assert result.outcomes[0].outcome in {"timeout", "provider_failure"}
