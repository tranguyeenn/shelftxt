# Shelftxt devlog

## Purpose

A **devlog** is an engineering journal: short, dated write-ups of what changed, why it changed, and what you learned. Unlike API reference docs (what the system *is*), devlogs capture how the system *evolved* — refactors, deploy incidents, architecture bets, and dead ends worth remembering.

This file is the **index**. Detailed entries live in [`docs/history/devlogs/`](docs/history/devlogs/).

---

## Major entries

| Date | Title | Summary |
|------|-------|---------|
| 2026-05-30 | [Weekly foundation work](docs/history/devlogs/2026-05-30-weekly-foundation-work.md) | Exception handling, docs expansion, pagination, recommendation tests, demo mode, Postgres planning |
| 2026-05-24 | [Refactoring shelftxt backend](docs/history/devlogs/2026-05-24-backend-refactor.md) | Layered backend: routes, services, repository; recommendation extracted from monolithic API; Render + Vercel deploy fixes |

---

## Recent refactors

- **Foundation week (2026-05-30)** — Narrower exception handling, paginated `GET /books`, system-design docs, recommendation test coverage, demo-mode banner; planning Postgres + per-user libraries.
- **Backend layering** — `backend/api.py` is now an app shell; HTTP lives in `routes/`, logic in `services/`, CSV access via `repository/` + `book_data.py`.
- **Recommendation pipeline** — `GET /recommend` orchestration moved to `services/recommendation.py`; ranking math stays in `ranking/` and `preprocess/`.
- **Monorepo layout** — Python app under `backend/`; Render runs from repo root; Vercel Root Directory = `frontend`.
- **Production connectivity** — Frontend on Vercel calls Render directly (`apiUrl.ts`); CORS updated for `shelftxt.vercel.app`.

---

## How to add an entry

1. Copy the template in [`docs/history/devlogs/README.md`](docs/history/devlogs/README.md).
2. Create `docs/history/devlogs/YYYY-MM-DD-short-title.md`.
3. Add a row to the **Major entries** table above.
4. Optionally add a one-line bullet under **Recent refactors**.

**Open refactor backlog:** [engineering/architecture.md#refactor-backlog](docs/engineering/architecture.md#refactor-backlog)

See also: [Architecture overview](docs/engineering/architecture.md) · [Technical docs index](docs/README.md)
