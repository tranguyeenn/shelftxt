# Development & operations

Local setup and day-to-day commands. For production deploy, see [deployment.md](deployment.md).

## Requirements

- Python 3.14+ (see `requirements.txt`)
- Node.js 20+ for frontend

### Install Python deps

From repo root:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

---

## Running locally

### API

```bash
source .venv/bin/activate
uvicorn backend.api:app --reload
```

- http://127.0.0.1:8000
- Swagger: http://127.0.0.1:8000/docs

Legacy: `uvicorn api:app --reload` via root shim.

### Frontend

```bash
cd frontend && npm install && npm run dev
```

Open http://localhost:3000.

**Backend target in dev:**

| Mode | Config | Browser calls |
|------|--------|---------------|
| Local API (default) | none | `/api/*` → Next proxy → `127.0.0.1:8000` |
| Remote API only | `frontend/.env.local` with `API_BASE_URL=https://shelftxt.onrender.com` | `/api/*` → Render |

Copy [`frontend/.env.local.example`](../frontend/.env.local.example) to get started.

Restart `npm run dev` after env changes.

### CLI

```bash
python -m cli.manage_books
```

Shares `backend/data/processed/books.csv` with the API.

---

## Tests

```bash
./.venv/bin/python -m unittest discover -s tests -v
```

| File | Coverage |
|------|----------|
| `tests/test_api.py` | FastAPI routes (mocked persistence) |
| `tests/test_flexible_pipeline.py` | Ingest, validation, ranking |

See [contributing.md](contributing.md) for conventions.

---

## Data directories

| Path | Git | Purpose |
|------|-----|---------|
| `backend/data/raw/` | tracked (`.gitkeep`) | Optional CSV staging |
| `backend/data/processed/books.csv` | gitignored | Live library |

First API/CLI access creates empty `books.csv` with correct headers.

---

## Environment variables (local)

| Variable | File | Purpose |
|----------|------|---------|
| `API_BASE_URL` | `frontend/.env.local` | Next.js server proxy target (dev) |
| `NEXT_PUBLIC_API_BASE_URL` | `frontend/.env.local` | Optional; forces client URL in dev builds |

Full reference: [deployment.md#environment-variable-reference](deployment.md#environment-variable-reference).

---

## Deployment

Production runbook (Render + Vercel): **[deployment.md](deployment.md)**

Issues: **[troubleshooting.md](troubleshooting.md)**

---

## Related docs

- [architecture.md](architecture.md)
- [api.md](api.md)
- [pipeline.md](pipeline.md)
- [decisions.md](decisions.md)
