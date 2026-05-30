# Architecture (summary)

ShelfTxt is a **monorepo** with a Vite + React frontend (Vercel), a FastAPI backend (Render), and optional CLI/batch tools—all sharing one CSV library.

For full diagrams, boundaries, and roadmap context, see **[system-design/architecture-overview.md](system-design/architecture-overview.md)**.

---

## Surfaces

| Surface | Stack | Host | Entry |
|---------|-------|------|-------|
| Web UI | Vite, React 19, TypeScript | [Vercel](https://shelftxt.vercel.app) | `frontend/src/main.tsx` |
| REST API | FastAPI, pandas, Pydantic | [Render](https://shelftxt.onrender.com) | `backend/api.py` |
| Batch pipeline | Python | Local | `backend/ingest/pipeline.py` |
| CLI | Python | Local | `cli/manage_books.py` |

**Persistence:** `backend/data/processed/books.csv` via `book_data.py` and `repository/books_repository.py`.

---

## Production topology

```mermaid
flowchart LR
  Browser[shelftxt.vercel.app]
  API[shelftxt.onrender.com]
  CSV[(books.csv)]

  Browser -->|HTTPS JSON| API
  API --> CSV
```

- **Production:** browser calls Render directly (`frontend/src/lib/api.ts`).
- **Local dev:** browser calls `/api/*` → Vite proxy → `127.0.0.1:8000`.

See [decisions.md](decisions.md#adr-003-production-api-calls-bypass-vercel-proxy).

---

## Backend layers

```text
HTTP → routes/ → services/ → repository/ → book_data.py → books.csv
                    ↘ preprocess/ + ranking/  (no I/O)
```

| Layer | Role |
|-------|------|
| `routes/` | HTTP only |
| `services/` | Business logic, cache invalidation |
| `repository/` | Persistence facade |
| `schemas/` | Pydantic request models |
| `preprocess/`, `ranking/` | Feature normalization and scoring |

Folder details: [architecture/system-overview.md](architecture/system-overview.md).

---

## Two data paths

| Path | Schema | Entry |
|------|--------|-------|
| **App (live)** | `BOOKS_COLUMNS` in CSV | UI, API, CLI |
| **Batch (offline)** | Canonical lowercase fields | `backend/ingest/pipeline.py` |

UI import uses `POST /books/import` (JSON)—not the batch pipeline. See [pipeline.md](pipeline.md).

---

## Route map (current)

| Router | Paths |
|--------|-------|
| `health.py` | `GET|HEAD /health` |
| `books.py` | `GET /books?page&limit` (paginated), `POST|PATCH|DELETE /books`, `GET /books/export`, `POST /books/import`, `POST /books/clear`, `PATCH /books/{id}/progress`, `DELETE /books/{id}` |
| `recommendation.py` | `GET /recommend?style=` |

Full API reference: [api.md](api.md).

---

## Cross-cutting

| Concern | Location |
|---------|----------|
| CORS | `backend/api.py` |
| Recommendation cache | `@lru_cache` in `services/recommendation.py`; cleared on book writes |
| Keep-warm | Scheduler pings `/health` every 14 min |
| Legacy | `backend/api_draft.py` — not loaded in production |

---

## Related

- [system-design/](system-design/README.md) — in-depth design docs
- [data-model.md](data-model.md) — CSV columns
- [deployment.md](deployment.md) — production runbook
