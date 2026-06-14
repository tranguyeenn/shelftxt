from datetime import date

from sqlalchemy import Date, Float, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from backend.db.database import Base


class Book(Base):
    __tablename__ = "books"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True, index=True)

    title: Mapped[str] = mapped_column(String, nullable=False)
    authors: Mapped[str] = mapped_column(String, nullable=False)
    isbn_uid: Mapped[str] = mapped_column(String, nullable=False, unique=True, index=True)

    read_status: Mapped[str | None] = mapped_column(String, nullable=True)
    star_rating: Mapped[float | None] = mapped_column(Float, nullable=True)
    last_date_read: Mapped[date | None] = mapped_column(Date, nullable=True)

    progress_percent: Mapped[float | None] = mapped_column(Float, nullable=True)
    pages_read: Mapped[int | None] = mapped_column(Integer, nullable=True)
    total_pages: Mapped[int | None] = mapped_column(Integer, nullable=True)
