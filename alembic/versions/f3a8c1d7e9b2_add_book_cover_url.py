"""add persistent book cover url

Revision ID: f3a8c1d7e9b2
Revises: e5a9c7d2b4f0
Create Date: 2026-06-30 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "f3a8c1d7e9b2"
down_revision: Union[str, Sequence[str], None] = "e5a9c7d2b4f0"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("books", sa.Column("cover_url", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("books", "cover_url")
