# Development & operations

## Requirements

- Python 3 (project tested with 3.14-compatible deps in `requirements.txt`)
- Node.js for frontend

### Python dependencies

```txt
fastapi
uvicorn
pandas
numpy
python-multipart
httpx
apscheduler
```

Install (from repo root):

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## Running locally

### API

Use the project venv so dependencies (e.g. `apscheduler`) are on the path:

```bash
source .venv/bin/activate
uvicorn backend.api:app --reload
```

Or without activating:

```bash
.venv/bin/uvicorn backend.api:app --reload
```

- http://127.0.0.1:8000
- Swagger: http://127.0.0.1:8000/docs

If you see `ModuleNotFoundError: No module named 'apscheduler'`, the shell is using system Python — stop the server and run uvicorn via `.venv/bin/` as above.

### Frontend

```bash
cd frontend && npm install && npm run dev
# http://localhost:3000
```

### CLI

```bash
python -m cli.manage_books
```

Interactive menu: mark finished, mark DNF, add TBR. Shares `backend/data/processed/books.csv` with the API.

## Tests

```bash
./.venv/bin/python -m unittest discover -s tests -v
```

| File | Coverage |
|------|----------|
| `tests/test_api.py` | FastAPI routes (mocked persistence) |
| `tests/test_flexible_pipeline.py` | Ingest, validation, ranking |

## Data directories

| Path | Git | Purpose |
|------|-----|---------|
| `backend/data/raw/` | tracked (`.gitkeep`) | Optional staging for user CSV exports |
| `backend/data/processed/books.csv` | gitignored | Live library file |

First API/CLI access creates an empty `books.csv` with correct headers.

## Environment variables

| Variable | Where | Purpose |
|----------|-------|---------|
| `API_BASE_URL` | frontend | Backend URL for server-side proxy |
| `NEXT_PUBLIC_API_BASE_URL` | frontend | Alternate override |
| `PORT` | Render | Injected port for uvicorn |
| `NODE_ENV` | Next.js | `development` selects local API default |

Example `frontend/.env.local`:

```bash
API_BASE_URL=https://your-api.example.com
```

## Deployment (Render)

### Python API service settings

`requirements.txt` and `Procfile` live at the **repo root**. After the `backend/` refactor, Render must **not** use `backend` or `frontend` as Root Directory for the API.

| Setting | Value |
|---------|-------|
| **Root Directory** | *(leave empty)* |
| **Build Command** | `pip install -r requirements.txt` |
| **Start Command** | `uvicorn backend.api:app --host 0.0.0.0 --port $PORT` |

(`uvicorn api:app` also works via the root `api.py` shim if your Render service still uses the old command.)

Or rely on the root `Procfile` (same start command) with an empty Root Directory.

**`ModuleNotFoundError: requirements.txt` during build** — Root Directory is set to a subfolder (e.g. `backend` or `frontend`). Clear it and redeploy.

**Frontend on Render** is a separate service: Root Directory = `frontend`, build = `npm install && npm run build`, start = `npm start` (or your Next.js start command). Do not use `pip install -r requirements.txt` on the frontend service.

Optional: [`render.yaml`](../render.yaml) at repo root documents the API service for Blueprint deploys.

**Procfile:**

```txt
web: uvicorn backend.api:app --host 0.0.0.0 --port $PORT
```

**Keep-warm:** `backend/api.py` lifespan starts `AsyncIOScheduler` pinging `https://shelftxt.onrender.com/health` every 14 minutes.

**CORS origins** in `backend/api.py`: localhost dev hosts + production frontend URL.

### Persistence warning

Free/ephemeral disks on PaaS may reset `books.csv` on redeploy or spin-down. For production libraries, plan persistent disk or external storage.

## Project layout (reference)

```txt
shelftxt/
├── backend/
│   ├── api.py
│   ├── book_data.py
│   ├── routes/
│   ├── services/
│   ├── schemas/
│   ├── preprocess/
│   ├── ranking/
│   ├── ingest/
│   └── data/
├── cli/
├── tests/
├── frontend/
├── docs/
└── Procfile
```

## Related docs

- [architecture.md](architecture.md)
- [api.md](api.md)
- [pipeline.md](pipeline.md)
