from typing import Literal

from pydantic import BaseModel, Field


class ReadingInsight(BaseModel):
    type: str
    label: str
    value: str
    detail: str | None = None


class ReadingInsightsResponse(BaseModel):
    profile_label: str
    insights: list[ReadingInsight]
    completed_books: int = Field(ge=0)
    unlock_threshold: int = Field(ge=1)
    status: Literal["ready", "insufficient_activity"]
    message: str | None = None
