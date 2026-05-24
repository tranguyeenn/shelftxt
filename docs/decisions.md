# Architecture decisions

Lightweight ADRs (Architecture Decision Records). Format: context → decision → consequences.

---

## ADR-001: CSV as single source of truth

**Status:** Accepted

**Context:** Solo project, small library size, no auth yet. Need simple persistence shared by API, CLI, and batch tools.

**Decision:** Store the live library in `backend/data/processed/books.csv`. Access only through `book_data.load_data()` / `save_data()`.

**Consequences:**

- (+) Zero infra cost, easy to inspect and backup
- (+) Same file for API and CLI
- (−) No concurrent-write safety beyond single-process assumption
- (−) PaaS ephemeral disks can wipe data on redeploy
- **Future:** Swap repository implementation; keep service interfaces stable

---

## ADR-002: Monorepo, not microservices

**Status:** Accepted

**Context:** One developer, one product. Deploy API and UI separately for hosting constraints, not organizational boundaries.

**Decision:** Single repo with `backend/`, `frontend/`, `cli/`. No Redis, queues, or service mesh.

**Consequences:**

- (+) One clone, one PR, shared docs
- (+) Ranking code reused by API and batch pipeline
- (−) Deploy config must respect monorepo roots (Render = repo root, Vercel = `frontend`)

---

## ADR-003: Production API calls bypass Vercel proxy

**Status:** Accepted (2026-05)

**Context:** Next.js `app/api/*` route handlers returned 404 on Vercel despite building locally. Root cause: monorepo root misconfiguration and/or serverless routing on static deploy.

**Decision:** In production, the browser calls Render directly via `frontend/lib/apiUrl.ts`. Local dev keeps `/api/*` proxy through Next.js route handlers.

**Consequences:**

- (+) Reliable production connectivity
- (+) Fewer serverless invocations on Vercel
- (−) Requires CORS on FastAPI for `https://shelftxt.vercel.app`
- (−) API URL baked into client bundle unless `NEXT_PUBLIC_API_BASE_URL` is set at build time
- **Note:** `app/api/*/route.ts` retained for local dev; `vercel.json` rewrites kept as fallback

---

## ADR-004: Title string as primary key

**Status:** Accepted

**Context:** Goodreads-style export uses `Title` as natural identifier. No user accounts yet.

**Decision:** PATCH/DELETE match books by exact `Title`. Renames check for duplicates. `ISBN/UID` is stored but not used as API key.

**Consequences:**

- (+) Matches user mental model and CSV exports
- (−) Fragile if titles change or duplicate titles exist
- **Future:** Introduce stable `id` when multi-user or imports create collisions

---

## ADR-005: Incremental service-layer extraction

**Status:** In progress

**Context:** `backend/api.py` grew to include shelf state machine, CRUD, and HTTP concerns. Hard to test and extend.

**Decision:** Extract use-cases into `backend/services/` one endpoint at a time. First: `GET /recommend` → `services/recommendation.py`. Keep `book_data.py` as repository; defer `routes/` and `schemas/` splits until patterns repeat.

**Consequences:**

- (+) Clear place for business logic without DI framework
- (+) Tests mock at service or `backend.api` boundary
- (−) Temporary duplication (`clean_for_json` in api + service) until consolidated

---

## ADR-006: Two ingest paths

**Status:** Accepted

**Context:** UI import is JSON bulk add from client-parsed CSV. Power users need arbitrary CSV schemas with mapping config.

**Decision:**

- **App path:** `POST /books/import` — simple JSON, no mapping file
- **Batch path:** `ingest/pipeline.py` — mapping JSON, validation, ranked output in memory

**Consequences:**

- (+) Simple UX for web import
- (+) Flexible batch analysis without coupling to live CSV
- (−) Two behaviors to document and test

---

## When to add a new ADR

Add a short entry when you:

- Change persistence, auth, or deployment topology
- Introduce a new external dependency (DB, cache, worker)
- Make a trade-off future contributors will question

Keep entries to one screen. Link from PR descriptions when relevant.
