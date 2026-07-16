import asyncio
from unittest.mock import patch

import httpx
import pytest

from backend.services.ollama_embeddings import (
    EXPECTED_EMBEDDING_DIMENSION,
    OllamaEmbeddingClient,
    OllamaEmbeddingError,
    _validate_vectors,
    book_source_text,
    canonical_embedding_model,
    embedding_content_hash,
    ensure_recommendation_embeddings,
    normalize_vector,
    rerank_with_semantics,
    weighted_average,
)


def _vector(value: float) -> list[float]:
    return [value] * EXPECTED_EMBEDDING_DIMENSION


def test_source_text_construction_excludes_user_reaction_fields():
    text = book_source_text(
        title="  The Naturals ",
        author="Jennifer Lynn Barnes",
        description="Teen profilers\nsolve cases.",
        genres=["Young Adult", "Mystery", ""],
        subjects=["Criminal profiling", "serial killers"],
        series_name="The Naturals",
        series_position=1,
    )

    assert "Title: The Naturals" in text
    assert "Author: Jennifer Lynn Barnes" in text
    assert "Genres: Young Adult, Mystery" in text
    assert "Subjects: Criminal profiling, serial killers" in text
    assert "Series position: 1" in text
    assert "rating" not in text.lower()
    assert "\n" not in text


def test_content_hash_uses_model_and_normalized_source_text():
    first = embedding_content_hash("embeddinggemma", "Title: A\nDescription: B")
    second = embedding_content_hash("embeddinggemma", "Title: A Description: B")
    other_model = embedding_content_hash("other-model", "Title: A Description: B")

    assert first == second
    assert first != other_model


def test_embedding_model_alias_canonicalizes_latest_tag():
    assert canonical_embedding_model("embeddinggemma") == "embeddinggemma:latest"
    assert canonical_embedding_model("embeddinggemma:latest") == "embeddinggemma:latest"
    assert embedding_content_hash("embeddinggemma", "Title: A") == embedding_content_hash("embeddinggemma:latest", "Title: A")


def test_malformed_ollama_vectors_are_rejected():
    with pytest.raises(OllamaEmbeddingError):
        _validate_vectors([[1.0, 2.0]], 1, EXPECTED_EMBEDDING_DIMENSION)
    with pytest.raises(OllamaEmbeddingError):
        _validate_vectors([["bad"] * EXPECTED_EMBEDDING_DIMENSION], 1, EXPECTED_EMBEDDING_DIMENSION)
    with pytest.raises(OllamaEmbeddingError):
        _validate_vectors([_vector(0.1)], 2, EXPECTED_EMBEDDING_DIMENSION)


def test_ollama_client_rejects_response_without_embeddings():
    class FakeAsyncClient:
        def __init__(self, *args, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return None

        async def post(self, url, json):
            return httpx.Response(
                200,
                json={"not_embeddings": []},
                request=httpx.Request("POST", url),
            )

    with patch("backend.services.ollama_embeddings.httpx.AsyncClient", FakeAsyncClient):
        client = OllamaEmbeddingClient(expected_dimension=EXPECTED_EMBEDDING_DIMENSION)
        with pytest.raises(OllamaEmbeddingError):
            asyncio.run(client.embed_many(["one"]))


def test_weighted_user_vector_calculation_normalizes_result():
    averaged = weighted_average([_vector(1.0), _vector(3.0)], [1.0, 0.5])
    normalized = normalize_vector(averaged)

    assert averaged[0] == pytest.approx(1.6666666667)
    assert sum(value * value for value in normalized) == pytest.approx(1.0)


def test_semantic_scoring_changes_order_without_adding_candidates():
    recommendations = [
        {"title": "Metadata Winner", "score": 0.8, "match_score": 0.8, "recommended_book": {"title": "A", "author": "X"}},
        {"title": "Semantic Winner", "score": 0.73, "match_score": 0.73, "recommended_book": {"title": "B", "author": "Y"}},
    ]

    with (
        patch("backend.services.ollama_embeddings.user_taste_vector", return_value=_vector(0.01)),
        patch(
            "backend.services.ollama_embeddings.recommendation_similarities",
            return_value={
                "title_author:a:x": 0.1,
                "title_author:b:y": 1.0,
            },
        ),
    ):
        result = rerank_with_semantics(
            None,
            recommendations,
            library_books=[],
            embedding_model="embeddinggemma",
            debug=True,
        )

    assert [item["title"] for item in result] == ["Semantic Winner", "Metadata Winner"]
    assert len(result) == 2
    assert result[0]["semantic_available"] is True
    assert result[0]["semantic_diagnostics"]["semantic_weight"] == 0.25


def test_candidates_without_embeddings_remain_eligible():
    recommendations = [
        {"title": "With Vector", "score": 0.7, "recommended_book": {"title": "A", "author": "X"}},
        {"title": "No Vector", "score": 0.69, "recommended_book": {"title": "B", "author": "Y"}},
    ]

    with (
        patch("backend.services.ollama_embeddings.user_taste_vector", return_value=_vector(0.01)),
        patch(
            "backend.services.ollama_embeddings.recommendation_similarities",
            return_value={"title_author:a:x": 0.8},
        ),
    ):
        result = rerank_with_semantics(
            None,
            recommendations,
            library_books=[],
            embedding_model="embeddinggemma",
        )

    assert {item["title"] for item in result} == {"With Vector", "No Vector"}
    assert next(item for item in result if item["title"] == "No Vector")["semantic_available"] is False


def test_external_candidates_receive_and_cache_embeddings_when_ollama_available():
    class FakeClient:
        model = "embeddinggemma"
        embedding_model = "embeddinggemma:latest"

        async def embed_many(self, texts):
            self.texts = texts
            return [_vector(0.2) for _ in texts]

    class FakeDb:
        def commit(self):
            self.committed = True

    upserts = []
    client = FakeClient()
    db = FakeDb()
    recommendations = [
        {
            "title": "External Book",
            "author": "Author",
            "outside_library": True,
            "description": "A strong adjacent match",
            "genres": ["Mystery"],
            "subjects": ["Investigation"],
            "discovery_source": "open_library",
            "recommended_book": {"title": "External Book", "author": "Author"},
        },
        {
            "title": "Library Book",
            "author": "Author",
            "outside_library": False,
            "recommended_book": {"title": "Library Book", "author": "Author"},
        },
    ]

    with (
        patch("backend.services.ollama_embeddings.stored_embedding_record", return_value=None),
        patch("backend.services.ollama_embeddings.upsert_embedding_record", side_effect=lambda *args, **kwargs: upserts.append(kwargs)),
    ):
        stats = asyncio.run(ensure_recommendation_embeddings(db, recommendations, client=client))

    assert stats.scanned == 1
    assert stats.created == 1
    assert len(client.texts) == 1
    assert upserts[0]["embedding_model"] == "embeddinggemma:latest"
    assert db.committed is True
