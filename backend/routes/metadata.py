from fastapi import APIRouter, BackgroundTasks, Depends
from sqlalchemy.orm import Session

from backend.auth.dependencies import get_current_user
from backend.db.database import get_db
from backend.db.models import Profile
from backend.schemas.metadata import MetadataStatusResponse
from backend.services.metadata_jobs import (
    create_metadata_job,
    get_metadata_status,
    process_metadata_job,
)

router = APIRouter()


@router.get("/metadata/status", response_model=MetadataStatusResponse)
async def metadata_status(
    db: Session = Depends(get_db),
    current_user: Profile = Depends(get_current_user),
):
    return get_metadata_status(db, current_user.id)


@router.post("/metadata/generate", response_model=MetadataStatusResponse)
async def generate_metadata(
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    current_user: Profile = Depends(get_current_user),
):
    job = create_metadata_job(db, current_user.id)
    if job.status in {"pending", "processing"}:
        background_tasks.add_task(process_metadata_job, job.id)
    return get_metadata_status(db, current_user.id)
