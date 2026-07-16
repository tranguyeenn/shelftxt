from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone
from uuid import UUID

from sqlalchemy import or_
from sqlalchemy.orm import Session

from backend.db.models import RecommendationFeedback
from backend.schemas.recommendation import RecommendationFeedbackCreate
from backend.services.recommendation_identity import recommendation_identity, recommendation_identity_aliases

NEGATIVE_FEEDBACK_TYPES = {"not_interested", "dismissed"}
POSITIVE_FEEDBACK_TYPES = {"interested", "accepted"}


def _clean_text(value: object) -> str:
    return re.sub(r"\s+", " ", str(value or "").strip())


def normalized_title_author_key(title: object, author: object) -> str:
    title_key = re.sub(r"[^a-z0-9]+", "-", _clean_text(title).casefold()).strip("-")
    author_key = re.sub(r"[^a-z0-9]+", "-", _clean_text(author).casefold()).strip("-")
    return f"title-author:{title_key}|{author_key}" if title_key or author_key else ""


def stable_recommendation_id(
    *,
    recommendation_id: str | None = None,
    work_id: str | None = None,
    isbn: str | None = None,
    title: str | None = None,
    author: str | None = None,
) -> str:
    if recommendation_id and _clean_text(recommendation_id):
        return _clean_text(recommendation_id)[:512]
    if work_id and _clean_text(work_id):
        return f"work:{_clean_text(work_id).casefold()}"[:512]
    if isbn and _clean_text(isbn):
        normalized_isbn = re.sub(r"[^0-9Xx]", "", isbn).upper()
        if normalized_isbn:
            return f"isbn:{normalized_isbn}"[:512]
    title_author = normalized_title_author_key(title, author)
    return (title_author or "unknown:recommendation")[:512]


def feedback_action(payload: RecommendationFeedbackCreate) -> str:
    return str(payload.action or payload.feedback_type or "not_interested").strip() or "not_interested"


def canonical_feedback_identity(payload: RecommendationFeedbackCreate) -> str:
    if payload.canonical_identity and _clean_text(payload.canonical_identity):
        return _clean_text(payload.canonical_identity)[:512]
    return recommendation_identity(
        work_id=payload.work_id,
        isbn=payload.isbn,
        title=payload.title,
        author=payload.author,
    )[:512]


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _expiry_for_feedback(db: Session, user_id: UUID, payload: RecommendationFeedbackCreate) -> datetime | None:
    now = _utcnow()
    action = feedback_action(payload)
    if action in POSITIVE_FEEDBACK_TYPES:
        return None

    identity = canonical_feedback_identity(payload)

    existing = (
        db.query(RecommendationFeedback)
        .filter(
            RecommendationFeedback.user_id == user_id,
            RecommendationFeedback.feedback_type == action,
            RecommendationFeedback.recommendation_identity == identity,
        )
        .one_or_none()
    )
    repeat_count = 0
    if existing is not None and isinstance(existing.inferred_trends, dict):
        repeat_count = int(existing.inferred_trends.get("_feedback_count") or 1)

    if repeat_count >= 2:
        return now + timedelta(days=180)
    if repeat_count == 1:
        return now + timedelta(days=90)
    return now + timedelta(days=30)


