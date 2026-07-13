from typing import Any, Literal

from pydantic import AliasChoices, BaseModel, ConfigDict, Field, field_validator

from backend.services.ratings import RATING_COLUMN_ALIASES, parse_rating_value


class ReadingDateRangeMixin(BaseModel):
    start_date: str | None = None
    end_date: str | None = None


TrackingMode = Literal["percentage", "pages"]


class AddBook(ReadingDateRangeMixin):
    title: str = Field(
        min_length=1,
        validation_alias=AliasChoices("title", "Title"),
    )
    author: str = Field(min_length=1)
    total_pages: int | None = Field(
        default=None,
        gt=0,
        validation_alias=AliasChoices("total_pages", "Total Pages"),
    )
    tracking_mode: TrackingMode | None = None
    isbn_uid: str | None = Field(default=None, min_length=1)
    status: Literal["not_started", "reading", "completed", "dnf"] = "not_started"
    star_rating: float | None = Field(default=None, ge=0, le=5)
    description: str | None = None
    cover_url: str | None = None
    subjects: list[str] = Field(default_factory=list)
    genres: list[str] = Field(default_factory=list)
    first_publish_year: int | None = Field(default=None, gt=0)
    metadata_source: str | None = None
    work_key: str | None = None
    edition_key: str | None = None
    related_isbns: list[str] = Field(default_factory=list)
    publisher: str | None = None
    publish_date: str | None = None
    language: str | None = None
    edition_type: Literal["original", "translation", "illustrated", "adaptation", "unknown"] = "unknown"
    original_title: str | None = None
    notes: str | None = None


class BookSearchResult(BaseModel):
    title: str
    authors: list[str]
    isbn_uid: str | None = None
    description: str | None = None
    cover_url: str | None = None
    total_pages: int | None = None
    subjects: list[str]
    genres: list[str]
    first_publish_year: int | None = None
    metadata_source: str
    work_key: str | None = None
    edition_key: str | None = None
    publisher: str | None = None
    publish_date: str | None = None
    related_isbns: list[str]
    already_in_library: bool
    confidence_score: float = Field(default=0.0, ge=0, le=1)
    canonical_title: str | None = None
    canonical_author: str | None = None
    edition_count: int = 1
    edition_type: Literal["original", "translation", "illustrated", "adaptation", "unknown"] = "unknown"
    primary_edition: dict[str, Any] | None = None
    editions: list[dict[str, Any]] = Field(default_factory=list)
    editions_loaded: bool = False


class BookSearchProviderDiagnostic(BaseModel):
    source: str
    success: bool
    result_count: int = 0
    latency_ms: float = 0.0
    outcome: str
    http_status: int | None = None
    request_url: str | None = None
    response_body: str | None = None
    error_type: str | None = None


class BookDiscoveryProviderDiagnostic(BaseModel):
    provider: str
    outcome: str
    request_attempted: bool
    result_count: int = 0
    latency_ms: float = 0.0
    http_status: int | None = None
    error_type: str | None = None
    transient: bool = False
    parser_version: str | None = None


class BookSearchResponse(BaseModel):
    status: Literal["ok", "empty", "degraded"]
    results: list[BookSearchResult]
    message: str | None = None
    diagnostics: list[BookSearchProviderDiagnostic] | None = None


class BookDiscoveryResponse(BaseModel):
    status: Literal["ok", "empty", "degraded"]
    results: list[BookSearchResult]
    message: str | None = None
    diagnostics: list[BookDiscoveryProviderDiagnostic]


class ManualMetadataDuplicate(BaseModel):
    id: str
    title: str
    author: str
    reason: str


class ManualMetadataRequest(BaseModel):
    title: str = Field(min_length=1)
    authors: list[str] = Field(default_factory=list)
    isbn_10: str | None = None
    isbn_13: str | None = None
    cover_url: str | None = None
    publisher: str | None = None
    publication_date: str | None = None
    publication_year: int | None = Field(default=None, gt=0)
    page_count: int | None = Field(default=None, gt=0)
    language: str | None = None
    edition_type: Literal["original", "translation", "illustrated", "adaptation", "unknown"] = "unknown"
    original_title: str | None = None
    notes: str | None = None
    work_id: str | None = None
    edition_id: str | None = None


