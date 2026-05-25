# backend/routes/recommendations.py

from fastapi import APIRouter
from backend.services.recommendation import get_recommendation

router = APIRouter()


@router.get("/recommend")
async def recommend():
    return get_recommendation()