# Scalability and limitations

Honest assessment of where ShelfTxt works well today and where it will strain—useful before adding features or choosing infrastructure.

---

## CSV persistence limitations

**Current state:** one file, `backend/data/processed/books.csv`, read/written whole on each mutation via pandas.

| Limitation | Impact |
|------------|--------|
| **No concurrent write safety** | Parallel requests can race; last write wins |
| **Full-file read/write** | O(n) with library size; fine for hundreds/low thousands of rows |
| **No query indexes** | Cannot efficiently filter by author/status at DB layer |
| **Render ephemeral disk** | Free/low-tier redeploys may wipe data ([deployment.md](../deployment.md)) |
| **Single library** | No multi-user isolation |

Acceptable for pre-release personal use; **not** a long-term production data layer without migration.

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
| `get_recommendation` LRU | Process memory, per style | Any book write via `invalidate_recommendation_cache()` |

Not shared across Render instances if scaled horizontally—each instance would have its own cache (another reason CSV + LRU is single-instance minded).

**Future:** Redis or computed-at-write ranking table when moving to DB.

---

## Database migration considerations

Repository facade (`books_repository.py`) exists to limit blast radius:

```text
services → repository → book_data (today)
services → repository → postgres adapter (future)
```

Migration tasks likely include:

1. Schema mirroring `BOOKS_COLUMNS` + future optional columns
2. Backfill from CSV export
3. Switch `get_all_books` / `save_books` implementation
4. Replace full-table scans with indexed queries where needed
5. Per-user `library_id` if auth added

### Possible direction: PostgreSQL / Supabase

Exploratory, not committed:

- **PostgreSQL** on Render or external host
- **Supabase** for Postgres + optional auth/storage

Either would address durability, concurrency, and multi-user paths better than CSV.

---

## Frontend scalability

- `GET /books` is paginated on the wire (`page`, `limit`, max 100), but `load_data()` still reads the full CSV per request — fine for small shelves; PostgreSQL paging needed at scale
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
