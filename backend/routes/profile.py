from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from backend.auth.dependencies import get_current_user
from backend.db.database import get_db
from backend.db.models import Profile
from backend.schemas.profile import ProfilePatch, ProfileResponse

router = APIRouter()


@router.get("/profile/me", response_model=ProfileResponse)
def get_my_profile(current_user: Profile = Depends(get_current_user)):
    return current_user


@router.patch("/profile/me", response_model=ProfileResponse)
def update_my_profile(
    body: ProfilePatch,
    db: Session = Depends(get_db),
    current_user: Profile = Depends(get_current_user),
):
    if body.username is not None:
        current_user.username = body.username
    current_user.display_name = body.display_name
    current_user.bio = body.bio
    current_user.reading_goal = body.reading_goal
    current_user.avatar_url = body.avatar_url
    current_user.favorite_genres = body.favorite_genres

    try:
        db.add(current_user)
        db.commit()
        db.refresh(current_user)
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(
            status_code=409,
            detail="That username is already taken.",
        ) from exc

    return current_user
