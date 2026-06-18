"""add profile personalization fields

Revision ID: 7b9d4f1c2a30
Revises: d2f6a8b9c1e3
Create Date: 2026-06-18 09:00:00.000000
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "7b9d4f1c2a30"
down_revision: Union[str, None] = "d2f6a8b9c1e3"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("profiles", sa.Column("display_name", sa.String(length=120), nullable=True))
    op.add_column("profiles", sa.Column("bio", sa.Text(), nullable=True))
    op.add_column("profiles", sa.Column("reading_goal", sa.Integer(), nullable=True))
    op.add_column("profiles", sa.Column("avatar_url", sa.Text(), nullable=True))
    op.add_column("profiles", sa.Column("favorite_genres", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("profiles", "favorite_genres")
    op.drop_column("profiles", "avatar_url")
    op.drop_column("profiles", "reading_goal")
    op.drop_column("profiles", "bio")
    op.drop_column("profiles", "display_name")
