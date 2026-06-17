"""add recommendation metadata fields

Revision ID: c1b2d3e4f5a6
Revises: 9c2e1d4a8b77
Create Date: 2026-06-17 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "c1b2d3e4f5a6"
down_revision: Union[str, Sequence[str], None] = "9c2e1d4a8b77"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("books", sa.Column("description", sa.Text(), nullable=True))
    op.add_column("books", sa.Column("first_publish_year", sa.Integer(), nullable=True))
    op.add_column("books", sa.Column("metadata_source", sa.String(), nullable=True))
    op.add_column("books", sa.Column("metadata_enriched_at", sa.DateTime(timezone=True), nullable=True))

    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        op.alter_column(
            "books",
            "subjects",
            type_=postgresql.JSONB(),
            existing_type=sa.JSON(),
            postgresql_using="subjects::jsonb",
        )
        op.alter_column(
            "books",
            "genres",
            type_=postgresql.JSONB(),
            existing_type=sa.JSON(),
            postgresql_using="genres::jsonb",
        )


def downgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        op.alter_column(
            "books",
            "genres",
            type_=sa.JSON(),
            existing_type=postgresql.JSONB(),
            postgresql_using="genres::json",
        )
        op.alter_column(
            "books",
            "subjects",
            type_=sa.JSON(),
            existing_type=postgresql.JSONB(),
            postgresql_using="subjects::json",
        )

    op.drop_column("books", "metadata_enriched_at")
    op.drop_column("books", "metadata_source")
    op.drop_column("books", "first_publish_year")
    op.drop_column("books", "description")
