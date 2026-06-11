from sqlalchemy import Float, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from backend.db.database import Base


class Book(Base):
    __tablename__ = "books"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)

    title: Mapped[str] = mapped_column(String, nullable=False)
    author: Mapped[str] = mapped_column(String, nullable=False)

    genre: Mapped[str | None] = mapped_column(String, nullable=True)
    status: Mapped[str | None] = mapped_column(String, nullable=True)

    rating: Mapped[float | None] = mapped_column(Float, nullable=True)
    pages: Mapped[int | None] = mapped_column(Integer, nullable=True)

    date_added: Mapped[str | None] = mapped_column(String, nullable=True)
    date_started: Mapped[str | None] = mapped_column(String, nullable=True)
    date_finished: Mapped[str | None] = mapped_column(String, nullable=True)