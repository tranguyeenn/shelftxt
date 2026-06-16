# backend/routes/recommendations.py

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from backend.auth.dependencies import get_current_user
from backend.db.database import get_db
from backend.db.models import Profile
from backend.services.recommendation import get_recommendation

router = APIRouter()


@router.get("/recommend")
async def recommend(
    style: str = Query(
        "balanced",
        description="Recommendation style: balanced, popular, or discovery",
    ),
    db: Session = Depends(get_db),
    current_user: Profile = Depends(get_current_user),
):
    return get_recommendation(db, current_user.id, style=style)