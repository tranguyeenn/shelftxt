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
uvicorn api:app --reload
```

Or without activating:

```bash
.venv/bin/uvicorn api:app --reload
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

Interactive menu: mark finished, mark DNF, add TBR. Shares `data/processed/books.csv` with the API.

## Tests

```bash
./venv/bin/python -m unittest discover -s test -v
```

| File | Coverage |
|------|----------|
| `test/test_api.py` | FastAPI routes (mocked persistence) |
| `test/test_flexible_pipeline.py` | Ingest, validation, ranking |

## Data directories

| Path | Git | Purpose |
|------|-----|---------|
| `data/raw/` | tracked (`.gitkeep`) | Optional staging for user CSV exports |
| `data/processed/books.csv` | gitignored | Live library file |

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

**Procfile:**

```txt
web: uvicorn api:app --host 0.0.0.0 --port $PORT
```

**Keep-warm:** `api.py` lifespan starts `AsyncIOScheduler` pinging `https://librorank.onrender.com/health` every 14 minutes. Update the URL if you deploy under a different hostname.

**CORS origins** in `api.py`: localhost dev hosts + production frontend URL.

### Persistence warning

Free/ephemeral disks on PaaS may reset `books.csv` on redeploy or spin-down. For production libraries, plan persistent disk or external storage.

## Project layout (reference)

```txt
libroRank/
├── api.py
├── book_data.py
├── ingest/
├── preprocess/
├── ranking/
├── cli/
├── test/
├── frontend/
├── data/
├── docs/          ← this folder
└── Procfile
```

## Related docs

- [architecture.md](architecture.md)
- [api.md](api.md)
- [pipeline.md](pipeline.md)
