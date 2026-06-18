from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator


class ProfilePatch(BaseModel):
    display_name: str | None = Field(default=None, max_length=120)
    username: str | None = Field(default=None, min_length=1, max_length=80)
    bio: str | None = Field(default=None, max_length=1000)
    reading_goal: int | None = Field(default=None, ge=0, le=10000)
    avatar_url: str | None = Field(default=None, max_length=2048)
    favorite_genres: str | None = Field(default=None, max_length=500)

    @field_validator("display_name", "username", "bio", "avatar_url", "favorite_genres", mode="before")
    @classmethod
    def blank_to_none(cls, value):
        if value is None:
            return None
        text = str(value).strip()
        return text or None


class ProfileResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    email: str
    username: str
    display_name: str | None = None
    bio: str | None = None
    reading_goal: int | None = None
    avatar_url: str | None = None
    favorite_genres: str | None = None