class ManualMetadataResponse(BaseModel):
    metadata: dict[str, Any]
    duplicates: list[ManualMetadataDuplicate]


class WorkEditionsResponse(BaseModel):
    status: Literal["ok", "empty"]
    work_id: str
    edition_count: int = Field(ge=0)
    editions_loaded: bool
    primary_edition: dict[str, Any] | None = None
    editions: list[dict[str, Any]] = Field(default_factory=list)
    message: str | None = None


class MetadataFromUrlRequest(BaseModel):
    url: str = Field(min_length=1, max_length=2000)


class MetadataFromUrlResponse(BaseModel):
    status: Literal["success", "empty", "blocked", "failed"]
    metadata: dict[str, Any] | None = None
    diagnostics: dict[str, Any] | None = None


class PatchBook(ReadingDateRangeMixin):
    title: str = Field(
        min_length=1,
        validation_alias=AliasChoices("title", "Title"),
    )
    new_title: str | None = Field(default=None, min_length=1)
    author: str | None = None
    isbn_uid: str | None = Field(default=None, min_length=1)
    total_pages: int | None = Field(
        default=None,
        gt=0,
        validation_alias=AliasChoices("total_pages", "Total Pages"),
    )
    pages_read: int | None = Field(default=None, ge=0)
    progress_percent: float | None = Field(default=None, ge=0, le=100)
    tracking_mode: TrackingMode | None = None
    move_to: Literal["want", "reading", "read", "dnf"] | None = None
    read_status: Literal["not_started", "reading", "completed", "dnf"] | None = None
    status: Literal["not_started", "reading", "completed", "dnf"] | None = None
    rating: float | None = Field(default=None, ge=1, le=5)
    date_read: str | None = None


class PatchBookById(ReadingDateRangeMixin):
    title: str | None = Field(default=None, min_length=1)
    author: str | None = None
    isbn_uid: str | None = Field(default=None, min_length=1)
    total_pages: int | None = Field(default=None, gt=0)
    pages_read: int | None = Field(default=None, ge=0)
    progress_percent: float | None = Field(default=None, ge=0, le=100)
    tracking_mode: TrackingMode | None = None
    read_status: Literal["not_started", "reading", "completed", "dnf"] | None = None
    status: Literal["not_started", "reading", "completed", "dnf"] | None = None
    star_rating: float | None = Field(default=None, ge=0, le=5)


