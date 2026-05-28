from typing import Literal

from pydantic import BaseModel, Field


class AddBook(BaseModel):
    title: str
    author: str
    total_pages: int | None = None


class PatchBook(BaseModel):
    title: str
    new_title: str | None = None
    author: str | None = None
    total_pages: int | None = None
    pages_read: int | None = None
    move_to: str | None = None
    rating: float | None = None
    date_read: str | None = None


class ImportRow(BaseModel):
    title: str
    author: str | None = None
    total_pages: int | None = None


class ImportBooks(BaseModel):
    books: list[ImportRow]


class BookProgressPatch(BaseModel):
    status: Literal["not_started", "reading", "completed"]
    pages_read: int = Field(ge=0)


class ClearLibraryRequest(BaseModel):
    confirm: bool