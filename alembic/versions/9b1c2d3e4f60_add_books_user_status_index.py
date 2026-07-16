"""add books user status index

Revision ID: 9b1c2d3e4f60
Revises: 8f2e4c6a9b10
Create Date: 2026-07-16 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op


revision: str = "9b1c2d3e4f60"
down_revision: Union[str, Sequence[str], None] = "8f2e4c6a9b10"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS ix_books_user_status
        ON books(user_id, read_status);
        """
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_books_user_status;")
