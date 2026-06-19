from datetime import date, datetime, timezone
from uuid import UUID

from sqlalchemy import Boolean, Date, DateTime, Float, ForeignKey, Integer, JSON, String, Text, UniqueConstraint, Uuid, false, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.db.database import Base

JSON_LIST = JSON().with_variant(JSONB, "postgresql")


class Profile(Base):
    __tablename__ = "profiles"

    id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        primary_key=True,
    )

    email: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        unique=True,
        index=True,
    )

    username: Mapped[str] = mapped_column(
        String(80),
        nullable=False,
        unique=True,
        index=True,
    )

    display_name: Mapped[str | None] = mapped_column(
        String(120),
        nullable=True,
    )

    bio: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )

    reading_goal: Mapped[int | None] = mapped_column(
        Integer,
        nullable=True,
    )

    avatar_url: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )

    favorite_genres: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        server_default=func.now(),
        nullable=False,
    )

    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        server_default=func.now(),
        nullable=False,
    )

    books: Mapped[list["Book"]] = relationship(
        "Book",
        back_populates="owner",
        cascade="all, delete-orphan",
    )


class Book(Base):
    __tablename__ = "books"

    __table_args__ = (
        UniqueConstraint("user_id", "isbn_uid", name="uq_books_user_id_isbn_uid"),
    )

    id: Mapped[int] = mapped_column(
        Integer,
        primary_key=True,
        autoincrement=True,
        index=True,
    )

    title: Mapped[str] = mapped_column(
        String,
        nullable=False,
    )

    authors: Mapped[str] = mapped_column(
        String,
        nullable=False,
    )

    isbn_uid: Mapped[str] = mapped_column(
        String,
        nullable=False,
        index=True,
    )

    user_id: Mapped[UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("profiles.id"),
        nullable=True,
        index=True,
    )

    owner: Mapped[Profile | None] = relationship(
        "Profile",
        back_populates="books",
    )

    read_status: Mapped[str | None] = mapped_column(
        String,
        nullable=True,
    )

    star_rating: Mapped[float | None] = mapped_column(
        Float,
        nullable=True,
    )

    last_date_read: Mapped[date | None] = mapped_column(
        Date,
        nullable=True,
    )

    start_date: Mapped[date | None] = mapped_column(
        Date,
        nullable=True,
    )

    end_date: Mapped[date | None] = mapped_column(
        Date,
        nullable=True,
    )

    progress_percent: Mapped[float | None] = mapped_column(
        Float,
        nullable=True,
    )

    pages_read: Mapped[int | None] = mapped_column(
        Integer,
        nullable=True,
    )

    total_pages: Mapped[int | None] = mapped_column(
        Integer,
        nullable=True,
    )

    tracking_mode: Mapped[str | None] = mapped_column(
        String(20),
        nullable=True,
    )

    description: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )

    page_count_checked: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
        server_default=false(),
        nullable=False,
    )

    page_count_source: Mapped[str | None] = mapped_column(
        String,
        nullable=True,
    )

    subjects: Mapped[list[str] | None] = mapped_column(
        JSON_LIST,
        nullable=True,
    )

    genres: Mapped[list[str] | None] = mapped_column(
        JSON_LIST,
        nullable=True,
    )

    first_publish_year: Mapped[int | None] = mapped_column(
        Integer,
        nullable=True,
    )

    metadata_source: Mapped[str | None] = mapped_column(
        String,
        nullable=True,
    )

    metadata_enriched_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    language: Mapped[str | None] = mapped_column(
        String,
        nullable=True,
    )

    work_key: Mapped[str | None] = mapped_column(
        String,
        nullable=True,
    )

    edition_key: Mapped[str | None] = mapped_column(
        String,
        nullable=True,
    )


class MetadataJob(Base):
    __tablename__ = "metadata_jobs"

    id: Mapped[int] = mapped_column(
        Integer,
        primary_key=True,
        autoincrement=True,
    )

    user_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("profiles.id"),
        nullable=False,
        index=True,
    )

    status: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        default="pending",
    )

    processed_count: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
    )

    total_count: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
    )

    error_message: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        server_default=func.now(),
        nullable=False,
    )

    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        server_default=func.now(),
        nullable=False,
    )

    completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
