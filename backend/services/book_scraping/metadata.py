from __future__ import annotations

import html
import re
from html.parser import HTMLParser
from typing import Any
from urllib.parse import urljoin

from backend.services.book_scraping.domains import (
    is_publisher_domain,
    is_retailer_domain,
    normalize_domain,
)
from backend.services.book_scraping.jsonld import extract_jsonld_documents, iter_jsonld_nodes
from backend.services.book_scraping.models import ScrapedBookMetadata


class MetaTagParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.meta: dict[str, str] = {}

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag.lower() != "meta":
            return
        attr_map = {name.lower(): value for name, value in attrs if value is not None}
        key = attr_map.get("property") or attr_map.get("name")
        content = attr_map.get("content")
        if key and content and key not in self.meta:
            self.meta[key] = content


def clean_text(value: object) -> str | None:
    if value is None:
        return None
    text = html.unescape(str(value))
    text = " ".join(text.split())
    return text or None


def normalize_isbn(value: object) -> str | None:
    cleaned = re.sub(r"[^0-9Xx]", "", str(value or "")).upper()
    if len(cleaned) == 10 and _valid_isbn10(cleaned):
        return cleaned
    if len(cleaned) == 13 and _valid_isbn13(cleaned):
        return cleaned
    return None


def _valid_isbn10(value: str) -> bool:
    total = 0
    for index, char in enumerate(value):
        if char == "X" and index == 9:
            digit = 10
        elif char.isdigit():
            digit = int(char)
        else:
            return False
        total += digit * (10 - index)
    return total % 11 == 0


def _valid_isbn13(value: str) -> bool:
    if not value.isdigit():
        return False
    total = sum((1 if index % 2 == 0 else 3) * int(char) for index, char in enumerate(value))
    return total % 10 == 0


def normalize_page_count(value: object) -> int | None:
    if value is None:
        return None
    match = re.search(r"\d+", str(value))
    if not match:
        return None
    pages = int(match.group(0))
    return pages if pages > 0 else None


def normalize_date(value: object) -> str | None:
    text = clean_text(value)
    if not text:
        return None
    match = re.search(r"\d{4}(?:-\d{1,2}(?:-\d{1,2})?)?", text)
    return match.group(0) if match else text


def _first(*values: object) -> str | None:
    for value in values:
        if cleaned := clean_text(value):
            return cleaned
    return None


def _as_list(value: Any) -> list[Any]:
    if value is None:
        return []
    return value if isinstance(value, list) else [value]


def _names(value: Any) -> list[str]:
    names: list[str] = []
    for item in _as_list(value):
        if isinstance(item, dict):
            name = clean_text(item.get("name"))
        else:
            name = clean_text(item)
        if name and name not in names:
            names.append(name)
    return names


def _image(value: Any, base_url: str) -> str | None:
    for item in _as_list(value):
        candidate = item.get("url") if isinstance(item, dict) else item
        if cleaned := clean_text(candidate):
            return urljoin(base_url, cleaned)
    return None


def _jsonld_type(node: dict) -> set[str]:
    values = _as_list(node.get("@type"))
    return {str(value).casefold() for value in values}


def _is_book_node(node: dict) -> bool:
    types = _jsonld_type(node)
    if "book" in types:
        return True
    if "product" in types:
        text = " ".join(str(node.get(key, "")) for key in ("category", "productID", "gtin13", "isbn"))
        return bool(normalize_isbn(text)) or "book" in text.casefold()
    return False


def _metadata_from_jsonld(node: dict, url: str, domain: str) -> ScrapedBookMetadata:
    publisher = node.get("publisher")
    publisher_name = clean_text(publisher.get("name")) if isinstance(publisher, dict) else clean_text(publisher)
    isbn = (
        normalize_isbn(node.get("isbn"))
        or normalize_isbn(node.get("gtin13"))
        or normalize_isbn(node.get("gtin"))
        or normalize_isbn(node.get("productID"))
    )
    types = _jsonld_type(node)
    return ScrapedBookMetadata(
        title=_first(node.get("name"), node.get("headline"), node.get("alternateName")),
        authors=_names(node.get("author")),
        isbn_uid=isbn,
        description=clean_text(node.get("description")),
        cover_url=_image(node.get("image"), url),
        total_pages=normalize_page_count(node.get("numberOfPages")),
        publisher=publisher_name,
        publish_date=normalize_date(node.get("datePublished")),
        language=clean_text(node.get("inLanguage")),
        book_format=clean_text(node.get("bookFormat")),
        source_url=url,
        source_domain=domain,
        parser_used="jsonld",
        confidence_score=_confidence(domain, "jsonld"),
        is_book_jsonld="book" in types,
    )


def _metadata_from_meta(html_text: str, url: str, domain: str) -> ScrapedBookMetadata:
    parser = MetaTagParser()
    parser.feed(html_text)
    meta = parser.meta
    authors = []
    for key in ("book:author", "author"):
        if value := clean_text(meta.get(key)):
            authors.append(value)
    isbn = normalize_isbn(meta.get("book:isbn")) or normalize_isbn(meta.get("product:isbn")) or normalize_isbn(meta.get("isbn"))
    return ScrapedBookMetadata(
        title=_first(meta.get("og:title"), meta.get("title")),
        authors=list(dict.fromkeys(authors)),
        isbn_uid=isbn,
        description=_first(meta.get("og:description"), meta.get("description")),
        cover_url=_image(meta.get("og:image"), url),
        source_url=url,
        source_domain=domain,
        parser_used="html_meta",
        confidence_score=_confidence(domain, "html_meta"),
    )


def _confidence(domain: str, parser_used: str) -> float:
    if parser_used == "jsonld":
        if is_publisher_domain(domain):
            return 0.95
        if is_retailer_domain(domain):
            return 0.80
        return 0.55
    if is_publisher_domain(domain):
        return 0.85
    if is_retailer_domain(domain):
        return 0.65
    return 0.45


def is_probably_book(metadata: ScrapedBookMetadata) -> bool:
    if not metadata.title:
        return False
    return bool(
        metadata.authors
        or metadata.isbn_uid
        or metadata.is_book_jsonld
        or (metadata.publisher and metadata.publish_date)
    )


def fields_extracted(metadata: ScrapedBookMetadata) -> list[str]:
    values = metadata.model_dump()
    return sorted(
        key for key, value in values.items()
        if key not in {"source_url", "source_domain", "metadata_source", "confidence_score"}
        and value not in (None, [], "")
    )


def parse_book_metadata(html_text: str, url: str) -> tuple[ScrapedBookMetadata | None, bool]:
    domain = normalize_domain(url)
    documents, malformed = extract_jsonld_documents(html_text)
    for document in documents:
        for node in iter_jsonld_nodes(document):
            if isinstance(node, dict) and _is_book_node(node):
                metadata = _metadata_from_jsonld(node, url, domain)
                if is_probably_book(metadata):
                    return metadata, malformed

    metadata = _metadata_from_meta(html_text, url, domain)
    if is_probably_book(metadata):
        return metadata, malformed
    return None, malformed
