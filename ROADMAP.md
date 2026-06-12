# Roadmap

Engineering directions for shelftxt — not fixed release dates. See [DEVLOG.md](DEVLOG.md) for completed work.

---

## Current

- FastAPI backend
- Recommendation scoring (`preprocess/` + `ranking/`)
- PostgreSQL-backed book CRUD through repository layer
- PostgreSQL migration phases 1-7 complete
- Open-source docs (CONTRIBUTING, templates, CI tests)
- Vite + React UI and batch ingest pipeline

---

## Planned

- PostgreSQL follow-up work for remaining CSV-adjacent paths
- Repository pattern improvements
- Caching improvements
- Better recommendation engine
- Serverless deployment exploration
- Auth
- Reading analytics

---

## How to suggest changes

Open a [feature request](.github/ISSUE_TEMPLATE/feature_request.md) with the problem and a proposed approach. Small PRs are easier to review than sweeping refactors.
