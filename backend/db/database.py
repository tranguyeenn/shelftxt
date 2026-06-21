# backend/db/database.py

import os
import logging
from collections.abc import Generator

from sqlalchemy import event
from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from backend.env import ENV_PATH, load_backend_env

load_backend_env()

logger = logging.getLogger(__name__)


class Base(DeclarativeBase):
    pass


def get_database_url() -> str:
    database_url = os.getenv("DATABASE_URL")

    if not database_url:
        raise RuntimeError(
            f"DATABASE_URL is not set. Expected to load it from {ENV_PATH}"
        )

    return database_url


def get_engine_kwargs(database_url: str) -> dict:
    engine_kwargs = {"pool_pre_ping": True}
    statement_timeout_ms = os.getenv("DB_STATEMENT_TIMEOUT_MS", "8000")
    idle_timeout_ms = os.getenv("DB_IDLE_TRANSACTION_TIMEOUT_MS", "15000")
    postgres_options = (
        f"-c statement_timeout={statement_timeout_ms} "
        f"-c idle_in_transaction_session_timeout={idle_timeout_ms}"
    )

    if database_url.startswith("postgresql"):
        engine_kwargs.update(
            {
                "pool_recycle": 300,
                "pool_timeout": 10,
                "pool_size": int(os.getenv("DB_POOL_SIZE", "2")),
                "max_overflow": int(os.getenv("DB_MAX_OVERFLOW", "1")),
                "pool_use_lifo": True,
            }
        )

    if database_url.startswith("postgresql+psycopg"):
        # Supabase pooled/PgBouncer connections can reuse server connections across
        # clients, so psycopg prepared statement names may collide.
        engine_kwargs["connect_args"] = {
            "prepare_threshold": None,
            "connect_timeout": 10,
            "options": postgres_options,
        }
    elif database_url.startswith("postgresql"):
        engine_kwargs["connect_args"] = {
            "connect_timeout": 10,
            "options": postgres_options,
        }

    return engine_kwargs


engine = None
SessionLocal = None


def get_engine():
    global engine

    if engine is None:
        database_url = get_database_url()
        engine = create_engine(database_url, **get_engine_kwargs(database_url))
        if database_url.startswith("postgresql"):
            _register_pool_logging(engine)

    return engine


def _register_pool_logging(engine_to_register) -> None:
    @event.listens_for(engine_to_register, "checkout")
    def _checkout(dbapi_connection, connection_record, connection_proxy):
        logger.debug("db_pool_checkout connection_id=%s", id(dbapi_connection))

    @event.listens_for(engine_to_register, "checkin")
    def _checkin(dbapi_connection, connection_record):
        logger.debug("db_pool_checkin connection_id=%s", id(dbapi_connection))


def get_session_local():
    global SessionLocal

    if SessionLocal is None:
        SessionLocal = sessionmaker(
            autocommit=False,
            autoflush=False,
            bind=get_engine(),
        )

    return SessionLocal


def get_db() -> Generator[Session, None, None]:
    logger.info("Creating DB session")
    db = get_session_local()()

    try:
        yield db
    finally:
        logger.info("Closing DB session")
        db.close()
