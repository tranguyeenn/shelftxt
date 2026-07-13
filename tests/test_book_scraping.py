import asyncio
from unittest.mock import AsyncMock, patch

import httpx

from backend.services.book_scraping.client import BookScrapingClient, FetchedPage, ScrapeBlocked, ScrapeUnavailable
from backend.services.book_scraping.metadata import normalize_isbn, parse_book_metadata
from backend.services.book_scraping.service import scrape_book_metadata


def test_book_jsonld_parses_metadata():
    html = """
    <script type="application/ld+json">
    {"@type":"Book","name":"Dune","author":{"name":"Frank Herbert"},"isbn":"978-0-441-17271-9",
     "image":{"url":"/cover.jpg"},"publisher":{"name":"Ace"},"datePublished":"1965-08-01",
     "numberOfPages":"412 pages","inLanguage":"en","description":"A classic."}
    </script>
    """

    metadata, malformed = parse_book_metadata(html, "https://www.penguinrandomhouse.com/books/dune/")

    assert malformed is False
    assert metadata is not None
    assert metadata.title == "Dune"
    assert metadata.authors == ["Frank Herbert"]
    assert metadata.isbn_uid == "9780441172719"
    assert metadata.cover_url == "https://www.penguinrandomhouse.com/cover.jpg"
    assert metadata.total_pages == 412
    assert metadata.confidence_score == 0.95


def test_product_jsonld_representing_book_parses_metadata():
    html = """
    <script type="application/ld+json">
    {"@type":"Product","name":"Kindred","author":["Octavia E. Butler"],"gtin13":"9780807083697"}
    </script>
    """

    metadata, _malformed = parse_book_metadata(html, "https://bookshop.org/p/books/kindred")

    assert metadata is not None
    assert metadata.title == "Kindred"
    assert metadata.authors == ["Octavia E. Butler"]
    assert metadata.isbn_uid == "9780807083697"
    assert metadata.confidence_score == 0.8


def test_graph_jsonld_parses_book_node():
    html = """
    <script type="application/ld+json">
    {"@graph":[{"@type":"WebPage","name":"Page"},{"@type":"Book","headline":"Beloved","author":"Toni Morrison"}]}
    </script>
    """

    metadata, _malformed = parse_book_metadata(html, "https://www.penguinrandomhouse.com/books/beloved/")

    assert metadata is not None
    assert metadata.title == "Beloved"
    assert metadata.authors == ["Toni Morrison"]


def test_malformed_jsonld_falls_back_to_open_graph():
    html = """
    <script type="application/ld+json">{bad json</script>
    <meta property="og:title" content="Dune">
    <meta name="author" content="Frank Herbert">
    <meta property="og:description" content="A classic.">
    """

    metadata, malformed = parse_book_metadata(html, "https://bookshop.org/p/books/dune")

    assert malformed is True
    assert metadata is not None
    assert metadata.parser_used == "html_meta"
    assert metadata.title == "Dune"


def test_open_graph_fallback_parses_book_metadata():
    html = """
    <meta property="og:title" content="  Dune &amp; Empire  ">
    <meta property="og:description" content="A book page">
    <meta property="og:image" content="/dune.jpg">
    <meta name="book:author" content=" Frank Herbert ">
    <meta name="book:isbn" content="978-0-441-17271-9">
    """

    metadata, _malformed = parse_book_metadata(html, "https://bookshop.org/p/books/dune")

    assert metadata is not None
    assert metadata.title == "Dune & Empire"
    assert metadata.authors == ["Frank Herbert"]
    assert metadata.isbn_uid == "9780441172719"
    assert metadata.cover_url == "https://bookshop.org/dune.jpg"


def test_isbn_normalization():
    assert normalize_isbn("978-0-441-17271-9") == "9780441172719"
    assert normalize_isbn("0-441-17271-7") == "0441172717"
    assert normalize_isbn("not an isbn") is None


def test_private_ip_rejection():
    result = asyncio.run(scrape_book_metadata("http://127.0.0.1/book", allow_unknown_domain=True))

    assert result.status == "blocked"
    assert result.diagnostics.exception_type == "ScrapeBlocked"


def test_robots_denial(monkeypatch):
    async def blocked_fetch(self, url, *, allow_unknown_domain=False):
        raise ScrapeBlocked("robots.txt disallows this URL")

    monkeypatch.setattr(BookScrapingClient, "fetch", blocked_fetch)

    result = asyncio.run(scrape_book_metadata("https://bookshop.org/p/books/dune", allow_unknown_domain=True))

    assert result.status == "blocked"
    assert result.diagnostics.robots_allowed is False


def test_redirect_limit_failure(monkeypatch):
    async def redirect_fetch(self, url, *, allow_unknown_domain=False):
        raise ScrapeUnavailable("too many redirects")

    monkeypatch.setattr(BookScrapingClient, "fetch", redirect_fetch)

    result = asyncio.run(scrape_book_metadata("https://bookshop.org/p/books/dune", allow_unknown_domain=True))

    assert result.status == "failed"
    assert result.diagnostics.exception_type == "ScrapeUnavailable"


def test_oversized_response_failure(monkeypatch):
    async def oversized_fetch(self, url, *, allow_unknown_domain=False):
        raise ScrapeUnavailable("response too large")

    monkeypatch.setattr(BookScrapingClient, "fetch", oversized_fetch)

    result = asyncio.run(scrape_book_metadata("https://bookshop.org/p/books/dune", allow_unknown_domain=True))

    assert result.status == "failed"


def test_timeout_failure(monkeypatch):
    async def timeout_fetch(self, url, *, allow_unknown_domain=False):
        raise httpx.ReadTimeout("timed out")

    monkeypatch.setattr(BookScrapingClient, "fetch", timeout_fetch)

    result = asyncio.run(scrape_book_metadata("https://bookshop.org/p/books/dune", allow_unknown_domain=True))

    assert result.status == "failed"
    assert result.diagnostics.outcome == "timeout"


def test_invalid_content_type_failure(monkeypatch):
    async def content_type_fetch(self, url, *, allow_unknown_domain=False):
        raise ScrapeUnavailable("invalid content type")

    monkeypatch.setattr(BookScrapingClient, "fetch", content_type_fetch)

    result = asyncio.run(scrape_book_metadata("https://bookshop.org/p/books/dune", allow_unknown_domain=True))

    assert result.status == "failed"


def test_user_submitted_url_scraping(monkeypatch):
    async def fetched(self, url, *, allow_unknown_domain=False):
        return FetchedPage(
            url=url,
            domain="example.com",
            html='<script type="application/ld+json">{"@type":"Book","name":"Dune","author":"Frank Herbert"}</script>',
            status_code=200,
            content_type="text/html",
            elapsed_ms=1.0,
            robots_allowed=True,
        )

    monkeypatch.setattr(BookScrapingClient, "fetch", fetched)

    result = asyncio.run(scrape_book_metadata("https://example.com/dune", allow_unknown_domain=True))

    assert result.status == "success"
    assert result.metadata is not None
    assert result.metadata.title == "Dune"
