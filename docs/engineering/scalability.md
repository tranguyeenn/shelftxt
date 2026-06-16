# Scalability and limitations

Honest assessment of where ShelfTxt works well today and where it will strain—useful before adding features or choosing infrastructure.

---

## Persistence status

**Current state:** PostgreSQL is the primary storage backend for profiles and user-owned book CRUD operations. CRUD and recommendation routes use `get_db()` session injection, validate Supabase Bearer tokens through `get_current_user()`, and flow through services, repository, SQLAlchemy, and PostgreSQL scoped by `user_id`.

Legacy CSV helpers still exist for export/import compatibility, recommendation-adjacent paths, and migration workflows.

## Previous CSV persistence limitations

Before the PostgreSQL CRUD migration, one file, `backend/data/processed/books.csv`, was read/written whole on each mutation via pandas.

| Limitation | Impact |
|------------|--------|
| **No concurrent write safety** | Parallel requests can race; last write wins |
| **Full-file read/write** | O(n) with library size; fine for hundreds/low thousands of rows |
| **No query indexes** | Cannot efficiently filter by author/status at DB layer |
| **Render ephemeral disk** | Free/low-tier redeploys may wipe data ([deployment.md](deployment.md)) |
| **Single library** | No multi-user isolation before `books.user_id` ownership |

These limitations are the reason PostgreSQL-backed CRUD now exists. Continue to avoid reintroducing direct CSV read/write behavior in book CRUD routes.

---

## Render / deployment considerations

- API hosted on Render; memory footprint includes pandas + full DataFrame copies during recommend
- Keep-warm job pings `/health` every 14 minutes (`backend/api.py` lifespan)
- Cold starts add latency to first request after idle
- Recommendation requests currently build from a fresh user-scoped PostgreSQL read and in-memory DataFrame

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
| Recommendation response cache | Not active on the current HTTP path | `recommendation.py` retains a legacy cached helper, but `get_recommendation(db, user_id, style)` builds fresh results |

If response caching is reintroduced, the cache key must include user identity and enough library versioning to avoid stale or cross-user results.

---

## Database migration considerations

Repository facade exists to limit blast radius:

```text
routes → services → repository → SQLAlchemy → PostgreSQL
```

Completed migration work includes:

1. Local PostgreSQL infrastructure
2. SQLAlchemy, psycopg, Alembic, and dotenv dependencies
3. SQLAlchemy foundation and `Profile` / `Book` ORM models
4. Alembic migrations for `profiles`, `books`, and `books.user_id`
5. User-scoped PostgreSQL repository CRUD operations
6. Book CRUD route refactor to PostgreSQL-backed services
7. Stronger Pydantic request/response validation
8. Supabase authentication and protected book/recommendation routes

Remaining follow-up:

- Add DB-backed integration tests where useful
- Move remaining CSV-adjacent paths when product requirements call for it
- Add SQL-level pagination/filtering where large libraries need it

---

## Frontend scalability

- `GET /books` is paginated on the wire (`page`, `limit`, max 100) and uses the PostgreSQL-backed repository layer; SQL-level pagination remains a follow-up optimization
- Settings in `localStorage` — no cross-device sync for theme/recommendation preferences
- Auth session persistence and refresh are handled by Supabase in the browser

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

- Authentication is implemented with Supabase Bearer tokens on book and recommendation routes
- No rate limiting on import or clear
- CORS restricted to known frontends; direct API clients still need valid tokens for protected routes

Address rate limiting and abuse controls before general release beyond controlled demos.

---

## When to revisit this document

- Before horizontal scaling on Render
- Before public beta with larger real-user traffic
- After library size exceeds ~2–5k rows (performance sanity check)
- When adding genre/mood fields that increase feature computation cost