def create_feedback(
    db: Session,
    user_id: UUID,
    payload: RecommendationFeedbackCreate,
) -> RecommendationFeedback:
    action = feedback_action(payload)
    recommendation_id = stable_recommendation_id(
        recommendation_id=payload.recommendation_id,
        work_id=payload.work_id,
        isbn=payload.isbn,
        title=payload.title,
        author=payload.author,
    )
    identity = canonical_feedback_identity(payload)
    existing = (
        db.query(RecommendationFeedback)
        .filter(
            RecommendationFeedback.user_id == user_id,
            RecommendationFeedback.recommendation_identity == identity,
            RecommendationFeedback.feedback_type == action,
        )
        .one_or_none()
    )
    inferred_trends = dict(payload.inferred_trends or {})
    current_count = 0
    if existing is not None and isinstance(existing.inferred_trends, dict):
        current_count = int(existing.inferred_trends.get("_feedback_count") or 1)
    inferred_trends["_feedback_count"] = current_count + 1
    values = {
        "book_id": payload.book_id,
        "recommendation_id": recommendation_id,
        "recommendation_identity": identity,
        "work_id": _clean_text(payload.work_id) or None,
        "isbn": _clean_text(payload.isbn) or None,
        "canonical_title": _clean_text(payload.title) or None,
        "canonical_author": _clean_text(payload.author) or None,
        "feedback_type": action,
        "expires_at": _expiry_for_feedback(db, user_id, payload),
        "source": _clean_text(payload.source) or None,
        "cluster_id": _clean_text(payload.cluster_id) or None,
        "related_genres": [_clean_text(value) for value in payload.genres if _clean_text(value)],
        "related_authors": [_clean_text(value) for value in payload.authors if _clean_text(value)],
        "related_books": payload.related_books[:10],
        "recommendation_score": payload.recommendation_score,
        "explanation": _clean_text(payload.reason or payload.explanation) or None,
        "inferred_trends": inferred_trends,
    }
    if existing is not None:
        for key, value in values.items():
            setattr(existing, key, value)
        db.commit()
        db.refresh(existing)
        return existing

    feedback = RecommendationFeedback(
        user_id=user_id,
        **values,
    )
    db.add(feedback)
    db.commit()
    db.refresh(feedback)
    return feedback


def active_feedback_for_user(db: Session, user_id: UUID) -> list[RecommendationFeedback]:
    now = _utcnow()
    return (
        db.query(RecommendationFeedback)
        .filter(
            RecommendationFeedback.user_id == user_id,
            or_(
                RecommendationFeedback.expires_at.is_(None),
                RecommendationFeedback.expires_at > now,
            ),
        )
        .order_by(RecommendationFeedback.created_at.desc())
        .all()
    )


def feedback_to_record(feedback: RecommendationFeedback) -> dict:
    return {
        "id": feedback.id,
        "user_id": str(feedback.user_id),
        "book_id": feedback.book_id,
        "recommendation_id": feedback.recommendation_id,
        "recommendation_identity": feedback.recommendation_identity,
        "canonical_identity": feedback.recommendation_identity,
        "work_id": feedback.work_id,
        "isbn": feedback.isbn,
        "canonical_title": feedback.canonical_title,
        "canonical_author": feedback.canonical_author,
        "feedback_type": feedback.feedback_type,
        "action": feedback.feedback_type,
        "source": feedback.source,
        "cluster_id": feedback.cluster_id,
        "created_at": feedback.created_at,
        "expires_at": feedback.expires_at,
        "related_genres": feedback.related_genres or [],
        "related_authors": feedback.related_authors or [],
        "related_books": feedback.related_books or [],
        "recommendation_score": feedback.recommendation_score,
        "explanation": feedback.explanation,
        "inferred_trends": feedback.inferred_trends or {},
    }


def feedback_to_ranking_records(feedback: list[RecommendationFeedback]) -> list[dict]:
    return [feedback_to_record(item) for item in feedback]


def active_not_interested_identities(db: Session, user_id: UUID) -> set[str]:
    identities: set[str] = set()
    for item in active_feedback_for_user(db, user_id):
        if item.feedback_type not in NEGATIVE_FEEDBACK_TYPES:
            continue
        identities.update(
            recommendation_identity_aliases(
                work_id=item.work_id,
                isbn=item.isbn,
                title=item.canonical_title,
                author=item.canonical_author,
            )
        )
        for value in (item.recommendation_identity, item.recommendation_id):
            clean = str(value or "").strip()
            if clean:
                identities.add(clean)
                identities.add(clean.casefold())
    return identities
