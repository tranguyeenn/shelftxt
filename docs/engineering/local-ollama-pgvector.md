# Local Ollama pgvector experiment

This experiment is optional. ShelfTXT keeps the deterministic recommendation
pipeline as the source of truth for ownership, feedback exclusions, DNF rules,
series order, canonical identity, deduplication, outside-library requirements,
and final result count.

Embeddings use `OLLAMA_EMBEDDING_MODEL=embeddinggemma` and the migration creates
`book_embeddings.embedding` as `VECTOR(768)`. Changing embedding models may
require a new vector column, a new table, or a migration if the model dimension
changes.

```bash
ollama pull embeddinggemma
ollama serve
alembic upgrade head
python -m backend.scripts.backfill_book_embeddings
```

Verify Ollama:

```bash
curl http://localhost:11434/api/embed \
  -d '{
    "model": "embeddinggemma",
    "input": "Young adult mystery about teenage criminal profilers"
  }'
```

Verify PostgreSQL:

```sql
SELECT title, embedding_model, vector_dims(embedding)
FROM book_embeddings
LIMIT 10;
```

Recommendation debug output should include title, outside-library status,
existing score, semantic similarity, final score, and series eligibility. For
the Naturals case, confirm `Killer Instinct` is eligible next, `All In` and
`Bad Blood` remain blocked until prior installments are read, at least one valid
outside-library candidate appears, and semantic scoring changes ordering without
violating those rules.
