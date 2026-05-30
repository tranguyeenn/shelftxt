# Repository map

Where code lives and what each layer may do. For diagrams and deployment context, see [architecture.md](../architecture.md) and [system-design/architecture-overview.md](../system-design/architecture-overview.md).

---

## Top level

```text
shelftxt/
├── backend/       # FastAPI, ranking, CSV persistence
├── frontend/        # Vite + React SPA (Vercel)
├── cli/             # Local shelf helper
├── tests/           # Python unit tests
└── docs/            # This documentation
```

---

## `backend/`

| Path | Responsibility |
|------|----------------|
| `api.py` | FastAPI app, CORS, keep-warm job, router registration |
| `routes/` | HTTP handlers — call services, return JSON/CSV |
| `schemas/` | Pydantic request models |
| `services/` | Use cases: books CRUD, import/export, recommendations |
| `services/recommendation_builder.py` | Top-10 recommendations + explanations |
| `services/book_api.py` | Row → API book dict; lookup by `ISBN/UID` |
| `repository/` | `get_all_books`, `save_books` → `book_data.py` |
| `book_data.py` | CSV path, columns, load/save coercion |
| `preprocess/` | `rating_norm`, `recency_norm` |
| `ranking/` | `score_tbr_books`, `score_read_books` |
| `ingest/` | Offline batch pipeline (not live UI import) |
| `data/processed/` | Runtime `books.csv` (gitignored) |

### Layer rules

```text
routes/  →  services/  →  repository/  →  book_data.py  →  CSV
                ↘  preprocess/ , ranking/  (algorithms only)
```

| Layer | Do | Don't |
|-------|-----|--------|
| `routes/` | HTTP, delegate to services | Shelf algorithms, long CSV rules |
| `services/` | Orchestration, business validation | FastAPI route definitions |
| `repository/` | Load/save abstraction | Ranking math |
| `ranking/` | Pure DataFrame transforms | File I/O |

Always import with the `backend.` package prefix from repo root.

---

## `backend/routes/` (current)

| File | Paths |
|------|-------|
| `health.py` | `/health` |
| `books.py` | `/books`, `/books/export`, `/books/import`, `/books/clear`, `/books/{id}/progress`, `/books/{id}` |
| `recommendation.py` | `/recommend` |

Most shelf logic lives in `services/books.py`. `GET /books` still calls `load_data()` directly in the route (minor inconsistency).

---

## `frontend/`

| Area | Role |
|------|------|
| `src/pages/` | Route screens (Dashboard, Library, Recommendations, …) |
| `src/features/` | Domain UI (dashboard, recommendations, settings) |
| `src/components/` | Shared layout and book editors |
| `src/lib/api.ts` | `apiUrl`, `fetchJson` |
| `src/lib/userSettings.ts` | Theme, accent, recommendation style (localStorage) |
| `src/contexts/` | `UserSettingsProvider` |

Deployed as a static SPA on Vercel (`frontend/dist/`). Details: [frontend.md](../frontend.md).

---

## Tests

```bash
./.venv/bin/python -m unittest discover -s tests -v
```

| File | Covers |
|------|--------|
| `test_api.py` | HTTP via `TestClient`; mock services/repository |
| `test_recommendation_builder.py` | Structured recommendation output |
| `test_flexible_pipeline.py` | Batch ingest + ranking |

Patch names **where they are used** in the module under test.

---

## Where to change things

| Question | Look in |
|----------|---------|
| API path or status code | `backend/routes/` |
| Scoring or explanation text | `ranking/`, `services/recommendation_builder.py` |
| CSV columns | `backend/book_data.py` |
| UI route or flow | `frontend/src/pages/` |
| Deploy / env | [deployment.md](../deployment.md) |
| Past refactors | [devlogs/](../devlogs/) |

---

## Refactor backlog

| Area | Status |
|------|--------|
| Layered routes + services | Mostly done |
| `GET /books` via repository | Minor gap |
| Remove `api_draft.py` | Pending |
| Postgres migration | Planned — [ROADMAP.md](../../ROADMAP.md) |
