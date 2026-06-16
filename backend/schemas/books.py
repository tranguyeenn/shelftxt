from typing import Any, Literal

from pydantic import AliasChoices, BaseModel, ConfigDict, Field, field_validator


class ReadingDateRangeMixin(BaseModel):
    start_date: str | None = None
    end_date: str | None = None


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
    read_status: Literal["not_started", "reading", "completed", "dnf"] | None = None
    status: Literal["not_started", "reading", "completed", "dnf"] | None = None


class ImportRow(ReadingDateRangeMixin):
    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "title": "The Left Hand of Darkness",
                    "author": "Ursula K. Le Guin",
                    "total_pages": 304,
                    "read_status": "reading",
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
    last_date_read: str | None = Field(
        default=None,
        validation_alias=AliasChoices("last_date_read", "Last Date Read", "date_read", "Date Read"),
    )
    start_date: str | None = Field(
        default=None,
        validation_alias=AliasChoices("start_date", "Start Date", "Started", "Date Started"),
    )
    end_date: str | None = Field(
        default=None,
        validation_alias=AliasChoices("end_date", "End Date", "Finished", "Finished On"),
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
                            "pages_read": 120,
                            "progress_percent": 39.47,
                        }
                    ]
                }
            ]
        }
    )

    books: list[ImportRow] = Field(min_length=1)


class BookProgressPatch(BaseModel):
    status: Literal["not_started", "reading", "completed", "dnf"]
    pages_read: int = Field(ge=0)


class ClearLibraryRequest(BaseModel):
    confirm: bool


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
