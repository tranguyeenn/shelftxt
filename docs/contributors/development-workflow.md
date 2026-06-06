# Development workflow

Day-to-day guide for working on ShelfTxt — from first clone through pull request. For install commands and env vars, see [development.md](development.md). For repository layout, see [engineering/architecture.md](../engineering/architecture.md).

---

## Quick start

```bash
git clone https://github.com/tranguyeenn/shelftxt.git
cd shelftxt
python3 -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r requirements.txt
python -m unittest discover -s tests -v
uvicorn backend.api:app --reload
```

Optional frontend (separate terminal):

```bash
cd frontend && npm install && npm run dev
```

---

## Branch strategy

| Contributor | Approach |
|-------------|----------|
| **Fork contributors** | Branch from `main` on your fork; open PR to upstream `main` |
| **Maintainer** | Short-lived feature branches or direct commits on `main` for small fixes |

Naming convention (recommended, not enforced):

```text
fix/csv-validation-message
docs/development-workflow
feat/books-pagination
```

Keep branches focused — one logical change per pull request when possible.

---

## Local verification checklist

Run these before opening a PR:

### Backend (required)

```bash
source .venv/bin/activate
python -m unittest discover -s tests -v
```

Optional (if you use pytest locally):

```bash
pip install -r requirements-dev.txt
python -m pytest -q
```

### Frontend (when touching `frontend/`)

```bash
cd frontend
npm run lint          # TypeScript check (tsc --noEmit)
npm run build         # Full production build
```

### Manual smoke (when touching API or UI)

1. Start API: `uvicorn backend.api:app --reload`
2. Open http://127.0.0.1:8000/docs
3. If UI changed: `cd frontend && npm run dev` → http://localhost:3000

---

## Where to put code

```text
HTTP request  →  routes/  →  services/  →  repository/  →  book_data.py  →  CSV
                                  ↘  preprocess/ , ranking/
```

| Change type | Location |
|-------------|----------|
| New or updated endpoint | `backend/routes/` + `backend/services/` |
| Request/response shapes | `backend/schemas/` |
| Ranking or normalization | `backend/preprocess/`, `backend/ranking/` |
| CSV batch ingest (offline) | `backend/ingest/` |
| UI page or feature | `frontend/src/pages/`, `frontend/src/features/` |
| Shared API client | `frontend/src/lib/api.ts` |
| Tests | `tests/test_*.py` |

Do **not** add business logic to route handlers or `backend/api.py` (app shell only).

---

## Documentation updates

Update docs in the same PR when you change behavior, paths, or deploy steps.

| If you changed… | Update… |
|-----------------|---------|
| API paths or payloads | [api.md](../engineering/api.md) |
| Deploy / env vars | [deployment.md](../engineering/deployment.md) |
| Folder responsibilities | [engineering/architecture.md](../engineering/architecture.md) |
| Non-obvious trade-off | [decisions.md](../product/decisions.md) or a [devlog](../history/devlogs) entry |
| Refactor worth remembering | [DEVLOG.md](../../DEVLOG.md) + `docs/history/devlogs/YYYY-MM-DD-*.md` |
| Production incident fix | [troubleshooting.md](troubleshooting.md) |

---

## Pull request process

1. **Open an issue first** for large features, breaking API changes, or storage/auth work.
2. **Fill out** the [PR template](../../.github/PULL_REQUEST_TEMPLATE.md).
3. **Link** related issues (`Fixes #123` when applicable).
4. **Wait for CI** — GitHub Actions runs Python tests and frontend TypeScript checks on push/PR.
5. **Respond to review** — ShelfTxt is solo-maintained; reviews may take time.

### PR scope guidelines

- Prefer diffs under ~400 lines when possible.
- Avoid unrelated refactors in the same PR.
- Do not commit secrets, `.env*`, venvs, or personal `books.csv`.
- Do not modify application behavior when the PR is docs-only or CI-only.

---

## Commit messages

Use imperative, scoped summaries:

```text
docs: add development workflow guide
fix: reject UTF-16 CSV uploads in validation gate
feat: paginate GET /books response
test: cover recommendation empty-state path
```

---

## Continuous integration

CI runs automatically on push and pull request to `main`:

| Workflow | File | What it runs |
|----------|------|--------------|
| Tests | `.github/workflows/tests.yml` | `python -m unittest discover -s tests -v` on Python 3.12 |
| Frontend CI | `.github/workflows/frontend-ci.yml` | `npm run lint` + `npm run build` when `frontend/` changes |

Fix failing CI before requesting review.

---

## Common tasks

### Add a test

1. Add or extend a file under `tests/`.
2. Mock persistence at the service or route boundary (`get_all_books`, `load_data`, etc.).
3. Run `python -m unittest discover -s tests -v`.

### Change a public API field

1. Update Pydantic schema in `backend/schemas/`.
2. Update service logic in `backend/services/`.
3. Update [api.md](../engineering/api.md) and frontend types in `frontend/src/lib/types.ts` if needed.
4. Add or update API tests in `tests/test_api.py`.

### Run the batch ingest pipeline locally

See [pipeline.md](../engineering/import-export.md#batch-pipeline). The live UI import path (`POST /books/import`) is separate from `backend/ingest/`.

---

## Getting help

| Need | Resource |
|------|----------|
| Setup or env issues | [development.md](development.md), [troubleshooting.md](troubleshooting.md) |
| Architecture questions | [engineering/architecture.md](../engineering/architecture.md) |
| Security concerns | [SECURITY.md](../../SECURITY.md) (do not file public issues) |
| Feature direction | [ROADMAP.md](../../ROADMAP.md), open a [feature request](../../.github/ISSUE_TEMPLATE/feature_request.md) |

---

## Related

- [CONTRIBUTING.md](../../CONTRIBUTING.md) — contributor entry point
- [contributing.md](contributing.md) — conventions and doc-update table
- [repository-audit.md](../history/audits/repository-audit.md) — known gaps and improvement backlog
