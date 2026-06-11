# Development & Operations

Local setup and day-to-day commands. For production deployment, see [deployment.md](engineering/deployment.md).

## Current Storage Status

ShelfTxt still uses CSV storage as the active production storage layer.

Live application data is stored at:

```txt
backend/data/processed/books.csv
```

The PostgreSQL migration is in progress. PostgreSQL infrastructure and the initial SQLAlchemy foundation have been added, but routes and repositories do not use PostgreSQL yet. CSV storage has not been removed.

## Requirements

* Python 3.12+
* Node.js 20+
* Docker Desktop, or another Docker Compose-compatible runtime, for local PostgreSQL development

---

## Install Python Dependencies

From the repository root:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### Database Migration Dependencies

The PostgreSQL migration stack is installed through `requirements.txt`:

| Dependency | Purpose |
| --- | --- |
| `SQLAlchemy` | ORM and database engine/session foundation |
| `psycopg[binary]` | PostgreSQL driver used by SQLAlchemy |
| `Alembic` | Database migration tooling dependency; migrations are not initialized yet |
| `python-dotenv` | Loads local environment variables from `.env` |

---

## Database Development Setup

PostgreSQL is available for local migration work through Docker Compose. It is not the active runtime storage layer for routes, services, repositories, the CLI, or production data yet.

### Environment Variables

Create a local `.env` file in the repository root:

```bash
cp .env.example .env
```

Required backend environment variables:

| Variable | Purpose | Local development value |
| --- | --- | --- |
| `DATABASE_URL` | SQLAlchemy PostgreSQL connection string for migration work | `postgresql+psycopg://shelftxt:shelftxt_dev_password@localhost:5432/shelftxt` |

`.env` files are gitignored. `.env.example` is committed as the local development template.

### Start PostgreSQL

From the repository root:

```bash
docker compose up -d
```

Verify the container is running:

```bash
docker compose ps
```

Expected local service:

```txt
shelftxt-postgres
```

### Connect to PostgreSQL with psql

Use `psql` inside the running container:

```bash
docker exec -it shelftxt-postgres psql -U shelftxt -d shelftxt
```

Exit `psql`:

```sql
\q
```

### Local Database Credentials

These values are defined in `docker-compose.yml`:

| Setting | Value |
| --- | --- |
| Host | `localhost` |
| Port | `5432` |
| Database | `shelftxt` |
| Username | `shelftxt` |
| Password | `shelftxt_dev_password` |

---

## Database Layer

The initial SQLAlchemy foundation has been added for the PostgreSQL migration.

Current database files:

| File | Purpose |
| --- | --- |
| `backend/db/database.py` | Loads `.env`, reads `DATABASE_URL`, creates the SQLAlchemy engine, configures `SessionLocal`, defines `Base`, and provides `get_db()` |
| `backend/db/models.py` | Defines the initial `Book` SQLAlchemy model |

Current database foundation:

* `load_dotenv()` loads local environment variables.
* `DATABASE_URL` is required by `backend/db/database.py`.
* `create_engine(DATABASE_URL)` configures the SQLAlchemy engine.
* `SessionLocal` is configured with `autocommit=False`, `autoflush=False`, and the shared engine.
* `get_db()` yields a SQLAlchemy `Session` and closes it after use.
* `Base` uses SQLAlchemy `DeclarativeBase`.
* `Book` maps to the `books` table with fields for title, author, genre, status, rating, pages, and date strings.

Important current limitations:

* API routes do not use PostgreSQL yet.
* Repositories do not use PostgreSQL yet.
* Alembic migrations are not initialized yet.
* No migration scripts have been added.
* CSV remains the active production storage layer.

---

## PostgreSQL Migration Progress

Completed migration phases:

### Phase 1: Local PostgreSQL Infrastructure

* Added Docker Compose configuration.
* Added local PostgreSQL container using `postgres:16`.
* Added `.env` support.
* Added `DATABASE_URL`.
* Added `.env.example`.
* Updated `.gitignore` for local environment files.

### Phase 2: Database Dependencies

* Added SQLAlchemy.
* Added psycopg.
* Added Alembic.
* Added python-dotenv.
* Updated `requirements.txt`.

### Phase 3: SQLAlchemy Foundation

* Added `backend/db/database.py`.
* Added `backend/db/models.py`.
* Configured the SQLAlchemy engine.
* Configured `SessionLocal`.
* Implemented `get_db()`.
* Added the initial `Book` SQLAlchemy model.

The migration is not complete. The next phases still need to connect application persistence to PostgreSQL and define migration management.

---

## Running Locally

### API

```bash
source .venv/bin/activate
uvicorn backend.api:app --reload
```

Available at:

* http://127.0.0.1:8000
* Swagger UI: http://127.0.0.1:8000/docs

Legacy entrypoint:

```bash
uvicorn api:app --reload
```

### Frontend

```bash
cd frontend
npm install
npm run dev
```

Open:

```txt
http://localhost:3000
```

### Backend Target Configuration

| Mode | Config | Browser Calls |
| --- | --- | --- |
| Local API default | None | `/api/*` through the Vite proxy to `127.0.0.1:8000` |
| Remote API | `frontend/.env.local` | Direct requests to deployed API |

Create local frontend environment variables:

```bash
cp frontend/.env.local.example frontend/.env.local
```

Restart the frontend after modifying environment variables.

### CLI

```bash
python -m cli.manage_books
```

The CLI currently shares the CSV storage layer with the API.

---

## Testing

Run all tests:

```bash
./.venv/bin/python -m unittest discover -s tests -v
```

### Test Coverage

| File | Coverage |
| --- | --- |
| `tests/test_api.py` | API routes and services |
| `tests/test_flexible_pipeline.py` | Ingest, validation, ranking pipeline |
| `tests/test_recommendation_builder.py` | Recommendation response construction |
| `tests/test_score.py` | Ranking score helpers |

See:

* [architecture.md](engineering/architecture.md)
* [contributing.md](contributors/contributing.md)

for development workflow and architecture guidelines.

---

## Data Storage

### Current Storage

ShelfTxt currently uses:

```txt
backend/data/processed/books.csv
```

for live application data.

### Data Directories

| Path | Git Status | Purpose |
| --- | --- | --- |
| `backend/data/raw/` | Tracked with `.gitkeep` | Optional CSV staging |
| `backend/data/processed/books.csv` | Gitignored | Live library storage |

The API and CLI automatically create an empty `books.csv` if one does not exist.

---

## Environment Variables

### Backend

| Variable | Purpose |
| --- | --- |
| `DATABASE_URL` | PostgreSQL connection string for migration work |

### Frontend

| Variable | Purpose |
| --- | --- |
| `VITE_API_BASE_URL` | Override backend API URL |

Full deployment configuration:

[deployment.md](engineering/deployment.md#environment-variable-reference)

---

## Deployment

Production deployment documentation:

* [deployment.md](engineering/deployment.md)

Troubleshooting:

* [troubleshooting.md](contributors/troubleshooting.md)

---

## Related Documentation

* [architecture.md](engineering/architecture.md)
* [api.md](engineering/api.md)
* [import-export.md](engineering/import-export.md#batch-pipeline)
* [postgres-migration-audit.md](engineering/postgres-migration-audit.md)
* [decisions.md](product/decisions.md)
