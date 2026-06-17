from typing import Literal

from pydantic import BaseModel, Field


class MetadataJobStatus(BaseModel):
    status: Literal["pending", "processing", "completed", "failed"]
    processed_count: int = Field(ge=0)
    total_count: int = Field(ge=0)
    error_message: str | None = None


class MetadataStatusResponse(BaseModel):
    books_with_genres: int = Field(ge=0)
    total_books: int = Field(ge=0)
    job: MetadataJobStatus
