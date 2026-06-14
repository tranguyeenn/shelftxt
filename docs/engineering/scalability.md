# Scalability and limitations

Honest assessment of where ShelfTxt works well today and where it will strain—useful before adding features or choosing infrastructure.

---

## Persistence status

**Current state:** PostgreSQL is the primary storage backend for book CRUD operations. CRUD routes use `get_db()` session injection and flow through services, repository, SQLAlchemy, and PostgreSQL.

Legacy CSV helpers still exist for export/import compatibility, recommendation-adjacent paths, and migration workflows.

## Previous CSV persistence limitations

Before the PostgreSQL CRUD migration, one file, `backend/data/processed/books.csv`, was read/written whole on each mutation via pandas.

| Limitation | Impact |
|------------|--------|
| **No concurrent write safety** | Parallel requests can race; last write wins |
| **Full-file read/write** | O(n) with library size; fine for hundreds/low thousands of rows |
| **No query indexes** | Cannot efficiently filter by author/status at DB layer |
| **Render ephemeral disk** | Free/low-tier redeploys may wipe data ([deployment.md](deployment.md)) |
| **Single library** | No multi-user isolation |

These limitations are the reason PostgreSQL-backed CRUD now exists. Continue to avoid reintroducing direct CSV read/write behavior in book CRUD routes.

---

## Render / deployment considerations

- API hosted on Render; memory footprint includes pandas + full DataFrame copies during recommend
- Keep-warm job pings `/health` every 14 minutes (`backend/api.py` lifespan)
- Cold starts add latency to first request after idle
- Recommendation `@lru_cache` reduces repeated CPU work but increases memory slightly per cached style

For large libraries, monitor recommend latency and memory on Render metrics if available.

---

## Why recommendation logic is decoupled from routes

Ranking lives in `preprocess/` and `ranking/`; HTTP assembly in `recommendation_builder.py`.

Benefits:

- Test scoring without FastAPI TestClient
- Swap cache, async, or precomputation in service layer only
- Future worker process could compute ranks offline without HTTP

**Anti-pattern:** embedding `score_tbr_books` inside route handlers—blocks extraction and duplicates cache invalidation concerns.

---

## Caching (current)

| Cache | Scope | Invalidation |
|-------|-------|--------------|
| `get_recommendation` LRU | Process memory, per style | Legacy CSV service writes call `invalidate_recommendation_cache()`; PostgreSQL CRUD cache invalidation should be reviewed before expanding recommendation freshness guarantees |

Not shared across Render instances if scaled horizontally—each instance would have its own cache (another reason CSV + LRU is single-instance minded).

**Future:** Redis or computed-at-write ranking table when moving to DB.

---

## Database migration considerations

Repository facade exists to limit blast radius:

```text
routes → services → repository → SQLAlchemy → PostgreSQL
```

Completed migration work includes:

1. Local PostgreSQL infrastructure
2. SQLAlchemy, psycopg, Alembic, and dotenv dependencies
3. SQLAlchemy foundation and `Book` ORM model
4. Alembic migrations for the `books` table
5. PostgreSQL repository CRUD operations
6. Book CRUD route refactor to PostgreSQL-backed services
7. Stronger Pydantic request/response validation

Remaining follow-up:

- Add DB-backed integration tests where useful
- Move remaining CSV-adjacent paths when product requirements call for it
- Add per-user `library_id` if auth is introduced

---

## Frontend scalability

- `GET /books` is paginated on the wire (`page`, `limit`, max 100) and uses the PostgreSQL-backed repository layer; SQL-level pagination remains a follow-up optimization
- Settings in `localStorage` — no cross-device sync

---

## Testing priorities

| Area | Current | Priority |
|------|---------|----------|
| API CRUD/import | `tests/test_api.py` | maintain |
| Recommendation builder smoke | `tests/test_recommendation_builder.py` | extend |
| Deterministic ranking | limited | **high** — fixed RNG seed in tests |
| CSV round-trip | manual | medium — automated export/import fixture |
| Progress edge cases | partial | medium |
| Frontend | tsc build only | add component tests selectively |

Recommendation scoring changes should include fixture libraries with expected ordering before/after refactor.

---

## Security / abuse (current gaps)

- No authentication — anyone with API URL can mutate library if exposed
- No rate limiting on import or clear
- CORS restricted to known frontends but public API remains open

Address before general release beyond personal demos.

---

## When to revisit this document

- Before horizontal scaling on Render
- Before public beta with real user accounts
- After library size exceeds ~2–5k rows (performance sanity check)
- When adding genre/mood fields that increase feature computation cost
