# backend/db/database.py

import os
import logging
from collections.abc import Generator
from pathlib import Path

from dotenv import load_dotenv
from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

ROOT_DIR = Path(__file__).resolve().parents[2]
ENV_PATH = ROOT_DIR / ".env"

load_dotenv(dotenv_path=ENV_PATH, override=False)

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

    if database_url.startswith("postgresql"):
        engine_kwargs.update(
            {
                "pool_recycle": 300,
                "pool_timeout": 10,
                "pool_size": int(os.getenv("DB_POOL_SIZE", "2")),
                "max_overflow": int(os.getenv("DB_MAX_OVERFLOW", "1")),
            }
        )

    if database_url.startswith("postgresql+psycopg"):
        # Supabase pooled/PgBouncer connections can reuse server connections across
        # clients, so psycopg prepared statement names may collide.
        engine_kwargs["connect_args"] = {
            "prepare_threshold": None,
            "connect_timeout": 10,
        }
    elif database_url.startswith("postgresql"):
        engine_kwargs["connect_args"] = {"connect_timeout": 10}

    return engine_kwargs


engine = None
SessionLocal = None


def get_engine():
    global engine

    if engine is None:
        database_url = get_database_url()
        engine = create_engine(database_url, **get_engine_kwargs(database_url))

    return engine


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
