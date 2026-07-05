import time
import threading
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import patch

from backend.services.book_resolver import (
    BookCandidate,
    clear_resolver_cache,
    merge_canonical_candidate,
    resolve_book,
    select_canonical_candidate,
)


def _candidate(source: str, **values) -> BookCandidate:
    return BookCandidate(
        title=values.pop("title", "Dune"),
        authors=values.pop("authors", ("Frank Herbert",)),
        source=source,
        **values,
    )


def test_exact_isbn_always_wins_selection():
    exact = _candidate("google_books", isbn="9780441172719")
    richer_wrong = _candidate(
        "open_library",
        isbn="9780000000000",
        cover_url="cover",
        total_pages=500,
        description="description",
    )

    selected = select_canonical_candidate(
        [richer_wrong, exact],
        query="9780441172719",
        isbn="9780441172719",
    )

    assert selected is not None
    assert selected[0] is exact


def test_provider_metadata_merges_without_overwriting_primary_edition():
    open_library = _candidate(
        "open_library",
        isbn="9780441172719",
        edition_key="OL1M",
        cover_url="ol-cover",
        total_pages=412,
        subjects=("desert",),
    )
    google = _candidate(
        "google_books",
        isbn="9780000000000",
        edition_key="google-1",
        cover_url="google-cover",
        total_pages=500,
        description="A science-fiction classic.",
        genres=("science fiction",),
    )

    result = merge_canonical_candidate(open_library, [google])

    assert result.description == "A science-fiction classic."
    assert result.genres == ("science fiction",)
    assert result.isbn == "9780441172719"
    assert result.edition_key == "OL1M"
    assert result.cover_url == "ol-cover"
    assert result.total_pages == 412


def test_librarything_enriches_but_does_not_affect_core_selection():
    provider_result = {
        "title": "Dune",
        "authors": ["Frank Herbert"],
        "isbn_uid": "9780441172719",
        "metadata_source": "open_library",
        "cover_url": "cover",
    }
    with (
        patch(
            "backend.services.book_resolver._provider_fetchers",
            return_value=(lambda _query: [provider_result], lambda _query: []),
        ),
        patch(
            "backend.services.book_resolver.librarything.fetch_related_isbns",
            return_value=["0441172717"],
        ),
    ):
        clear_resolver_cache()
        result = resolve_book("9780441172719")

    assert result is not None
    assert result.source == "open_library"
    assert result.isbn == "9780441172719"
    assert result.related_isbns == ("0441172717",)


def test_provider_timeout_is_bounded_and_fails_open():
    def slow_provider(_query):
        time.sleep(0.2)
        return []

    google_result = {
        "title": "Dune",
        "authors": ["Frank Herbert"],
        "isbn_uid": "9780441172719",
        "metadata_source": "google_books",
    }
    with (
        patch("backend.services.book_resolver.PROVIDER_TIMEOUT_SECONDS", 0.02),
        patch(
            "backend.services.book_resolver._provider_fetchers",
            return_value=(slow_provider, lambda _query: [google_result]),
        ),
        patch("backend.services.book_resolver.librarything.fetch_related_isbns", return_value=[]),
    ):
        clear_resolver_cache()
        started = time.perf_counter()
        result = resolve_book("9780441172719")
        elapsed = time.perf_counter() - started

    assert result is not None
    assert result.source == "google_books"
    assert elapsed < 0.15


def test_same_input_is_cached_and_deterministic():
    calls = {"open_library": 0, "google_books": 0}
    result = {
        "title": "Kindred",
        "authors": ["Octavia E. Butler"],
        "isbn_uid": "9780807083697",
        "metadata_source": "open_library",
    }

    def open_library(_query):
        calls["open_library"] += 1
        return [result]

    def google_books(_query):
        calls["google_books"] += 1
        return []

    with (
        patch(
            "backend.services.book_resolver._provider_fetchers",
            return_value=(open_library, google_books),
        ),
        patch("backend.services.book_resolver.librarything.fetch_related_isbns", return_value=[]),
    ):
        clear_resolver_cache()
        first = resolve_book("9780807083697")
        second = resolve_book("9780807083697")

    assert first == second
    assert calls == {"open_library": 1, "google_books": 1}


def test_concurrent_identical_requests_are_deduplicated():
    calls = 0
    calls_lock = threading.Lock()
    provider_result = {
        "title": "Dune",
        "authors": ["Frank Herbert"],
        "isbn_uid": "9780441172719",
        "metadata_source": "open_library",
    }

    def open_library(_query):
        nonlocal calls
        with calls_lock:
            calls += 1
        time.sleep(0.05)
        return [provider_result]

    with (
        patch(
            "backend.services.book_resolver._provider_fetchers",
            return_value=(open_library, lambda _query: []),
        ),
        patch("backend.services.book_resolver.librarything.fetch_related_isbns", return_value=[]),
    ):
        clear_resolver_cache()
        with ThreadPoolExecutor(max_workers=2) as executor:
            first = executor.submit(resolve_book, "9780441172719")
            second = executor.submit(resolve_book, "9780441172719")
            results = [first.result(), second.result()]

    assert results[0] == results[1]
    assert calls == 1


def test_no_good_match_returns_none_safely():
    unrelated = {
        "title": "Completely Different",
        "authors": ["Someone Else"],
        "metadata_source": "open_library",
    }
    with (
        patch(
            "backend.services.book_resolver._provider_fetchers",
            return_value=(lambda _query: [unrelated], lambda _query: []),
        ),
    ):
        clear_resolver_cache()
        result = resolve_book("Small Things Like These", "Claire Keegan")

    assert result is None
