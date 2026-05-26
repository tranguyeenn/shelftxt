# backend/routes/recommendations.py

from fastapi import APIRouter
from backend.services.recommendation import get_recommendation, invalidate_recommendation_cache

router = APIRouter()


@router.get("/recommend")
async def recommend():
    return get_recommendation()


@router.post("/recommend/refresh")
async def refresh_recommendation():
    invalidate_recommendation_cache()
    return {"status": "recommendation cache cleared"}