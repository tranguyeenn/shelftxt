"""add tracking mode and reading dates

Revision ID: e5a9c7d2b4f0
Revises: 7b9d4f1c2a30
Create Date: 2026-06-19 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op


revision: str = "e5a9c7d2b4f0"
down_revision: Union[str, Sequence[str], None] = "7b9d4f1c2a30"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # start_date/end_date already exist in revision 9c2e1d4a8b77. Keeping
    # these idempotent statements makes the migration safe for databases that
    # were manually patched or partially migrated before tracking_mode shipped.
    op.execute("ALTER TABLE books ADD COLUMN IF NOT EXISTS start_date DATE")
    op.execute("ALTER TABLE books ADD COLUMN IF NOT EXISTS end_date DATE")
    op.execute("ALTER TABLE books ADD COLUMN IF NOT EXISTS tracking_mode VARCHAR(20)")
    op.execute(
        """
        UPDATE books
        SET tracking_mode = CASE
            WHEN total_pages IS NOT NULL THEN 'pages'
            ELSE 'percentage'
        END
        WHERE tracking_mode IS NULL
        """
    )


def downgrade() -> None:
    op.execute("ALTER TABLE books DROP COLUMN IF EXISTS tracking_mode")
