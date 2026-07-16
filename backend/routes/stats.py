from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from backend.auth.dependencies import get_current_user
from backend.db.database import get_db
from backend.db.models import Profile
from backend.schemas.stats import ReadingInsightsResponse
from backend.services.reading_insights import get_dashboard_summary, get_reading_insights

router = APIRouter()


@router.get("/stats/reading-insights", response_model=ReadingInsightsResponse)
def reading_insights(
    db: Session = Depends(get_db),
    current_user: Profile = Depends(get_current_user),
):
    return get_reading_insights(db, current_user.id)


@router.get("/dashboard/summary")
def dashboard_summary(
    db: Session = Depends(get_db),
    current_user: Profile = Depends(get_current_user),
):
    return get_dashboard_summary(db, current_user.id)
