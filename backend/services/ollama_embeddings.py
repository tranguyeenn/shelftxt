from __future__ import annotations

import hashlib
import math
import re
from dataclasses import dataclass
from uuid import uuid4

import httpx
from sqlalchemy import bindparam, text
from sqlalchemy.orm import Session

from backend.db.models import Book
from backend.env import (
    OLLAMA_EMBEDDING_DIMENSION,
    ollama_base_url,
    ollama_embedding_model,
    ollama_timeout_seconds,
)
from backend.services.recommendation_identity import recommendation_identity
from backend.services.status import normalize_status

EXPECTED_EMBEDDING_DIMENSION = OLLAMA_EMBEDDING_DIMENSION
SEMANTIC_WEIGHT = 0.25


class OllamaEmbeddingError(RuntimeError):
    pass


def canonical_embedding_model(model: str) -> str:
    normalized = str(model or "").strip()
    if not normalized:
        return "embeddinggemma:latest"
    return normalized if ":" in normalized else f"{normalized}:latest"


def normalize_embedding_source_text(text: str) -> str:
    return re.sub(r"\s+", " ", str(text or "")).strip()


def book_source_text(
    *,
    title: object,
    author: object = None,
    description: object = None,
    genres: object = None,
    subjects: object = None,
    series_name: object = None,
    series_position: object = None,
) -> str:
    lines: list[str] = []
    fields = [
        ("Title", title),
        ("Author", author),
        ("Description", description),
        ("Genres", _join_values(genres)),
        ("Subjects", _join_values(subjects)),
        ("Series", series_name),
        ("Series position", series_position),
    ]
    for label, value in fields:
        clean = normalize_embedding_source_text(str(value or ""))
        if clean:
            lines.append(f"{label}: {clean}")
    return normalize_embedding_source_text("\n".join(lines))


def book_source_text_from_book(book: Book) -> str:
    metadata = book.book_metadata if isinstance(book.book_metadata, dict) else {}
    series = metadata.get("series") if isinstance(metadata.get("series"), dict) else {}
    return book_source_text(
        title=book.title,
        author=book.authors,
        description=book.description,
        genres=book.genres,
        subjects=book.subjects,
        series_name=series.get("series_name"),
        series_position=series.get("series_position"),
    )


def book_source_text_from_row(row: dict) -> str:
    return book_source_text(
        title=row.get("Title") or row.get("title"),
        author=row.get("Authors") or row.get("author"),
        description=row.get("Description") or row.get("description"),
        genres=row.get("Genres") or row.get("genres"),
        subjects=row.get("Subjects") or row.get("subjects"),
        series_name=row.get("Series Name") or row.get("series_name"),
        series_position=row.get("Series Position") or row.get("series_position"),
    )


def embedding_content_hash(embedding_model: str, normalized_source_text: str) -> str:
    payload = f"{canonical_embedding_model(embedding_model)}\n{normalize_embedding_source_text(normalized_source_text)}"
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def canonical_identity_for_book(book: Book) -> str:
    return recommendation_identity(
        work_id=book.work_key,
        isbn=book.isbn_uid,
        title=book.title,
        author=book.authors,
    )


def canonical_identity_for_recommendation(item: dict) -> str:
    book = item.get("recommended_book") or item.get("book") or item
    return recommendation_identity(
        work_id=book.get("work_id") or item.get("work_id"),
        isbn=book.get("isbn") or item.get("isbn"),
        title=book.get("title") or item.get("title"),
        author=book.get("author") or item.get("author"),
    )


def _join_values(value: object) -> str | None:
    if isinstance(value, (list, tuple, set)):
        clean = [normalize_embedding_source_text(str(item)) for item in value if normalize_embedding_source_text(str(item))]
        return ", ".join(clean) if clean else None
    return str(value) if value else None


def _validate_vectors(vectors: object, expected_count: int, expected_dimension: int) -> list[list[float]]:
    if not isinstance(vectors, list):
        raise OllamaEmbeddingError("Ollama response did not include an embeddings list")
    if len(vectors) != expected_count:
        raise OllamaEmbeddingError(
            f"Ollama returned {len(vectors)} embeddings for {expected_count} inputs"
        )
    validated: list[list[float]] = []
    for index, vector in enumerate(vectors):
        if not isinstance(vector, list) or not vector:
            raise OllamaEmbeddingError(f"Ollama embedding {index} is empty or not a list")
        if len(vector) != expected_dimension:
            raise OllamaEmbeddingError(
                f"Ollama embedding {index} has dimension {len(vector)}, expected {expected_dimension}"
            )
        clean_vector: list[float] = []
        for value in vector:
            if not isinstance(value, (int, float)) or isinstance(value, bool) or not math.isfinite(float(value)):
                raise OllamaEmbeddingError(f"Ollama embedding {index} contains a non-numeric value")
            clean_vector.append(float(value))
        validated.append(clean_vector)
    return validated


