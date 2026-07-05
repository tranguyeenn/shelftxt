"""Open Library candidate adapter used by the resolver."""


def search_candidates(query: str) -> list[dict]:
    from backend.services.book_search import _open_library_results

    return _open_library_results(query)
