from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


FeedbackType = Literal["not_interested", "dismissed", "interested", "accepted"]


class RecommendationFeedbackCreate(BaseModel):
    canonical_identity: str | None = Field(default=None, max_length=512)
    recommendation_id: str | None = Field(default=None, max_length=512)
    feedback_type: FeedbackType | None = None
    action: FeedbackType | None = None
    current_recommendation_ids: list[str] = Field(default_factory=list)
    style: str = "balanced"
    book_id: int | None = None
    work_id: str | None = None
    isbn: str | None = None
    title: str | None = None
    author: str | None = None
    genres: list[str] = Field(default_factory=list)
    authors: list[str] = Field(default_factory=list)
    related_books: list[dict] = Field(default_factory=list)
    recommendation_score: float | None = None
    explanation: str | None = None
    reason: str | None = None
    source: str | None = None
    cluster_id: str | None = None
    inferred_trends: dict | None = None


class RecommendationFeedbackRecord(BaseModel):
    id: int
    user_id: str
    book_id: int | None
    recommendation_id: str
    recommendation_identity: str
    canonical_identity: str
    work_id: str | None
    isbn: str | None
    canonical_title: str | None
    canonical_author: str | None
    feedback_type: str
    action: str
    source: str | None
    cluster_id: str | None
    created_at: datetime
    expires_at: datetime | None
    related_genres: list[str]
    related_authors: list[str]
    related_books: list[dict]
    recommendation_score: float | None
    explanation: str | None
    inferred_trends: dict | None


class RecommendationFeedbackResponse(BaseModel):
    status: str = "stored"
    removed_recommendation_id: str
    feedback: RecommendationFeedbackRecord
    should_hide: bool
    replacement: dict | None = None
    recommendations: list[dict] = Field(default_factory=list)
    recommendation_count: int = 0
