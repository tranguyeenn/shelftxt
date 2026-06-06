# Refactoring shelftxt backend

| | |
|---|---|
| **Date** | 2026-05-24 |
| **Feature / Refactor** | Backend layering — routes, services, repository, schemas |
| **Problem** | Monolithic `api.py` mixed HTTP, shelf rules, and recommendation orchestration; hard to test, extend, and reason about under production load |
| **Old approach** | Single ~500-line FastAPI file with inline recommendation pipeline (`load_data` → normalize → score → JSON) and all CRUD/shelf PATCH logic in route handlers |
| **New approach** | Thin `backend/api.py` registers routers; recommendation in `services/recommendation.py`; HTTP in `routes/`; Pydantic in `schemas/`; persistence via `repository/books_repository.py` → `book_data.py` |
| **Files changed** | `backend/api.py`, `backend/routes/*`, `backend/services/*`, `backend/schemas/books.py`, `backend/repository/`, `tests/test_api.py`, `docs/` |
| **Lessons learned** | [Below](#lessons-learned) |
| **Next steps** | Move shelf PATCH/add/import → `services/books.py`; remove `api_draft.py`; plan storage beyond CSV on Render |

---

## Context

Shelftxt started as a single-file FastAPI app: routes, Pydantic schemas, shelf state machine, and recommendation pipeline all lived in one module. That worked for a solo prototype but became friction when:

1. **Recommendation logic was buried in a route** — changing scoring or empty-state behavior meant editing HTTP code.
2. **Render free tier felt unstable** — cold starts, deploy config mistakes (wrong Root Directory, old `uvicorn api:app` entrypoint), and an overloaded “do everything” API module made incidents harder to isolate.
3. **Scaling is really about clarity first** — before Redis, workers, or a database, the codebase needed obvious boundaries so the next feature doesn’t bloat the entrypoint again.

The goal was not enterprise architecture — it was **clean FastAPI routes + a place for business logic** that a solo developer can still navigate.

---

## What changed

### Recommendation moved out of `api.py`

**Before:** `GET /recommend` loaded CSV, called `normalize_rating`, `compute_recency`, `score_tbr_books`, and `recommend_one` inline, then serialized to JSON.

**After:** `routes/recommendation.py` exposes `GET /recommend`; `services/recommendation.py` owns the pipeline. Ranking math stays in `ranking/score.py` and `preprocess/normalize.py` — the service is a conductor, not a copy-paste of algorithms.

Added `@lru_cache` on `get_recommendation()` plus `POST /recommend/refresh` to clear cache after shelf changes (lightweight optimization for repeated reads on a small free-tier instance).

### Separating ranking, preprocessing, and services

| Layer | Folder | Job |
|-------|--------|-----|
| Algorithms | `preprocess/`, `ranking/` | Pure transforms and scores |
| Orchestration | `services/` | Wire repo + algorithms for one use-case |
| HTTP | `routes/` | Methods, call services, return responses |
| Persistence | `repository/`, `book_data.py` | CSV only |

This matches how the **batch pipeline** already reused `preprocess/` and `ranking/` — the live API now follows the same split.

### Monorepo + deploy alignment

Around the same refactor window:

- Python moved under `backend/` as an installable package (`from backend.X import Y`).
- Render runs from **repo root** with `uvicorn backend.api:app`.
- Frontend on Vercel uses Root Directory `frontend`; production browser calls Render directly (`apiUrl.ts`) after Vercel `/api/*` route handlers proved unreliable in production.

These weren’t aesthetic moves — wrong Root Directory and missing `requirements.txt` caused real build failures.

---

## Render instability (what we actually saw)

Not “Render is bad” — mostly **configuration + free-tier behavior**:

| Symptom | Cause |
|---------|--------|
| `requirements.txt` not found | Render Root Directory set to `backend/` or `frontend/` |
| `Could not import module "api"` | Start command not updated after package move |
| Cold start / slow first request | Free tier spin-down (~15 min idle) |
| Vercel 404 on `/api/books` | Frontend serverless proxy not serving App Router API routes; fixed by direct Render fetch + CORS |

Documented in [deployment.md](../../engineering/deployment.md) and [troubleshooting.md](../../contributors/troubleshooting.md).

---

## Lessons learned


1. **Extract the smallest vertical slice first** — `GET /recommend` was one endpoint, one service file, high learning value, low risk.
2. **Keep algorithms separate from orchestration** — `ranking/` didn’t move; only the workflow moved. No duplicate scoring code.
3. **Deploy config is part of architecture** — monorepo root paths must be documented next to code structure or deploys break silently.
4. **Don’t over-abstract** — no DI container, no extra repository interfaces; `books_repository.py` is a thin wrapper until a second storage backend exists.
5. **Tests follow imports** — after split, mocks must target `backend.routes.books.load_data` or `backend.services.books.get_all_books`, not `backend.api.load_data`.
6. **Public API paths are contracts** — frontend expects `GET /recommend`; refactored router briefly used `/recommendation` and broke discover until aligned.

---

## Next steps

- [ ] Move add / import / PATCH shelf logic from `routes/books.py` → `services/books.py`
- [ ] Delete `backend/api_draft.py` once nothing references it
- [ ] Add devlog entry when persistence moves off ephemeral CSV (Postgres or similar)
- [ ] Optional: wire frontend to call `POST /recommend/refresh` after shelf mutations

See also: [Refactor backlog](../../engineering/architecture.md#refactor-backlog) in system overview.

---

## Related docs

- [System overview](../../engineering/architecture.md)
- [Architecture](../../engineering/architecture.md)
- [ADR-005: Layered backend](../../product/decisions.md#adr-005-layered-backend-routes--services--repository)
