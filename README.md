# shelftxt

![Open Source](https://img.shields.io/badge/Open%20Source-Yes-green)
![Python](https://img.shields.io/badge/Python-3.x-blue)
![FastAPI](https://img.shields.io/badge/FastAPI-backend-teal)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Tests](https://github.com/tranguyeenn/shelftxt/actions/workflows/tests.yml/badge.svg)](https://github.com/tranguyeenn/shelftxt/actions/workflows/tests.yml)

Shelftxt is an open-source backend-driven recommendation system for organizing and ranking books in a TBR list. Built to explore recommendation logic, data pipelines, backend architecture, and scalable systems.

**Live:** [shelftxt.vercel.app](https://shelftxt.vercel.app) · **API docs:** [shelftxt.onrender.com/docs](https://shelftxt.onrender.com/docs)

---

## Overview

Shelftxt exposes a FastAPI service over a PostgreSQL-backed book CRUD API, with CSV import/export compatibility. A Vite + React UI and CLI share the same data model. Recommendation scoring runs in Python (`preprocess/` + `ranking/`) with transparent, inspectable logic—not a black-box API.

The project is maintained in the open: architecture notes, ADRs, and [devlogs](docs/history/devlogs/) document how the backend evolves.

---

## Features

- **Shelf management** — want-to-read, reading (progress %), read (ratings), DNF
- **TBR ranking** — `GET /recommend` scores your to-read list from read-history author preferences
- **REST API** — OpenAPI at `/docs`; Pydantic schemas in `backend/schemas/`
- **CSV import** — bulk add via `POST /books/import`; duplicates skipped and stored through PostgreSQL-backed routes
- **Batch ingest pipeline** — map external exports to a canonical schema ([pipeline docs](docs/engineering/import-export.md#batch-pipeline))
- **CLI** — `python -m cli.manage_books` for local shelf edits

CSV export remains available for backups and spreadsheet workflows.

---

## Tech stack

| Layer | Stack |
|-------|--------|
| **API** | Python, FastAPI, uvicorn, pandas |
| **Ranking** | Custom scoring in `backend/ranking/`, features in `backend/preprocess/` |
| **Persistence** | PostgreSQL for book CRUD (`backend/db/` + `backend/repository/postgres_books_repository.py`) |
| **UI** | Vite, React, TypeScript |
| **Deploy** | Render (API), Vercel (frontend) |

---

## Architecture

```text
HTTP → routes/ → services/ → repository/ → SQLAlchemy → PostgreSQL
                    ↘ preprocess/ + ranking/  (no I/O)
```

| Layer | Role |
|-------|------|
| `backend/api.py` | App shell: CORS, lifespan, router registration |
| `routes/` | HTTP only — parse request, call services |
| `services/` | Business logic (shelves, recommendations) |
| `repository/` | Persistence layer for PostgreSQL-backed book CRUD |
| `schemas/` | Pydantic request/response models |
| `ingest/` | Offline CSV pipeline (not live UI import) |

Deeper docs: [documentation index](./docs/README.md) · [architecture](./docs/engineering/architecture.md) · [decisions](./docs/product/decisions.md)

---

## Local setup

### Backend (required for API work)

PostgreSQL is the primary storage backend for book CRUD data. Local development uses Docker Compose to run PostgreSQL, SQLAlchemy for database access, and Alembic for schema migrations.

```bash
git clone https://github.com/tranguyeenn/shelftxt.git
cd shelftxt
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
docker compose up -d
docker compose ps
alembic upgrade head
uvicorn backend.api:app --reload
```

- API: http://127.0.0.1:8000  
- Swagger: http://127.0.0.1:8000/docs  

Run commands from the **repo root** so `backend` resolves as a package.

#### Prerequisites

- Python 3
- Docker and Docker Compose
- Local PostgreSQL through `docker compose`

#### Environment

Copy the example environment file, then adjust values if your local database differs:

```bash
cp .env.example .env
```

Required variable:

```env
DATABASE_URL=postgresql+psycopg://shelftxt:shelftxt_dev_password@localhost:5432/shelftxt
```

#### Database commands

Start PostgreSQL and check the container:

```bash
docker compose up -d
docker compose ps
```

Install dependencies and apply migrations:

```bash
pip install -r requirements.txt
alembic upgrade head
```

Reset the local database from scratch:

```bash
docker compose down -v
docker compose up -d
alembic upgrade head
```

#### Migrating old CSV data

After PostgreSQL is running and migrations have been applied, migrate an existing ShelfTxt CSV into PostgreSQL:

```bash
python -m backend.scripts.migrate_csv_to_postgres --csv backend/data/processed/books.csv
```

The `--csv` option is optional; when omitted, the script uses `backend/data/processed/books.csv`. Imported rows are stored in PostgreSQL. The migration skips duplicate rows when the `ISBN/UID` or title already exists, and reports imported, duplicate, and invalid row counts.

#### CSV compatibility

CSV is no longer the primary storage mechanism for book CRUD. CSV import and export remain supported for backups, spreadsheet workflows, and compatibility:

- `POST /books/import` imports parsed rows into PostgreSQL and skips duplicate titles.
- `GET /books/export` exports the current PostgreSQL library as `shelftxt-library.csv`.

### Frontend (optional)

```bash
cd frontend && npm install && npm run dev
```

Open http://localhost:3000. See [docs/contributors/development.md](docs/contributors/development.md) for env vars and remote API mode.

### Tests

```bash
pytest
```

If `pytest` is not installed in your active environment:

```bash
pip install -r requirements-dev.txt
python -m pytest
```

`python -m unittest discover -s tests -v` is also supported.

---

## API routes

| Method | Path | Description |
|--------|------|-------------|
| `GET` / `HEAD` | `/health` | Health check |
| `GET` | `/books` | List library (paginated: `?page=1&limit=20`) |
| `POST` | `/books` | Add book (TBR) |
| `PATCH` | `/books` | Update / move shelf |
| `PATCH` | `/books/{id}/progress` | Update status and pages read |
| `GET` | `/books/export` | Download library CSV |
| `POST` | `/books/clear` | Clear entire library |
| `POST` | `/books/import` | Bulk import |
| `DELETE` | `/books/{id}` | Delete by book id |
| `GET` | `/recommend?style=` | Top 10 TBR suggestions |

Full reference: [docs/engineering/api.md](docs/engineering/api.md) · [Documentation index](docs/README.md)

---

## Roadmap

See [ROADMAP.md](ROADMAP.md) for current capabilities and planned work (remaining PostgreSQL follow-up, caching, auth, analytics).

Engineering history: [DEVLOG.md](DEVLOG.md) · [docs/history/devlogs/](docs/history/devlogs/)

---

## Documentation

Backend services and repository functions include docstrings where helpful. See `backend/services/` and `backend/repository/` for inline notes.

---

## Contributing

Shelftxt is open source and contributions, bug reports, discussions, and feature ideas are welcome.

See [CONTRIBUTING.md](CONTRIBUTING.md) for development guidelines.

Use GitHub templates under `.github/` for bugs and pull requests.

---

## License

MIT — see [LICENSE](LICENSE).

Additional docs: [docs/README.md](docs/README.md) · [User research](docs/product/user-research/README.md) · [SECURITY.md](SECURITY.md) · [CHANGELOG.md](CHANGELOG.md)
