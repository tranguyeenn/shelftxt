# backend/routes/recommendations.py

from fastapi import APIRouter, Query

from backend.services.recommendation import get_recommendation

router = APIRouter()


@router.get("/recommend")
async def recommend(
    style: str = Query(
        "balanced",
        description="Recommendation style: balanced, popular, or discovery",
    ),
):
    return get_recommendation(style=style)