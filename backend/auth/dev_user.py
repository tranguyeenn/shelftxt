from uuid import UUID

from sqlalchemy.orm import Session

from backend.db.models import Profile

DEV_USER_ID = UUID("00000000-0000-0000-0000-000000000001")


def get_or_create_dev_user(db: Session) -> UUID:
    profile = db.query(Profile).filter(Profile.id == DEV_USER_ID).first()

    if profile is None:
        profile = Profile(
            id=DEV_USER_ID,
            email="dev@shelftxt.local",
            username="dev",
        )
        db.add(profile)
        db.commit()
        db.refresh(profile)

    return profile.id