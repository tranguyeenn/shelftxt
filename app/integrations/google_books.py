"""Google Books candidate adapter used by the resolver."""


def search_candidates(query: str) -> list[dict]:
    from backend.services.book_search import _google_books_results

    return _google_books_results(query)
