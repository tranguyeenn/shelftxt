"""repair recommendation feedback identity uniqueness

Revision ID: 8f2e4c6a9b10
Revises: 5a6b7c8d9e10
Create Date: 2026-07-16 08:30:00.000000

"""
from typing import Sequence, Union

from alembic import op


revision: str = "8f2e4c6a9b10"
down_revision: Union[str, Sequence[str], None] = "5a6b7c8d9e10"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


TABLE_NAME = "recommendation_feedback"
CONSTRAINT_NAME = "uq_recommendation_feedback_user_identity_action"


def upgrade() -> None:
    op.execute(
        f"""
        DO $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1
                FROM information_schema.columns
                WHERE table_schema = current_schema()
                  AND table_name = '{TABLE_NAME}'
                  AND column_name = 'source'
            ) THEN
                ALTER TABLE {TABLE_NAME}
                ADD COLUMN source VARCHAR(64);
            END IF;
        END $$;
        """
    )
    op.execute(
        f"""
        DO $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1
                FROM information_schema.columns
                WHERE table_schema = current_schema()
                  AND table_name = '{TABLE_NAME}'
                  AND column_name = 'cluster_id'
            ) THEN
                ALTER TABLE {TABLE_NAME}
                ADD COLUMN cluster_id VARCHAR(128);
            END IF;
        END $$;
        """
    )
    op.execute(
        f"""
        DELETE FROM {TABLE_NAME}
        WHERE id IN (
            SELECT id
            FROM (
                SELECT
                    id,
                    row_number() OVER (
                        PARTITION BY user_id, recommendation_identity, feedback_type
                        ORDER BY created_at DESC, id DESC
                    ) AS duplicate_rank
                FROM {TABLE_NAME}
            ) ranked_duplicates
            WHERE duplicate_rank > 1
        )
        """
    )
    op.execute(
        f"""
        DO $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1
                FROM pg_constraint constraint_info
                JOIN pg_class table_info
                  ON table_info.oid = constraint_info.conrelid
                JOIN pg_namespace namespace_info
                  ON namespace_info.oid = table_info.relnamespace
                WHERE namespace_info.nspname = current_schema()
                  AND table_info.relname = '{TABLE_NAME}'
                  AND constraint_info.contype = 'u'
                  AND ARRAY(
                      SELECT attribute_info.attname::text
                      FROM unnest(constraint_info.conkey) AS constrained_columns(attnum)
                      JOIN pg_attribute attribute_info
                        ON attribute_info.attrelid = constraint_info.conrelid
                       AND attribute_info.attnum = constrained_columns.attnum
                      ORDER BY attribute_info.attname
                  ) = ARRAY[
                      'feedback_type',
                      'recommendation_identity',
                      'user_id'
                  ]::text[]
            ) THEN
                ALTER TABLE {TABLE_NAME}
                ADD CONSTRAINT {CONSTRAINT_NAME}
                UNIQUE (user_id, recommendation_identity, feedback_type);
            END IF;
        END $$;
        """
    )


def downgrade() -> None:
    # Forward-only repair: the migration cannot safely determine whether the
    # repaired columns or equivalent unique constraint predated this revision.
    pass
