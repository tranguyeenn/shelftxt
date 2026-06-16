"""add open library metadata and page count checked

Revision ID: 4f5a7c9c2d31
Revises: ba60395bdc82
Create Date: 2026-06-16 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "4f5a7c9c2d31"
down_revision: Union[str, Sequence[str], None] = "ba60395bdc82"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "books",
        sa.Column("page_count_checked", sa.Boolean(), server_default=sa.false(), nullable=False),
    )
    op.add_column("books", sa.Column("page_count_source", sa.String(), nullable=True))
    op.add_column("books", sa.Column("subjects", sa.JSON(), nullable=True))
    op.add_column("books", sa.Column("genres", sa.JSON(), nullable=True))
    op.add_column("books", sa.Column("language", sa.String(), nullable=True))
    op.add_column("books", sa.Column("work_key", sa.String(), nullable=True))
    op.add_column("books", sa.Column("edition_key", sa.String(), nullable=True))


def downgrade() -> None:
    op.drop_column("books", "edition_key")
    op.drop_column("books", "work_key")
    op.drop_column("books", "language")
    op.drop_column("books", "genres")
    op.drop_column("books", "subjects")
    op.drop_column("books", "page_count_source")
    op.drop_column("books", "page_count_checked")
