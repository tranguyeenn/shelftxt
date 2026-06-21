import logging

from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from backend.db.database import get_db

logger = logging.getLogger(__name__)

router = APIRouter()


@router.get("/health", operation_id="health_check")
async def health():
    return {
        "status": "healthy",
        "service": "ShelfTxt",
    }


@router.head("/health", include_in_schema=False)
async def health_head():
    return Response(status_code=200)


@router.get("/ready")
def ready(db: Session = Depends(get_db)):
    try:
        db.execute(text("SELECT 1"))
    except SQLAlchemyError as exc:
        logger.exception("readiness_check_failed")
        raise HTTPException(
            status_code=503,
            detail="Database unavailable",
        ) from exc

    return {
        "status": "ready",
        "service": "ShelfTxt",
    }
