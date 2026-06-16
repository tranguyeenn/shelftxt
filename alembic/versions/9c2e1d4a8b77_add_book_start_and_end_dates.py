"""add book start and end dates

Revision ID: 9c2e1d4a8b77
Revises: 4f5a7c9c2d31
Create Date: 2026-06-16 00:00:01.000000

"""
from typing import Sequence, Union

from alembic import op


revision: str = "9c2e1d4a8b77"
down_revision: Union[str, Sequence[str], None] = "4f5a7c9c2d31"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Nullable columns with no defaults avoid a table rewrite on PostgreSQL.
    # IF NOT EXISTS keeps deploys safe if Supabase was patched manually after
    # a Render timeout or if only one column was added before interruption.
    op.execute("ALTER TABLE books ADD COLUMN IF NOT EXISTS start_date DATE")
    op.execute("ALTER TABLE books ADD COLUMN IF NOT EXISTS end_date DATE")


def downgrade() -> None:
    op.execute("ALTER TABLE books DROP COLUMN IF EXISTS end_date")
    op.execute("ALTER TABLE books DROP COLUMN IF EXISTS start_date")
