# backend/routes/recommendations.py

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from backend.auth.dependencies import get_current_user
from backend.db.database import get_db
from backend.db.models import Profile
from backend.services.recommendation import get_recommendation

router = APIRouter()


def _parse_exclude_ids(raw: str | None) -> set[str]:
    if not raw:
        return set()
    return {value.strip() for value in raw.split(",") if value.strip()}


@router.get("/recommend")
async def recommend(
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
    return get_recommendation(
        db,
        current_user.id,
        style=style,
        refresh=refresh,
        exclude_ids=_parse_exclude_ids(exclude_ids),
    )
