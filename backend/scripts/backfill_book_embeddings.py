from __future__ import annotations

import argparse
import asyncio
import sys

from backend.db.database import get_session_local
from backend.db.models import Book
from backend.env import ollama_enabled
from backend.services.ollama_embeddings import (
    EXPECTED_EMBEDDING_DIMENSION,
    OllamaEmbeddingClient,
    ensure_book_embeddings,
)


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Backfill ShelfTXT book embeddings with local Ollama.")
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--book-id", type=int, default=None)
    parser.add_argument("--external", action="store_true", help="Process external catalog books instead of user library books.")
    return parser.parse_args()


async def _run() -> int:
    args = _parse_args()
    client = OllamaEmbeddingClient()
    available = await client.healthcheck() if ollama_enabled() else False
    print(f"Ollama available: {'yes' if available else 'no'}")
    print(f"Model: {client.embedding_model}")
    print(f"Vector dimension: {EXPECTED_EMBEDDING_DIMENSION}")
    if not available:
        return 1

    SessionLocal = get_session_local()
    db = SessionLocal()
    try:
        query = db.query(Book)
        if args.book_id is not None:
            query = query.filter(Book.id == args.book_id)
        elif args.external:
            query = query.filter(Book.user_id.is_(None))
        else:
            query = query.filter(Book.user_id.is_not(None))
        query = query.order_by(Book.id.asc())
        if args.limit:
            query = query.limit(args.limit)
        books = query.all()
        stats = await ensure_book_embeddings(db, books, client=client, force=args.force)
    finally:
        db.close()

    print(f"Books scanned: {stats.scanned}")
    print(f"Embeddings created: {stats.created}")
    print(f"Embeddings reused: {stats.reused}")
    print(f"Embeddings updated: {stats.updated}")
    print(f"Failures: {stats.failures}")
    return 0


def main() -> None:
    sys.exit(asyncio.run(_run()))


if __name__ == "__main__":
    main()
