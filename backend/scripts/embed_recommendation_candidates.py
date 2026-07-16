from __future__ import annotations

import argparse
import asyncio
import sys
from uuid import UUID

from backend.db.database import get_session_local
from backend.repository.postgres_books_repository import get_books_for_recommendation
from backend.services.ollama_embeddings import (
    OllamaEmbeddingClient,
    book_source_text_from_row,
    embedding_content_hash,
    stored_embedding_record,
    upsert_embedding_record,
)
from backend.services.recommendation import MAX_RECOMMENDATION_BOOKS, get_recommendation
from backend.services.recommendation_discovery import discovery_candidate_rows
from backend.services.recommendation_identity import recommendation_identity


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Embed limited external recommendation candidates.")
    parser.add_argument("--user-id", required=True)
    parser.add_argument("--limit", type=int, default=50)
    parser.add_argument("--force", action="store_true")
    return parser.parse_args()


async def _run() -> int:
    args = _parse_args()
    user_id = UUID(args.user_id)
    client = OllamaEmbeddingClient()
    if not await client.healthcheck():
        print("Ollama available: no")
        return 1
    print("Ollama available: yes")
    print(f"Model: {client.embedding_model}")

    SessionLocal = get_session_local()
    db = SessionLocal()
    created = reused = updated = failures = 0
    try:
        books = get_books_for_recommendation(db, user_id, MAX_RECOMMENDATION_BOOKS)
        rows, diagnostics = discovery_candidate_rows(db, user_id, books, limit=args.limit, allow_external=True)
        pending = []
        for row in rows[: args.limit]:
            identity = recommendation_identity(
                work_id=row.get("External Work ID") or row.get("Work Key"),
                isbn=row.get("External ISBN") or row.get("ISBN/UID"),
                title=row.get("Title"),
                author=row.get("Authors"),
            )
            source_text = book_source_text_from_row(row)
            content_hash = embedding_content_hash(client.embedding_model, source_text)
            existing = stored_embedding_record(db, identity, client.embedding_model)
            if existing and existing.get("content_hash") == content_hash and not args.force:
                reused += 1
                continue
            pending.append((row, identity, source_text, content_hash, bool(existing)))

        for offset in range(0, len(pending), 16):
            batch = pending[offset : offset + 16]
            try:
                vectors = await client.embed_many([item[2] for item in batch])
            except Exception:
                failures += len(batch)
                continue
            for (row, identity, source_text, content_hash, existed), vector in zip(batch, vectors, strict=True):
                try:
                    upsert_embedding_record(
                        db,
                        canonical_identity=identity,
                        book_id=None,
                        title=str(row.get("Title") or "Untitled"),
                        author=str(row.get("Authors") or "") or None,
                        embedding=vector,
                        embedding_model=client.embedding_model,
                        content_hash=content_hash,
                        source_text=source_text,
                        metadata_source=str(row.get("Discovery Source") or "metadata_aggregation"),
                    )
                    updated += 1 if existed else 0
                    created += 0 if existed else 1
                except Exception:
                    failures += 1
            db.commit()

        recommendations = get_recommendation(db, user_id, top_n=10, refresh=True)
    finally:
        db.close()

    print(f"Candidates scanned: {len(rows)}")
    print(f"Embeddings created: {created}")
    print(f"Embeddings reused: {reused}")
    print(f"Embeddings updated: {updated}")
    print(f"Failures: {failures}")
    print(f"Discovery diagnostics: {diagnostics.to_dict()}")
    for item in recommendations:
        print(
            f"{item.get('title')} | outside_library={item.get('outside_library')} "
            f"existing_score={(item.get('semantic_diagnostics') or {}).get('existing_score', item.get('score'))} "
            f"semantic_similarity={item.get('semantic_similarity')} final_score={item.get('score')} "
            f"series={item.get('series_name')} position={item.get('series_position')}"
        )
    return 0


def main() -> None:
    sys.exit(asyncio.run(_run()))


if __name__ == "__main__":
    main()