class ImportRow(ReadingDateRangeMixin):
    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "title": "The Left Hand of Darkness",
                    "author": "Ursula K. Le Guin",
                    "total_pages": 304,
                    "read_status": "reading",
                    "star_rating": 4.75,
                    "pages_read": 120,
                    "progress_percent": 39.47,
                }
            ]
        }
    )

    title: str = Field(
        min_length=1,
        validation_alias=AliasChoices("title", "Title"),
    )
    isbn_uid: str | None = Field(
        default=None,
        min_length=1,
        validation_alias=AliasChoices("isbn_uid", "ISBN/UID", "isbn", "ISBN"),
    )
    author: str | None = Field(
        default=None,
        min_length=1,
        validation_alias=AliasChoices("author", "authors", "Author", "Authors"),
    )
    total_pages: int | None = Field(
        default=None,
        gt=0,
        validation_alias=AliasChoices("total_pages", "Total Pages"),
    )
    read_status: str | None = Field(
        default=None,
        validation_alias=AliasChoices("read_status", "status", "Read Status"),
    )
    tracking_mode: TrackingMode | None = Field(
        default=None,
        validation_alias=AliasChoices("tracking_mode", "Tracking Mode"),
    )
    star_rating: float | None = Field(
        default=None,
        ge=0,
        le=5,
        validation_alias=AliasChoices(*RATING_COLUMN_ALIASES),
    )
    last_date_read: str | None = Field(
        default=None,
        validation_alias=AliasChoices("last_date_read", "Last Date Read", "date_read", "Date Read"),
    )
    dates_read: str | None = Field(
        default=None,
        validation_alias=AliasChoices("dates_read", "Dates Read", "Dates read"),
    )
    start_date: str | None = Field(
        default=None,
        validation_alias=AliasChoices(
            "start_date",
            "Start Date",
            "Started",
            "Date Started",
            "date_started",
        ),
    )
    end_date: str | None = Field(
        default=None,
        validation_alias=AliasChoices(
            "end_date",
            "End Date",
            "Finished",
            "Finished On",
            "finish_date",
            "Finish Date",
            "date_finished",
            "Date Finished",
        ),
    )
    pages_read: int | None = Field(
        default=None,
        ge=0,
        validation_alias=AliasChoices("pages_read", "Pages Read"),
    )
    progress_percent: float | None = Field(
        default=None,
        ge=0,
        le=100,
        validation_alias=AliasChoices("progress_percent", "Progress (%)"),
    )

    @field_validator("star_rating", mode="before")
    @classmethod
    def parse_import_star_rating(cls, value):
        return parse_rating_value(value)


class ImportBooks(BaseModel):
    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "books": [
                        {
                            "title": "The Left Hand of Darkness",
                            "author": "Ursula K. Le Guin",
                            "total_pages": 304,
                            "read_status": "reading",
                            "star_rating": 4.75,
                            "pages_read": 120,
                            "progress_percent": 39.47,
                        }
                    ]
                }
            ]
        }
    )

    books: list[ImportRow] = Field(min_length=1)


class BookProgressPatch(ReadingDateRangeMixin):
    status: Literal["not_started", "reading", "completed", "dnf"] | None = None
    read_status: Literal["not_started", "reading", "completed", "dnf"] | None = None
    tracking_mode: TrackingMode | None = None
    pages_read: int | None = Field(default=None, ge=0)
    total_pages: int | None = Field(default=None, gt=0)
    progress_percent: float | None = Field(default=None, ge=0, le=100)


class ClearLibraryRequest(BaseModel):
    confirm: bool


class PageCountLookupResponse(BaseModel):
    found: bool
    source: str
    book: dict[str, Any]


class PageCountBackfillResponse(BaseModel):
    processed: int = Field(ge=0)
    updated: int = Field(ge=0)
    unresolved: int = Field(ge=0)


class BookResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    title: str
    authors: str
    isbn_uid: str
    read_status: str | None = None
    star_rating: float | None = None
    last_date_read: str | None = None
    start_date: str | None = None
    end_date: str | None = None
    progress_percent: float | None = None
    pages_read: int | None = None
    total_pages: int | None = None
    tracking_mode: str | None = None
    description: str | None = None
    cover_url: str | None = None
    subjects: list[str] | None = None
    genres: list[str] | None = None
    first_publish_year: int | None = None
    metadata_source: str | None = None
    metadata_enriched_at: str | None = None
    page_count_checked: bool = False
    page_count_source: str | None = None


class BooksPage(BaseModel):
    """Paginated library list (GET /books). Each result row uses CSV column names."""

    page: int = Field(ge=1)
    limit: int = Field(ge=1, le=100)
    total: int = Field(ge=0)
    results: list[dict[str, Any]]


class MessageResponse(BaseModel):
    message: str


class ImportResult(BaseModel):
    imported_count: int = Field(ge=0)
    skipped_count: int = Field(ge=0)
    duplicate_count: int = Field(ge=0)
    skipped_duplicates: int = Field(ge=0)
    enriched_count: int = Field(ge=0)
    enrichment_skipped_count: int = Field(ge=0)
    enrichment_failed_count: int = Field(ge=0)
