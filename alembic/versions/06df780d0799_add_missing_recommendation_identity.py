"""add missing recommendation identity

Revision ID: 06df780d0799
Revises: 2f8b6d0a4c91
Create Date: 2026-07-15 12:24:19.981534
"""

from typing import Sequence, Union

from alembic import context, op
import sqlalchemy as sa


revision: str = "06df780d0799"
down_revision: Union[str, Sequence[str], None] = "2f8b6d0a4c91"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


TABLE_NAME = "recommendation_feedback"
COLUMN_NAME = "recommendation_identity"
INDEX_NAME = "ix_recommendation_feedback_recommendation_identity"


def _column_exists(column_name: str) -> bool:
    inspector = sa.inspect(op.get_bind())
    return any(
        column["name"] == column_name
        for column in inspector.get_columns(TABLE_NAME)
    )


def _index_exists(index_name: str) -> bool:
    inspector = sa.inspect(op.get_bind())
    return any(
        index["name"] == index_name
        for index in inspector.get_indexes(TABLE_NAME)
    )


def upgrade() -> None:
    if context.is_offline_mode():
        _populate_identity_values()
        op.alter_column(
            TABLE_NAME,
            COLUMN_NAME,
            existing_type=sa.String(length=512),
            nullable=False,
        )
        return

    # Older databases may genuinely lack the column.
    # Fresh databases may already have it from 2f8b6d0a4c91.
    if not _column_exists(COLUMN_NAME):
        op.add_column(
            TABLE_NAME,
            sa.Column(
                COLUMN_NAME,
                sa.String(length=512),
                nullable=True,
            ),
        )

    _populate_identity_values()

    if not _index_exists(INDEX_NAME):
        op.create_index(
            INDEX_NAME,
            TABLE_NAME,
            [COLUMN_NAME],
            unique=False,
        )

    op.alter_column(
        TABLE_NAME,
        COLUMN_NAME,
        existing_type=sa.String(length=512),
        nullable=False,
    )


def downgrade() -> None:
    if context.is_offline_mode():
        op.alter_column(
            TABLE_NAME,
            COLUMN_NAME,
            existing_type=sa.String(length=512),
            nullable=True,
        )
        return

    # This revision may not have created the column because it can already
    # exist from the parent revision. Do not drop a parent-owned column.
    if _index_exists(INDEX_NAME):
        op.drop_index(
            INDEX_NAME,
            table_name=TABLE_NAME,
        )

    if _column_exists(COLUMN_NAME):
        op.alter_column(
            TABLE_NAME,
            COLUMN_NAME,
            existing_type=sa.String(length=512),
            nullable=True,
        )


def _populate_identity_values() -> None:
    op.execute(
        """
        UPDATE recommendation_feedback
        SET recommendation_identity =
            CASE
                WHEN recommendation_id IS NOT NULL
                     AND recommendation_id <> ''
                    THEN recommendation_id
                WHEN work_id IS NOT NULL
                     AND work_id <> ''
                    THEN 'work:' || lower(trim(work_id))
                WHEN isbn IS NOT NULL
                     AND isbn <> ''
                    THEN 'isbn:' || regexp_replace(
                        isbn,
                        '[^0-9Xx]',
                        '',
                        'g'
                    )
                ELSE
                    'title_author:'
                    || lower(trim(coalesce(canonical_title, '')))
                    || ':'
                    || lower(trim(coalesce(canonical_author, '')))
            END
        WHERE recommendation_identity IS NULL
        """
    )