class OllamaEmbeddingClient:
    def __init__(
        self,
        *,
        base_url: str | None = None,
        model: str | None = None,
        timeout_seconds: float | None = None,
        expected_dimension: int = EXPECTED_EMBEDDING_DIMENSION,
    ) -> None:
        self.base_url = (base_url or ollama_base_url()).rstrip("/")
        self.model = model or ollama_embedding_model()
        self.embedding_model = canonical_embedding_model(self.model)
        self.timeout = httpx.Timeout(timeout_seconds or ollama_timeout_seconds())
        self.expected_dimension = expected_dimension

    async def healthcheck(self) -> bool:
        try:
            await self.embed("healthcheck")
        except Exception:
            return False
        return True

    async def embed(self, text_value: str) -> list[float]:
        return (await self.embed_many([text_value]))[0]

    async def embed_many(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        normalized = [normalize_embedding_source_text(value) for value in texts]
        if any(not value for value in normalized):
            raise OllamaEmbeddingError("Cannot embed empty text")
        payload = {"model": self.model, "input": normalized}
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.post(f"{self.base_url}/api/embed", json=payload)
                response.raise_for_status()
                data = response.json()
        except httpx.HTTPError as exc:
            raise OllamaEmbeddingError(f"Ollama embedding request failed: {exc}") from exc
        except ValueError as exc:
            raise OllamaEmbeddingError("Ollama embedding response was not valid JSON") from exc
        return _validate_vectors(data.get("embeddings"), len(normalized), self.expected_dimension)


@dataclass
class EmbeddingBackfillStats:
    scanned: int = 0
    created: int = 0
    reused: int = 0
    updated: int = 0
    failures: int = 0


def _vector_literal(vector: list[float]) -> str:
    return "[" + ",".join(f"{float(value):.12g}" for value in vector) + "]"


def _parse_vector(value: object) -> list[float]:
    if isinstance(value, list):
        return [float(item) for item in value]
    text_value = str(value or "").strip().strip("[]")
    if not text_value:
        return []
    return [float(item) for item in text_value.split(",")]


def stored_embedding_record(
    db: Session,
    canonical_identity: str,
    embedding_model: str,
) -> dict | None:
    embedding_model = canonical_embedding_model(embedding_model)
    row = db.execute(
        text(
            """
            SELECT id, canonical_identity, book_id, title, author, embedding::text AS embedding,
                   embedding_model, content_hash
            FROM book_embeddings
            WHERE canonical_identity = :canonical_identity
              AND embedding_model = :embedding_model
            LIMIT 1
            """
        ),
        {"canonical_identity": canonical_identity, "embedding_model": embedding_model},
    ).mappings().first()
    return dict(row) if row else None


def upsert_embedding_record(
    db: Session,
    *,
    canonical_identity: str,
    book_id: int | None,
    title: str,
    author: str | None,
    embedding: list[float],
    embedding_model: str,
    content_hash: str,
    source_text: str | None,
    metadata_source: str | None,
) -> None:
    embedding_model = canonical_embedding_model(embedding_model)
    if len(embedding) != EXPECTED_EMBEDDING_DIMENSION:
        raise OllamaEmbeddingError(
            f"Embedding dimension {len(embedding)} does not match {EXPECTED_EMBEDDING_DIMENSION}"
        )
    db.execute(
        text(
            """
            INSERT INTO book_embeddings (
                id, canonical_identity, book_id, title, author, embedding,
                embedding_model, content_hash, source_text, metadata_source, created_at, updated_at
            )
            VALUES (
                :id, :canonical_identity, :book_id, :title, :author, CAST(:embedding AS vector),
                :embedding_model, :content_hash, :source_text, :metadata_source, now(), now()
            )
            ON CONFLICT (canonical_identity, embedding_model)
            DO UPDATE SET
                book_id = EXCLUDED.book_id,
                title = EXCLUDED.title,
                author = EXCLUDED.author,
                embedding = EXCLUDED.embedding,
                content_hash = EXCLUDED.content_hash,
                source_text = EXCLUDED.source_text,
                metadata_source = EXCLUDED.metadata_source,
                updated_at = now()
            """
        ),
        {
            "id": str(uuid4()),
            "canonical_identity": canonical_identity,
            "book_id": book_id,
            "title": title,
            "author": author,
            "embedding": _vector_literal(embedding),
            "embedding_model": embedding_model,
            "content_hash": content_hash,
            "source_text": source_text,
            "metadata_source": metadata_source,
        },
    )


async def ensure_book_embeddings(
    db: Session,
    books: list[Book],
    *,
    client: OllamaEmbeddingClient,
    force: bool = False,
) -> EmbeddingBackfillStats:
    stats = EmbeddingBackfillStats(scanned=len(books))
    pending: list[tuple[Book, str, str, str, bool]] = []
    for book in books:
        source_text = book_source_text_from_book(book)
        content_hash = embedding_content_hash(client.embedding_model, source_text)
        identity = canonical_identity_for_book(book)
        existing = stored_embedding_record(db, identity, client.embedding_model)
        if existing and existing.get("content_hash") == content_hash and not force:
            stats.reused += 1
            continue
        pending.append((book, identity, source_text, content_hash, bool(existing)))

    batch_size = 16
    for offset in range(0, len(pending), batch_size):
        batch = pending[offset : offset + batch_size]
        try:
            vectors = await client.embed_many([item[2] for item in batch])
        except Exception:
            stats.failures += len(batch)
            continue
        for (book, identity, source_text, content_hash, existed), vector in zip(batch, vectors, strict=True):
            try:
                upsert_embedding_record(
                    db,
                    canonical_identity=identity,
                    book_id=book.id,
                    title=book.title,
                    author=book.authors,
                    embedding=vector,
                    embedding_model=client.embedding_model,
                    content_hash=content_hash,
                    source_text=source_text,
                    metadata_source=book.metadata_source,
                )
                if existed:
                    stats.updated += 1
                else:
                    stats.created += 1
            except Exception:
                stats.failures += 1
        db.commit()
    return stats


def positive_book_weight(book: Book) -> float:
    status = normalize_status(
        book.read_status,
        progress_percent=float(book.progress_percent or 0),
        pages_read=int(book.pages_read or 0),
    )
    rating = float(book.star_rating or 0)
    if status == "dnf" or (0 < rating <= 2.0):
        return 0.0
    if status == "completed":
        if rating >= 5:
            return 1.0
        if rating >= 4:
            return 0.8
        if rating >= 3:
            return 0.3
    if status == "reading":
        return 0.4
    if status == "not_started":
        return 0.1
    return 0.0


def weighted_average(vectors: list[list[float]], weights: list[float]) -> list[float] | None:
    if not vectors or not weights or len(vectors) != len(weights):
        return None
    dimension = len(vectors[0])
    totals = [0.0] * dimension
    total_weight = 0.0
    for vector, weight in zip(vectors, weights, strict=True):
        if len(vector) != dimension or weight <= 0:
            continue
        total_weight += weight
        for index, value in enumerate(vector):
            totals[index] += float(value) * weight
    if total_weight <= 0:
        return None
    return [value / total_weight for value in totals]


def normalize_vector(vector: list[float]) -> list[float] | None:
    magnitude = math.sqrt(sum(value * value for value in vector))
    if magnitude <= 0:
        return None
    return [value / magnitude for value in vector]


def user_taste_vector(db: Session, books: list[Book], embedding_model: str) -> list[float] | None:
    embedding_model = canonical_embedding_model(embedding_model)
    weighted_books = [(book, positive_book_weight(book)) for book in books]
    identities = [canonical_identity_for_book(book) for book, weight in weighted_books if weight > 0]
    if not identities:
        return None
    rows = db.execute(
        text(
            """
            SELECT canonical_identity, embedding::text AS embedding
            FROM book_embeddings
            WHERE embedding_model = :embedding_model
              AND canonical_identity IN :identities
            """
        ).bindparams(bindparam("identities", expanding=True)),
        {"embedding_model": embedding_model, "identities": identities},
    ).mappings().all()
    by_identity = {row["canonical_identity"]: _parse_vector(row["embedding"]) for row in rows}
    vectors: list[list[float]] = []
    weights: list[float] = []
    for book, weight in weighted_books:
        vector = by_identity.get(canonical_identity_for_book(book))
        if weight > 0 and vector:
            vectors.append(vector)
            weights.append(weight)
    averaged = weighted_average(vectors, weights)
    return normalize_vector(averaged) if averaged else None


def recommendation_similarities(
    db: Session,
    recommendations: list[dict],
    *,
    user_vector: list[float],
    embedding_model: str,
) -> dict[str, float]:
    embedding_model = canonical_embedding_model(embedding_model)
    identities = [canonical_identity_for_recommendation(item) for item in recommendations]
    if not identities:
        return {}
    rows = db.execute(
        text(
            """
            SELECT canonical_identity, 1 - (embedding <=> CAST(:user_vector AS vector)) AS similarity
            FROM book_embeddings
            WHERE embedding_model = :embedding_model
              AND canonical_identity IN :identities
            """
        ).bindparams(bindparam("identities", expanding=True)),
        {
            "embedding_model": embedding_model,
            "identities": identities,
            "user_vector": _vector_literal(user_vector),
        },
    ).mappings().all()
    return {
        str(row["canonical_identity"]): float(row["similarity"])
        for row in rows
        if row["similarity"] is not None
    }


def rerank_with_semantics(
    db: Session,
    recommendations: list[dict],
    *,
    library_books: list[Book],
    embedding_model: str,
    debug: bool = False,
) -> list[dict]:
    embedding_model = canonical_embedding_model(embedding_model)
    if not recommendations:
        return recommendations
    taste_vector = user_taste_vector(db, library_books, embedding_model)
    if not taste_vector:
        for item in recommendations:
            item["semantic_available"] = False
        return recommendations
    similarities = recommendation_similarities(
        db,
        recommendations,
        user_vector=taste_vector,
        embedding_model=embedding_model,
    )
    reranked: list[dict] = []
    for index, item in enumerate(recommendations):
        identity = canonical_identity_for_recommendation(item)
        existing_score = float(item.get("score") or item.get("match_score") or 0.0)
        similarity = similarities.get(identity)
        semantic_available = similarity is not None
        final_score = existing_score
        if semantic_available:
            normalized_similarity = min(1.0, max(0.0, float(similarity)))
            final_score = (existing_score * (1.0 - SEMANTIC_WEIGHT)) + (normalized_similarity * SEMANTIC_WEIGHT)
            item["score"] = round(final_score, 4)
            item["match_score"] = round(final_score, 4)
            if isinstance(item.get("score_breakdown"), dict):
                item["score_breakdown"]["overall"] = round(final_score, 4)
        item["semantic_similarity"] = round(float(similarity), 4) if similarity is not None else None
        item["semantic_model"] = embedding_model if semantic_available else None
        item["semantic_available"] = semantic_available
        if debug:
            item["semantic_diagnostics"] = {
                "existing_score": round(existing_score, 4),
                "semantic_similarity": item["semantic_similarity"],
                "semantic_weight": SEMANTIC_WEIGHT if semantic_available else 0.0,
                "final_score": round(final_score, 4),
            }
        reranked.append({**item, "_semantic_original_rank": index})
    reranked.sort(key=lambda item: (float(item.get("score") or 0.0), -int(item["_semantic_original_rank"])), reverse=True)
    for item in reranked:
        item.pop("_semantic_original_rank", None)
    return reranked


def embedding_status(db: Session, *, client: OllamaEmbeddingClient, enabled: bool) -> dict:
    embedding_model = canonical_embedding_model(client.embedding_model)
    counts = db.execute(
        text(
            """
            SELECT
                count(*) AS stored_embedding_count,
                count(*) FILTER (WHERE book_id IS NOT NULL) AS library_embedding_count,
                count(*) FILTER (WHERE book_id IS NULL) AS external_embedding_count
            FROM book_embeddings
            WHERE embedding_model = :embedding_model
            """
        ),
        {"embedding_model": embedding_model},
    ).mappings().first()
    return {
        "enabled": enabled,
        "model": embedding_model,
        "expected_dimension": client.expected_dimension,
        "stored_embedding_count": int(counts["stored_embedding_count"] or 0) if counts else 0,
        "library_embedding_count": int(counts["library_embedding_count"] or 0) if counts else 0,
        "external_embedding_count": int(counts["external_embedding_count"] or 0) if counts else 0,
    }
