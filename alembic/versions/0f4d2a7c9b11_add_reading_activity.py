"""add reading activity

Revision ID: 0f4d2a7c9b11
Revises: 481e865803ec
Create Date: 2026-07-14 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "0f4d2a7c9b11"
down_revision: Union[str, Sequence[str], None] = "481e865803ec"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "reading_activity",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("book_id", sa.Integer(), nullable=True),
        sa.Column("activity_type", sa.String(length=32), nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("pages_read_delta", sa.Integer(), server_default="0", nullable=False),
        sa.Column("progress_delta", sa.Float(), server_default="0", nullable=False),
        sa.Column("metadata", sa.JSON().with_variant(postgresql.JSONB(), "postgresql"), nullable=True),
        sa.ForeignKeyConstraint(["book_id"], ["books.id"]),
        sa.ForeignKeyConstraint(["user_id"], ["profiles.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_reading_activity_book_id"), "reading_activity", ["book_id"], unique=False)
    op.create_index(op.f("ix_reading_activity_occurred_at"), "reading_activity", ["occurred_at"], unique=False)
    op.create_index(op.f("ix_reading_activity_user_id"), "reading_activity", ["user_id"], unique=False)
    op.create_index("ix_reading_activity_user_id_occurred_at", "reading_activity", ["user_id", "occurred_at"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_reading_activity_user_id_occurred_at", table_name="reading_activity")
    op.drop_index(op.f("ix_reading_activity_user_id"), table_name="reading_activity")
    op.drop_index(op.f("ix_reading_activity_occurred_at"), table_name="reading_activity")
    op.drop_index(op.f("ix_reading_activity_book_id"), table_name="reading_activity")
    op.drop_table("reading_activity")
