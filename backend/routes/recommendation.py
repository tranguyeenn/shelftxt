# backend/routes/recommendations.py

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from backend.db.database import get_db
from backend.services.recommendation import get_recommendation

router = APIRouter()


@router.get("/recommend")
async def recommend(
    style: str = Query(
        "balanced",
        description="Recommendation style: balanced, popular, or discovery",
    ),
    db: Session = Depends(get_db),
):
    return get_recommendation(db, style=style)