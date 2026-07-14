# backend/routes/recommendations.py

import logging
import time

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from backend.auth.dependencies import get_current_user
from backend.db.database import get_db
from backend.db.models import Profile
from backend.services.recommendation import get_recommendation, get_recommendation_sections, recommendation_facets

router = APIRouter()
logger = logging.getLogger(__name__)


def _parse_exclude_ids(raw: str | None) -> set[str]:
    if not raw:
        return set()
    return {value.strip() for value in raw.split(",") if value.strip()}


@router.get("/recommend")
def recommend(
    top_n: int = Query(
        10,
        ge=1,
        le=10,
        description="Number of recommendations to return, up to 10.",
    ),
    style: str = Query(
        "balanced",
        description="Recommendation style: balanced, popular, or discovery",
    ),
    refresh: bool = Query(
        False,
        description="Rerun DB-only recommendation with a slight reshuffle among strong candidates.",
    ),
    exclude_ids: str | None = Query(
        None,
        description="Comma-separated recommendation ids to avoid on refresh when alternatives exist.",
    ),
    genre: str | None = Query(
        None,
        description="Only recommend books matching this genre.",
    ),
    author: str | None = Query(
        None,
        description="Only recommend books matching this author.",
    ),
    min_pages: int | None = Query(
        None,
        ge=0,
        description="Only recommend books with at least this many pages.",
    ),
    max_pages: int | None = Query(
        None,
        ge=0,
        description="Only recommend books with at most this many pages.",
    ),
    db: Session = Depends(get_db),
    current_user: Profile = Depends(get_current_user),
):
    started = time.perf_counter()
    try:
        return get_recommendation(
            db,
            current_user.id,
            top_n=top_n,
            style=style,
            refresh=refresh,
            exclude_ids=_parse_exclude_ids(exclude_ids),
            genre=genre,
            author=author,
            min_pages=min_pages,
            max_pages=max_pages,
        )
    finally:
        logger.info(
            "recommendation_request duration_ms=%.2f user_id=%s style=%s refresh=%s "
            "genre=%s min_pages=%s max_pages=%s",
            (time.perf_counter() - started) * 1000,
            current_user.id,
            style,
            refresh,
            genre,
            min_pages,
            max_pages,
        )


@router.get("/recommendations")
def recommendations(
    limit: int = Query(
        10,
        ge=1,
        le=20,
        description="Number of recommendations to return, up to 20.",
    ),
    style: str = Query(
        "balanced",
        description="Recommendation style: balanced, popular, or discovery",
    ),
    refresh: bool = Query(False),
    exclude_ids: str | None = Query(None),
    genre: str | None = Query(None),
    author: str | None = Query(None),
    min_pages: int | None = Query(None, ge=0),
    max_pages: int | None = Query(None, ge=0),
    db: Session = Depends(get_db),
    current_user: Profile = Depends(get_current_user),
):
    return get_recommendation(
        db,
        current_user.id,
        top_n=limit,
        style=style,
        refresh=refresh,
        exclude_ids=_parse_exclude_ids(exclude_ids),
        genre=genre,
        author=author,
        min_pages=min_pages,
        max_pages=max_pages,
    )


@router.get("/recommendations/sections")
def recommendation_sections(
    limit: int = Query(
        10,
        ge=1,
        le=20,
        description="Number of recommendations to return across generated sections.",
    ),
    style: str = Query(
        "balanced",
        description="Recommendation style: balanced, popular, or discovery",
    ),
    refresh: bool = Query(False),
    exclude_ids: str | None = Query(None),
    genre: str | None = Query(None),
    author: str | None = Query(None),
    min_pages: int | None = Query(None, ge=0),
    max_pages: int | None = Query(None, ge=0),
    db: Session = Depends(get_db),
    current_user: Profile = Depends(get_current_user),
):
    return get_recommendation_sections(
        db,
        current_user.id,
        top_n=limit,
        style=style,
        refresh=refresh,
        exclude_ids=_parse_exclude_ids(exclude_ids),
        genre=genre,
        author=author,
        min_pages=min_pages,
        max_pages=max_pages,
    )


@router.get("/recommendations/genres")
def recommendation_genres(
    limit: int = Query(12, ge=1, le=30),
    db: Session = Depends(get_db),
    current_user: Profile = Depends(get_current_user),
):
    return recommendation_facets(db, current_user.id, kind="genres", limit=limit)


@router.get("/recommendations/authors")
def recommendation_authors(
    limit: int = Query(12, ge=1, le=30),
    db: Session = Depends(get_db),
    current_user: Profile = Depends(get_current_user),
):
    return recommendation_facets(db, current_user.id, kind="authors", limit=limit)
