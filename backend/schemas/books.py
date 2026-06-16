from typing import Any, Literal

from pydantic import AliasChoices, BaseModel, ConfigDict, Field, field_validator


class AddBook(BaseModel):
    title: str = Field(min_length=1)
    author: str = Field(min_length=1)
    total_pages: int | None = Field(default=None, gt=0)


class PatchBook(BaseModel):
    title: str = Field(min_length=1)
    new_title: str | None = Field(default=None, min_length=1)
    author: str | None = Field(default=None, min_length=1)
    total_pages: int | None = Field(default=None, gt=0)
    pages_read: int | None = Field(default=None, ge=0)
    move_to: Literal["want", "reading", "read", "dnf"] | None = None
    rating: float | None = Field(default=None, ge=1, le=5)
    date_read: str | None = None


class ImportRow(BaseModel):
    title: str = Field(min_length=1)
    author: str | None = Field(default=None, min_length=1)
    total_pages: int | None = Field(default=None, gt=0)
    read_status: str | None = Field(
        default=None,
        validation_alias=AliasChoices("read_status", "status", "Read Status"),
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
    imported: int = Field(ge=0)
    skipped: int = Field(ge=0)
