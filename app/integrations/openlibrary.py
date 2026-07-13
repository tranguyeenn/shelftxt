"""Open Library metadata provider."""

from __future__ import annotations

import asyncio

from backend.services.metadata_providers import MetadataProvider


class OpenLibraryProvider(MetadataProvider):
    name = "open_library"
    timeout_seconds = 5.0
    max_retries = 1

    async def search(self, query: str) -> list[dict]:
        from backend.services.book_search import _open_library_results

        return await asyncio.to_thread(_open_library_results, query)


def search_candidates(query: str) -> list[dict]:
    from backend.services.book_search import _open_library_results

    return _open_library_results(query)
