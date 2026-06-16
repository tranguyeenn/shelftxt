"""add book start and end dates

Revision ID: 9c2e1d4a8b77
Revises: 4f5a7c9c2d31
Create Date: 2026-06-16 00:00:01.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "9c2e1d4a8b77"
down_revision: Union[str, Sequence[str], None] = "4f5a7c9c2d31"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("books", sa.Column("start_date", sa.Date(), nullable=True))
    op.add_column("books", sa.Column("end_date", sa.Date(), nullable=True))


def downgrade() -> None:
    op.drop_column("books", "end_date")
    op.drop_column("books", "start_date")
