import importlib.util
from pathlib import Path
from uuid import uuid4

import sqlalchemy as sa
from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import inspect


def test_reading_activity_migration_upgrade_and_downgrade(monkeypatch):
    migration_path = Path("alembic/versions/0f4d2a7c9b11_add_reading_activity.py")
    spec = importlib.util.spec_from_file_location("reading_activity_migration", migration_path)
    assert spec is not None and spec.loader is not None
    migration = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(migration)
    engine = sa.create_engine("sqlite://")

    with engine.begin() as connection:
        connection.execute(
            sa.text(
                """
                CREATE TABLE profiles (
                    id CHAR(32) PRIMARY KEY,
                    email VARCHAR(255) NOT NULL,
                    username VARCHAR(80) NOT NULL
                )
                """
            )
        )
        connection.execute(
            sa.text(
                """
                CREATE TABLE books (
                    id INTEGER PRIMARY KEY,
                    title VARCHAR NOT NULL,
                    authors VARCHAR NOT NULL,
                    isbn_uid VARCHAR NOT NULL,
                    user_id CHAR(32),
                    FOREIGN KEY(user_id) REFERENCES profiles (id)
                )
                """
            )
        )

        operations = Operations(MigrationContext.configure(connection))
        monkeypatch.setattr(migration, "op", operations)

        migration.upgrade()

        inspector = inspect(connection)
        assert "reading_activity" in inspector.get_table_names()
        columns = {column["name"]: column for column in inspector.get_columns("reading_activity")}
        assert set(columns) == {
            "id",
            "user_id",
            "book_id",
            "activity_type",
            "occurred_at",
            "pages_read_delta",
            "progress_delta",
            "metadata",
        }
        assert columns["activity_type"]["nullable"] is False
        assert columns["occurred_at"]["nullable"] is False
        indexes = {index["name"]: index["column_names"] for index in inspector.get_indexes("reading_activity")}
        assert indexes["ix_reading_activity_user_id"] == ["user_id"]
        assert indexes["ix_reading_activity_occurred_at"] == ["occurred_at"]
        assert indexes["ix_reading_activity_user_id_occurred_at"] == ["user_id", "occurred_at"]
        foreign_keys = {
            tuple(foreign_key["constrained_columns"]): foreign_key["referred_table"]
            for foreign_key in inspector.get_foreign_keys("reading_activity")
        }
        assert foreign_keys[("user_id",)] == "profiles"
        assert foreign_keys[("book_id",)] == "books"

        connection.execute(
            sa.text(
                """
                INSERT INTO reading_activity
                    (user_id, activity_type, pages_read_delta, progress_delta)
                VALUES
                    (:user_id, 'progress', 12, 5)
                """
            ),
            {"user_id": uuid4().hex},
        )

        migration.downgrade()

        assert "reading_activity" not in inspect(connection).get_table_names()
