"""dedupe recommendation feedback by identity and action

Revision ID: 7c2d1a9e4b33
Revises: 06df780d0799
Create Date: 2026-07-15 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "7c2d1a9e4b33"
down_revision: Union[str, Sequence[str], None] = "06df780d0799"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("recommendation_feedback", sa.Column("source", sa.String(length=64), nullable=True))
    op.add_column("recommendation_feedback", sa.Column("cluster_id", sa.String(length=128), nullable=True))
    op.execute(
        """
        DELETE FROM recommendation_feedback
        WHERE id IN (
            SELECT id FROM (
                SELECT
                    id,
                    row_number() OVER (
                        PARTITION BY user_id, recommendation_identity, feedback_type
                        ORDER BY created_at DESC, id DESC
                    ) AS duplicate_rank
                FROM recommendation_feedback
            ) ranked_duplicates
            WHERE duplicate_rank > 1
        )
        """
    )
    op.create_unique_constraint(
        "uq_recommendation_feedback_user_identity_action",
        "recommendation_feedback",
        ["user_id", "recommendation_identity", "feedback_type"],
    )


def downgrade() -> None:
    op.drop_constraint(
        "uq_recommendation_feedback_user_identity_action",
        "recommendation_feedback",
        type_="unique",
    )
    op.drop_column("recommendation_feedback", "cluster_id")
    op.drop_column("recommendation_feedback", "source")
