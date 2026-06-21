# backend/routes/recommendations.py

import logging
import time

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from backend.auth.dependencies import get_current_user
from backend.db.database import get_db
from backend.db.models import Profile
from backend.services.recommendation import get_recommendation

router = APIRouter()
logger = logging.getLogger(__name__)


def _parse_exclude_ids(raw: str | None) -> set[str]:
    if not raw:
        return set()
    return {value.strip() for value in raw.split(",") if value.strip()}


@router.get("/recommend")
def recommend(
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
    db: Session = Depends(get_db),
    current_user: Profile = Depends(get_current_user),
):
    started = time.perf_counter()
    try:
        return get_recommendation(
            db,
            current_user.id,
            style=style,
            refresh=refresh,
            exclude_ids=_parse_exclude_ids(exclude_ids),
        )
    finally:
        logger.info(
            "recommendation_request duration_ms=%.2f user_id=%s style=%s refresh=%s",
            (time.perf_counter() - started) * 1000,
            current_user.id,
            style,
            refresh,
        )
