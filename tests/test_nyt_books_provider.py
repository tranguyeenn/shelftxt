from app.integrations import nyt_books


def _overview_payload():
    return {
        "status": "OK",
        "results": {
            "bestsellers_date": "2026-07-04",
            "published_date": "2026-07-12",
            "lists": [
                {
                    "list_name": "Hardcover Fiction",
                    "display_name": "Hardcover Fiction",
                    "list_name_encoded": "hardcover-fiction",
                    "books": [
                        {
                            "title": "THE FICTION BOOK",
                            "author": "A Writer",
                            "contributor": "by A Writer",
                            "publisher": "Test Publisher",
                            "description": "A novel.",
                            "primary_isbn13": "9781234567890",
                            "primary_isbn10": "123456789X",
                            "rank": 1,
                            "rank_last_week": 2,
                            "weeks_on_list": 8,
                            "book_image": "https://img.example/book.jpg",
                            "amazon_product_url": "https://example.com/book",
                        }
                    ],
                }
            ],
        },
    }


def test_nyt_overview_normalization_preserves_official_fields():
    items = nyt_books._normalize_overview(_overview_payload())

    assert len(items) == 1
    item = items[0]
    assert item["title"] == "The Fiction Book"
    assert item["authors"] == ["A Writer"]
    assert item["publisher"] == "Test Publisher"
    assert item["primary_isbn13"] == "9781234567890"
    assert item["primary_isbn10"] == "123456789X"
    assert item["rank"] == 1
    assert item["rank_last_week"] == 2
    assert item["weeks_on_list"] == 8
    assert item["list_name"] == "Hardcover Fiction"
    assert item["list_name_encoded"] == "hardcover-fiction"
    assert item["published_date"] == "2026-07-12"
    assert item["bestsellers_date"] == "2026-07-04"
    assert item["cover_url"] == "https://img.example/book.jpg"
    assert item["source_url"] == "https://example.com/book"
    assert item["source"] == "nyt"
    assert item["broad_genre"] == "Fiction"


def test_nyt_list_names_map_to_broad_genres_without_duplicate_list_granularity():
    assert nyt_books.nyt_broad_genre("Combined Print and E-Book Fiction") == "Fiction"
    assert nyt_books.nyt_broad_genre("Hardcover Fiction") == "Fiction"
    assert nyt_books.nyt_broad_genre("Young Adult Hardcover") == "Young Adult"
    assert nyt_books.nyt_broad_genre("Advice How-To and Miscellaneous") == "Nonfiction"
    assert nyt_books.nyt_broad_genre("Graphic Books and Manga") == "Graphic / Manga"


def test_nyt_disabled_without_backend_key(monkeypatch):
    monkeypatch.delenv("NYT_BOOKS_API_KEY", raising=False)
    monkeypatch.setenv("NYT_BOOKS_ENABLED", "true")
    nyt_books.clear_nyt_books_cache()

    items, status = nyt_books.current_overview()

    assert items == []
    assert status.enabled is False
    assert status.available is False
    assert status.error == "not_configured"


def test_nyt_overview_cache_prevents_repeated_http_calls(monkeypatch):
    calls = []

    class Response:
        def raise_for_status(self):
            return None

        def json(self):
            return _overview_payload()

    class Client:
        def __init__(self, *args, **kwargs):
            return None

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return None

        def get(self, url, params):
            calls.append((url, params))
            return Response()

    monkeypatch.setenv("NYT_BOOKS_ENABLED", "true")
    monkeypatch.setenv("NYT_BOOKS_API_KEY", "test-key")
    monkeypatch.setattr(nyt_books.httpx, "Client", Client)
    nyt_books.clear_nyt_books_cache()

    first, first_status = nyt_books.current_overview()
    second, second_status = nyt_books.current_overview()

    assert len(first) == 1
    assert second == first
    assert first_status.cached is False
    assert second_status.cached is True
    assert len(calls) == 1
    assert calls[0][1]["api-key"] == "test-key"
