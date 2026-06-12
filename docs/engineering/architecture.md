# Architecture

## High-level summary

ShelfTxt is a **monorepo** with three runnable surfaces that share one logical library:

| Surface | Stack | Role |
|---------|-------|------|
| **Web UI** | Vite, React 19, TypeScript, Tailwind CSS | Reader-facing library, progress, recommendations, settings |
| **REST API** | FastAPI, pandas, Pydantic | CRUD, import/export, recommendation orchestration |
| **CLI** | Python (`cli/manage_books.py`) | Local shelf edits (limited commands today) |
| **Batch pipeline** | Python (`backend/ingest/`) | Offline CSV mapping to canonical schema—not used by live UI import |

**Persistence today:** PostgreSQL is the primary storage backend for book CRUD operations. Routes call services, services call the PostgreSQL repository layer, and SQLAlchemy persists `Book` rows to the `books` table. CSV remains for export/import compatibility and legacy helper paths.

**Production hosts (as of current deployment):**

- Frontend: Vercel (`shelftxt.vercel.app`)
- API: Render (`shelftxt.onrender.com`)

---

## Production topology

```mermaid
flowchart LR
  Browser[shelftxt.vercel.app]
  API[shelftxt.onrender.com]
  DB[(PostgreSQL books table)]

  Browser -->|HTTPS JSON| API
  API --> DB
```

- **Production:** browser calls Render directly (`frontend/src/lib/api.ts`).
- **Local dev:** browser calls `/api/*` → Vite proxy → `127.0.0.1:8000`.

