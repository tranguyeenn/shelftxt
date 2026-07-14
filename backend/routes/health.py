import logging

from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy import inspect, text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from backend.db.database import get_db

logger = logging.getLogger(__name__)

router = APIRouter()
REQUIRED_TABLES = frozenset({"profiles", "books", "metadata_jobs", "reading_activity"})


def missing_required_tables(db: Session) -> list[str]:
    inspector = inspect(db.get_bind())
    existing = set(inspector.get_table_names())
    return sorted(REQUIRED_TABLES - existing)


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
        missing_tables = missing_required_tables(db)
    except SQLAlchemyError as exc:
        logger.exception("readiness_check_failed")
        raise HTTPException(
            status_code=503,
            detail="Database unavailable",
        ) from exc
    if missing_tables:
        logger.error("readiness_schema_check_failed missing_tables=%s", missing_tables)
        raise HTTPException(
            status_code=503,
            detail=f"Database schema unavailable: missing tables {', '.join(missing_tables)}",
        )

    return {
        "status": "ready",
        "service": "ShelfTxt",
    }
