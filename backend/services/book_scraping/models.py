from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


ScrapeStatus = Literal["success", "empty", "blocked", "failed"]


class ScrapedBookMetadata(BaseModel):
    title: str | None = None
    authors: list[str] = Field(default_factory=list)
    isbn_uid: str | None = None
    description: str | None = None
    cover_url: str | None = None
    total_pages: int | None = None
    publisher: str | None = None
    publish_date: str | None = None
    language: str | None = None
    book_format: str | None = None
    series_name: str | None = None
    series_position: float | None = None
    series_position_label: str | None = None
    series_type: str | None = None
    series_books: list[dict] = Field(default_factory=list)
    series_source: str | None = None
    series_confidence: float | None = Field(default=None, ge=0, le=1)
    series_publication_order: list[dict] | None = None
    series_chronological_order: list[dict] | None = None
    metadata_source: str = "scraped"
    source_url: str
    source_domain: str
    parser_used: str | None = None
    confidence_score: float = Field(default=0.0, ge=0, le=1)
    is_book_jsonld: bool = False

    def to_search_result(self) -> dict:
        return {
            "title": self.title,
            "authors": self.authors,
            "isbn_uid": self.isbn_uid,
            "description": self.description,
            "cover_url": self.cover_url,
            "total_pages": self.total_pages,
            "publisher": self.publisher,
            "publish_date": self.publish_date,
            "language": self.language,
            "series_name": self.series_name,
            "series_position": self.series_position,
            "series_position_label": self.series_position_label,
            "series_type": self.series_type,
            "series_books": self.series_books,
            "series_source": self.series_source,
            "series_confidence": self.series_confidence,
            "series_publication_order": self.series_publication_order,
            "series_chronological_order": self.series_chronological_order,
            "metadata_source": self.metadata_source,
            "confidence_score": self.confidence_score,
            "source_urls": [self.source_url],
        }


class ScrapeDiagnostic(BaseModel):
    domain: str | None = None
    outcome: str
    http_status: int | None = None
    elapsed_ms: float = 0.0
    parser_used: str | None = None
    robots_allowed: bool | None = None
    fields_extracted: list[str] = Field(default_factory=list)
    exception_type: str | None = None
    response_content_type: str | None = None
    cache_hit: bool = False
    request_url: str | None = None


class ScrapeResult(BaseModel):
    status: ScrapeStatus
    metadata: ScrapedBookMetadata | None = None
    diagnostics: ScrapeDiagnostic
