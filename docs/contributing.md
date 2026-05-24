# Contributing

Shelftxt is a small monorepo maintained for learning and personal use. These conventions keep the codebase readable as it grows.

---

## Prerequisites

- Python 3.14+ (see `requirements.txt`)
- Node.js 20+ (for `frontend/`)
- Git

Setup: [development.md](development.md).

---

## Project conventions

### Backend (`backend/`)

| Do | Don't |
|----|--------|
| Put orchestration in `services/` | Put ranking math in routes |
| Keep CSV I/O in `book_data.py` | Call `load_data()` from `ranking/` |
| Import as `from backend.X import Y` | Import from repo root without package prefix |
| Use plain functions | Add DI frameworks unless truly needed |

**Layer flow:** `routes → services → book_data / preprocess / ranking`

### Frontend (`frontend/`)

| Do | Don't |
|----|--------|
| Use `apiUrl()` for browser fetches in `page.tsx` | Hardcode Render URL in components |
| Keep types near `page.tsx` until shared | Create abstraction layers for one use |
| Match API column names (`"Read Status"`) | Rename API fields in the client only |

### Tests

- Run before PR: `./.venv/bin/python -m unittest discover -s tests -v`
- Mock persistence at `backend.api.*` for route tests
- Mock `services.recommendation.*` when testing recommendation pipeline in isolation

### Docs

Update docs when you change:

- Deploy commands or env vars → `deployment.md`, `development.md`
- API shape → `api.md`, `data-model.md`
- Scoring behavior → `ranking.md`
- Non-obvious trade-off → `decisions.md`

---

## Pull request checklist

- [ ] Functionality unchanged or intentionally documented
- [ ] Tests pass locally
- [ ] No secrets in diff (`.env.local`, API keys)
- [ ] `backend/data/processed/books.csv` not committed
- [ ] Relevant doc updated (or N/A noted in PR)
- [ ] Pyright/lint clean on touched files (if applicable)

---

## Commit messages

Prefer imperative, scoped summaries:

```txt
Add root api.py shim for Render uvicorn api:app
Extract GET /recommend into services/recommendation.py
Fix Vercel production fetch via apiUrl helper
```

---

## Refactor roadmap (optional context)

Not blocking contributions — documented in [architecture.md](architecture.md):

1. ~~`GET /recommend` → service~~ (done)
2. Delete + add + import → `services/books.py`
3. Pydantic models → `backend/schemas/`
4. Routes → `backend/routes/`
5. `PATCH /books` shelf state machine → service (largest)

One endpoint per change; keep PRs reviewable.

---

## Related

- [architecture.md](architecture.md)
- [decisions.md](decisions.md)
- [troubleshooting.md](troubleshooting.md)
