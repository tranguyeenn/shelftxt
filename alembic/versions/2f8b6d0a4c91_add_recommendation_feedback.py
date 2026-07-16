"""add recommendation feedback

Revision ID: 2f8b6d0a4c91
Revises: 0f4d2a7c9b11
Create Date: 2026-07-15 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "2f8b6d0a4c91"
down_revision: Union[str, Sequence[str], None] = "0f4d2a7c9b11"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


json_list = sa.JSON().with_variant(postgresql.JSONB(), "postgresql")
json_object = sa.JSON().with_variant(postgresql.JSONB(), "postgresql")


def upgrade() -> None:
    op.create_table(
        "recommendation_feedback",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("book_id", sa.Integer(), nullable=True),
        sa.Column("recommendation_id", sa.String(length=512), nullable=False),
        sa.Column("recommendation_identity", sa.String(length=512), nullable=False),
        sa.Column("work_id", sa.String(), nullable=True),
        sa.Column("isbn", sa.String(), nullable=True),
        sa.Column("canonical_title", sa.String(), nullable=True),
        sa.Column("canonical_author", sa.String(), nullable=True),
        sa.Column("feedback_type", sa.String(length=32), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("related_genres", json_list, nullable=True),
        sa.Column("related_authors", json_list, nullable=True),
        sa.Column("related_books", json_list, nullable=True),
        sa.Column("recommendation_score", sa.Float(), nullable=True),
        sa.Column("explanation", sa.Text(), nullable=True),
        sa.Column("inferred_trends", json_object, nullable=True),
        sa.ForeignKeyConstraint(["book_id"], ["books.id"]),
        sa.ForeignKeyConstraint(["user_id"], ["profiles.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_recommendation_feedback_book_id"), "recommendation_feedback", ["book_id"], unique=False)
    op.create_index(op.f("ix_recommendation_feedback_created_at"), "recommendation_feedback", ["created_at"], unique=False)
    op.create_index(op.f("ix_recommendation_feedback_expires_at"), "recommendation_feedback", ["expires_at"], unique=False)
    op.create_index(op.f("ix_recommendation_feedback_feedback_type"), "recommendation_feedback", ["feedback_type"], unique=False)
    op.create_index(op.f("ix_recommendation_feedback_isbn"), "recommendation_feedback", ["isbn"], unique=False)
    op.create_index(op.f("ix_recommendation_feedback_recommendation_id"), "recommendation_feedback", ["recommendation_id"], unique=False)
    op.create_index(op.f("ix_recommendation_feedback_recommendation_identity"), "recommendation_feedback", ["recommendation_identity"], unique=False)
    op.create_index(op.f("ix_recommendation_feedback_user_id"), "recommendation_feedback", ["user_id"], unique=False)
    op.create_index(op.f("ix_recommendation_feedback_work_id"), "recommendation_feedback", ["work_id"], unique=False)
    op.create_index("ix_recommendation_feedback_user_created", "recommendation_feedback", ["user_id", "created_at"], unique=False)
    op.create_index("ix_recommendation_feedback_user_expires", "recommendation_feedback", ["user_id", "expires_at"], unique=False)
    op.create_index("ix_recommendation_feedback_user_recommendation", "recommendation_feedback", ["user_id", "recommendation_id"], unique=False)
    op.create_index("ix_recommendation_feedback_user_work", "recommendation_feedback", ["user_id", "work_id"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_recommendation_feedback_user_work", table_name="recommendation_feedback")
    op.drop_index("ix_recommendation_feedback_user_recommendation", table_name="recommendation_feedback")
    op.drop_index("ix_recommendation_feedback_user_expires", table_name="recommendation_feedback")
    op.drop_index("ix_recommendation_feedback_user_created", table_name="recommendation_feedback")
    op.drop_index(op.f("ix_recommendation_feedback_work_id"), table_name="recommendation_feedback")
    op.drop_index(op.f("ix_recommendation_feedback_user_id"), table_name="recommendation_feedback")
    op.drop_index(op.f("ix_recommendation_feedback_recommendation_id"), table_name="recommendation_feedback")
    op.drop_index(op.f("ix_recommendation_feedback_recommendation_identity"), table_name="recommendation_feedback")
    op.drop_index(op.f("ix_recommendation_feedback_isbn"), table_name="recommendation_feedback")
    op.drop_index(op.f("ix_recommendation_feedback_feedback_type"), table_name="recommendation_feedback")
    op.drop_index(op.f("ix_recommendation_feedback_expires_at"), table_name="recommendation_feedback")
    op.drop_index(op.f("ix_recommendation_feedback_created_at"), table_name="recommendation_feedback")
    op.drop_index(op.f("ix_recommendation_feedback_book_id"), table_name="recommendation_feedback")
    op.drop_table("recommendation_feedback")