See [decisions.md](../product/decisions.md#adr-003-production-api-calls-bypass-vercel-proxy).

---

## Main components

### Frontend

- SPA under `frontend/src/`
- Routes: Dashboard, Library, Recommendations, Book detail, Add book, Insights, Settings
- Calls the API via `frontend/src/lib/api.ts` (direct to Render in production; Vite proxy `/api/*` in local dev)
- Reader preferences (recommendation style, theme, accent) stored in **browser `localStorage`** — not synced to the backend today

### FastAPI backend

- Entry: `backend/api.py` — CORS, lifespan (keep-warm ping), router registration
- HTTP handlers: `backend/routes/` — thin; delegate to services
- Business logic: `backend/services/` — shelf mutations, import/export, recommendation cache
- Validation: `backend/schemas/` — Pydantic request and response models

### Book data storage layer

- `backend/db/database.py` — SQLAlchemy engine, session factory, `get_db()` dependency, declarative `Base`
- `backend/db/models.py` — `Book` ORM model mapped to the `books` table
- `backend/repository/postgres_books_repository.py` — CRUD operations for `Book` records
- `backend/services/postgres_books.py` — book CRUD use cases backed by the repository layer
- `backend/book_data.py` — legacy CSV helper used by CSV-adjacent paths, not the book CRUD source of truth

### Recommendation / ranking logic

- **Preprocess:** `backend/preprocess/normalize.py` — `rating_norm`, `recency_norm`
- **Ranking:** `backend/ranking/score.py` — TBR scoring via author preference from read history
- **Orchestration:** `backend/services/recommendation_builder.py` — top-N list, explanations, similar books
- **Cache:** `backend/services/recommendation.py` — `@lru_cache` keyed by recommendation style

Ranking modules perform **no I/O**; they receive DataFrames from services.

### CSV import / export

- **UI import:** browser parses CSV → JSON → `POST /books/import`
- **Export:** `GET /books/export` returns full library CSV
- **Batch ingest:** separate Python pipeline for arbitrary external CSV schemas — see [import-export.md](import-export.md#batch-pipeline)

---

## Request / response flow (typical read)

```mermaid
sequenceDiagram
  participant Browser
  participant Vite as Vite dev proxy (local only)
  participant API as FastAPI routes
  participant Svc as services/
  participant Repo as repository/
  participant DB as PostgreSQL

  Browser->>API: GET /books?page=&limit=
  API->>Svc: get_books_service(db, page, limit)
  Svc->>Repo: get_all_books(db)
  Repo->>DB: SQLAlchemy query
  DB-->>Repo: Book rows
  Repo-->>Svc: Book models
  API-->>Browser: { page, limit, total, results }
```

## Request / response flow (recommendation)

```mermaid
sequenceDiagram
  participant Browser
  participant API as GET /recommend?style=
  participant Rec as recommendation.py
  participant Builder as recommendation_builder.py
  participant Rank as ranking/score.py
  participant Pre as preprocess/normalize.py
  participant CSV as books.csv

  Browser->>API: style query param
  API->>Rec: get_recommendation(style)
  alt cache hit
    Rec-->>API: cached top 10
  else cache miss
    Rec->>CSV: load_data()
    Rec->>Builder: build_recommendations(df, style)
    Builder->>Pre: normalize_rating, compute_recency
    Builder->>Rank: score_tbr_books(...)
    Builder-->>Rec: structured recommendations
  end
  API-->>Browser: JSON array
```

Book CRUD mutations (add, patch, progress, delete, import, clear) go through `services/postgres_books.py` and persist through the PostgreSQL repository layer.

---

## System context diagram

```mermaid
flowchart TB
  subgraph client [Client]
    UI[Vite + React SPA]
  end

  subgraph render [Render - API]
    Routes[routes/]
    Services[services/]
    Repo[repository/]
    SA[SQLAlchemy]
    Rank[ranking/ + preprocess/]
    DB[(PostgreSQL)]
  end

  UI -->|HTTPS JSON| Routes
  Routes --> Services
  Services --> Repo
  Repo --> SA
  SA --> DB
  Services --> Rank
  Rank -.->|read-only DataFrame| Services
```

---

## Layer boundaries

| Layer | Responsibility | Should not |
|-------|----------------|------------|
| **UI** | Display library, collect edits, explain recommendations to readers | Implement scoring rules or persist data locally (except UI-only prefs) |
| **Routes** | HTTP mapping, status codes, JSON/CSV response shapes | Contain shelf transition branching or ranking math |
| **Services** | Use cases: add book, update progress, build recommendations | Know about React or Vite |
| **Repository** | SQLAlchemy-backed CRUD abstraction | Rank or validate HTTP bodies |
| **Database** | SQLAlchemy session/model mapping and PostgreSQL persistence | Business rules for shelf states |
| **book_data** | Legacy CSV I/O for CSV-adjacent compatibility paths | Book CRUD source of truth |
| **ranking / preprocess** | Pure transforms on DataFrames | Read files or call HTTP |

### Known boundary gaps (current)

- `GET /books` now goes through `services/postgres_books.py` and the PostgreSQL repository layer. Pagination response shape is preserved; deeper SQL-level pagination can still be improved.
- `backend/api_draft.py` exists as legacy reference; **not** mounted by `uvicorn backend.api:app`.
- Title remains a lookup key for `PATCH /books` and `DELETE /books?title=`; book id (`ISBN/UID`) is preferred for progress and delete-by-id from the UI.

---

## Two data paths

| Path | Schema | Entry |
|------|--------|-------|
| **App (live CRUD)** | SQLAlchemy `Book` model plus CSV-shaped API compatibility fields | UI, API |
| **Batch (offline)** | Canonical lowercase fields | `backend/ingest/pipeline.py` |

UI import uses `POST /books/import` (JSON)—not the batch pipeline. See [import-export.md](import-export.md).

---

## Route map (current)

| Router | Paths |
|--------|-------|
| `health.py` | `GET|HEAD /health` |
| `books.py` | `GET /books?page&limit` (paginated), `POST|PATCH|DELETE /books`, `GET /books/export`, `POST /books/import`, `POST /books/clear`, `PATCH /books/{id}/progress`, `DELETE /books/{id}` |
| `recommendation.py` | `GET /recommend?style=` |

Full API reference: [api.md](api.md).

---

## Cross-cutting concerns

| Concern | Location |
|---------|----------|
| CORS | `backend/api.py` |
| Recommendation cache | `@lru_cache` in `services/recommendation.py`; cleared on book writes |
| Keep-warm | Scheduler pings `/health` every 14 min |
| Legacy | `backend/api_draft.py` — not loaded in production |

---

## Repository map

Where code lives and what each layer may do.

### Top level

```text
shelftxt/
├── backend/       # FastAPI, ranking, PostgreSQL persistence
├── frontend/        # Vite + React SPA (Vercel)
├── cli/             # Local shelf helper
├── tests/           # Python unit tests
└── docs/            # This documentation
```

### `backend/`

| Path | Responsibility |
|------|----------------|
| `api.py` | FastAPI app, CORS, keep-warm job, router registration |
| `routes/` | HTTP handlers — call services, return JSON/CSV |
| `schemas/` | Pydantic request/response models |
| `services/` | Use cases: books CRUD, import/export, recommendations |
| `services/recommendation_builder.py` | Top-10 recommendations + explanations |
| `services/book_api.py` | Row → API book dict; lookup by `ISBN/UID` |
| `db/` | SQLAlchemy engine/session setup and ORM models |
| `repository/` | PostgreSQL CRUD operations |
| `book_data.py` | Legacy CSV path, columns, load/save coercion for CSV-adjacent paths |
| `preprocess/` | `rating_norm`, `recency_norm` |
| `ranking/` | `score_tbr_books`, `score_read_books` |
| `ingest/` | Offline batch pipeline (not live UI import) |
| `data/processed/` | Runtime `books.csv` (gitignored) |

#### Layer rules {#backend-layer-rules}

```text
routes/  →  services/  →  repository/  →  SQLAlchemy  →  PostgreSQL
                ↘  preprocess/ , ranking/  (algorithms only)
```

| Layer | Do | Don't |
|-------|-----|--------|
| `routes/` | HTTP, dependency injection, delegate to services | Shelf algorithms, persistence rules |
| `services/` | Orchestration, business validation | FastAPI route definitions |
| `repository/` | Load/save abstraction | Ranking math |
| `ranking/` | Pure DataFrame transforms | File I/O |

Always import with the `backend.` package prefix from repo root.

### `backend/routes/` (current)

| File | Paths |
|------|-------|
| `health.py` | `/health` |
| `books.py` | `GET /books?page&limit` (paginated), `/books/export`, `/books/import`, `/books/clear`, `/books/{id}/progress`, `/books/{id}` |
| `recommendation.py` | `/recommend` |

Most PostgreSQL-backed shelf logic lives in `services/postgres_books.py`. Routes inject a database session with `get_db()` and preserve existing response formats.

### `frontend/`

| Area | Role |
|------|------|
| `src/pages/` | Route screens (Dashboard, Library, Recommendations, …) |
| `src/features/` | Domain UI (dashboard, recommendations, settings) |
| `src/components/` | Shared layout and book editors |
| `src/lib/api.ts` | `apiUrl`, `fetchJson` |
| `src/lib/userSettings.ts` | Theme, accent, recommendation style (localStorage) |
| `src/contexts/` | `UserSettingsProvider` |

Deployed as a static SPA on Vercel (`frontend/dist/`). Details: [frontend.md](frontend.md).

### Tests

```bash
./.venv/bin/python -m unittest discover -s tests -v
```

| File | Covers |
|------|--------|
| `test_api.py` | HTTP via `TestClient`; `GET /books` pagination + mock services/repository |
| `test_recommendation_builder.py` | Structured recommendation output |
| `test_flexible_pipeline.py` | Batch ingest + ranking |

Patch names **where they are used** in the module under test.

---

## Where to change things

| Question | Look in |
|----------|---------|
| API path or status code | `backend/routes/` |
| Scoring or explanation text | `ranking/`, `services/recommendation_builder.py` |
| PostgreSQL book schema | `backend/db/models.py` |
| CSV compatibility columns | `backend/book_data.py` |
| UI route or flow | `frontend/src/pages/` |
| Deploy / env | [deployment.md](deployment.md) |
| Past refactors | [devlogs/](../history/devlogs) |

---

## Deployment notes

See [deployment.md](deployment.md). Render runs a periodic self-ping to `/health` to reduce cold starts on free tier.

---

## Refactor backlog

| Area | Status |
|------|--------|
| Layered routes + services | Mostly done |
| `GET /books` via repository | Done |
| Remove `api_draft.py` | Pending |
| Postgres migration phases 1-7 | Complete — [postgres-migration-audit.md](postgres-migration-audit.md) |

---

## Related

- [data-model.md](data-model.md) — CSV columns
- [backend.md](backend.md) — routes, services, sequence diagrams
- [deployment.md](deployment.md) — production runbook
- [recommendation-system.md](recommendation-system.md) — scoring and explanations
