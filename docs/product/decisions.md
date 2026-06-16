# Architecture decisions

Lightweight ADRs. Format: context → decision → consequences.

---

## ADR-001: CSV as single source of truth (superseded)

**Status:** Superseded by ADR-009

**Context:** Solo project, small library, no auth yet.

**Historical decision:** Live library in `backend/data/processed/books.csv`. Low-level access via `book_data.py`; services/routes prefer `repository/books_repository.py`.

**Consequences:** (+) Simple, portable (−) No concurrent-write safety; ephemeral disk on Render free tier.

---

## ADR-002: Monorepo, not microservices

**Status:** Accepted

**Decision:** Single repo: `backend/`, `frontend/`, `cli/`. Deploy API (Render) and UI (Vercel) separately.

**Consequences:** (+) One PR, shared ranking code (−) Correct Root Directory per host required.

---

## ADR-003: Production API calls bypass Vercel proxy

**Status:** Accepted

**Decision:** Production browser → Render via `apiUrl.ts`. Local dev → `/api/*` Vite proxy to `127.0.0.1:8000`.

**Consequences:** (+) Reliable on Vercel (−) CORS required for `shelftxt.vercel.app`.

---

## ADR-004: Book identity keys

**Status:** Accepted (evolving)

**Decision:** `ISBN/UID` is the stable id for UI routes, progress updates, and delete-by-id. Legacy endpoints still match by exact `Title` for PATCH/DELETE.

**Consequences:** (+) Stable URLs after renames (−) Title-based endpoints remain fragile; import dedupes by title case-sensitively.

---

## ADR-005: Layered backend (routes / services / repository)

**Status:** Accepted (2026-05)

**Context:** Monolithic `api.py` mixed HTTP, shelf rules, and persistence.

**Decision:**

| Layer | Location |
|-------|----------|
| App shell | `backend/api.py` |
| HTTP routes | `backend/routes/` |
| Request models | `backend/schemas/` |
| Business logic | `backend/services/` |
| Persistence facade | `backend/repository/` |

**Consequences:**

- (+) Clear boundaries; routes stay thin where extracted
- (+) `GET /recommend` isolated in `services/recommendation.py`
- (−) Some shelf PATCH logic still in `services/books.py` — largely migrated from routes
- (−) `api_draft.py` kept temporarily as legacy reference — **do not extend**

---

## ADR-006: Two ingest paths

**Status:** Accepted

**Decision:** Web `POST /books/import` (JSON) vs batch `ingest/pipeline.py` (mapping JSON).

---

## ADR-007: Cached recommendations

**Status:** Accepted

**Decision:** Earlier recommendation work introduced an `@lru_cache` helper, but the current authenticated HTTP path builds recommendations from a fresh PostgreSQL read scoped by `user_id`.

**Consequences:** (+) Simpler multi-user correctness and fresher reads (+) No cross-user cache-key risk (−) Repeated recommendation requests recompute scores.

---

## ADR-008: Paginated `GET /books`

**Status:** Accepted

**Context:** Large libraries inflate response size; PostgreSQL migration was planned.

**Decision:** `GET /books` returns `{ page, limit, total, results }` with query params `page` (≥ 1) and `limit` (1–100, default 20). Frontend loads the full shelf via `fetchAllLibraryBooks()` until the Library UI paginates client-side.

**Consequences:** (+) Smaller payloads per request (+) API shape is compatible with DB-backed paging (−) Breaking change vs. top-level array (−) SQL-level pagination remains a follow-up optimization.

---

## ADR-009: PostgreSQL-backed book CRUD

**Status:** Accepted

**Context:** CSV storage was simple but created durability, concurrency, and deployment risks. PostgreSQL migration phases 1-7 established local database infrastructure, SQLAlchemy, Alembic migrations, a repository layer, route/session injection through `get_db()`, PostgreSQL-backed book CRUD services, and stronger Pydantic validation.

**Decision:** Book CRUD routes use PostgreSQL as the source of truth through the flow `routes -> services -> repository -> SQLAlchemy -> PostgreSQL`. Existing API response formats are preserved, including CSV-compatible field names for `GET /books`.

**Consequences:** (+) Book CRUD no longer depends on direct CSV reads/writes (+) Stronger request validation and documented response models (+) Durable database foundation for authenticated multi-user ownership (−) CSV export/import compatibility and recommendation-adjacent paths still need careful follow-up.

---

## ADR-010: Supabase Auth and user-owned libraries

**Status:** Accepted

**Context:** Multi-user ShelfTxt needs account identity, session persistence, and authorization without hand-rolling password storage.

**Decision:** Supabase Auth owns registration, login, token issuance, session refresh, and logout. The frontend uses `@supabase/supabase-js`; protected React routes require a session. Backend routes validate `Authorization: Bearer <access_token>` in `backend/auth/dependencies.py`, load the matching `profiles` row, and scope book CRUD plus recommendations by `current_user.id`.

**Consequences:** (+) No custom password handling (+) Libraries are isolated by `books.user_id` (+) Frontend sessions persist and refresh through Supabase (−) Backend and frontend deployments both need correct Supabase environment variables.

---

## When to add a new ADR

Persistence change, auth, new deploy target, or a trade-off future you will question.
