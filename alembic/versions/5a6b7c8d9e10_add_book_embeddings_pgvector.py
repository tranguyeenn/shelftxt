"""add book embeddings pgvector table

Revision ID: 5a6b7c8d9e10
Revises: 7c2d1a9e4b33
Create Date: 2026-07-15 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "5a6b7c8d9e10"
down_revision: Union[str, Sequence[str], None] = "7c2d1a9e4b33"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")
    op.create_table(
        "book_embeddings",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("canonical_identity", sa.Text(), nullable=False),
        sa.Column("book_id", sa.Integer(), nullable=True),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("author", sa.Text(), nullable=True),
        sa.Column("embedding", sa.Text(), nullable=False),
        sa.Column("embedding_model", sa.Text(), nullable=False),
        sa.Column("content_hash", sa.Text(), nullable=False),
        sa.Column("source_text", sa.Text(), nullable=True),
        sa.Column("metadata_source", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["book_id"], ["books.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("canonical_identity", "embedding_model", name="uq_book_embeddings_identity_model"),
    )
    op.execute("ALTER TABLE book_embeddings ALTER COLUMN embedding TYPE vector(768) USING embedding::vector")
    op.create_index("ix_book_embeddings_book_id", "book_embeddings", ["book_id"], unique=False)
    op.create_index("ix_book_embeddings_canonical_identity", "book_embeddings", ["canonical_identity"], unique=False)
    op.create_index("ix_book_embeddings_embedding_model", "book_embeddings", ["embedding_model"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_book_embeddings_embedding_model", table_name="book_embeddings")
    op.drop_index("ix_book_embeddings_canonical_identity", table_name="book_embeddings")
    op.drop_index("ix_book_embeddings_book_id", table_name="book_embeddings")
    op.drop_table("book_embeddings")
