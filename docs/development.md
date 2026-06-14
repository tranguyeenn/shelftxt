# Development & Operations

Local setup and day-to-day commands. For production deployment, see [deployment.md](engineering/deployment.md).

## Current Storage Status

ShelfTxt now uses PostgreSQL as the primary storage backend for book CRUD operations.

The active book CRUD path is:

```txt
Route -> Service -> Repository -> SQLAlchemy -> PostgreSQL
```

The PostgreSQL migration is complete for book CRUD. Routes use database session injection through `get_db()` and call the PostgreSQL-backed service/repository layer. CSV support remains for import/export compatibility and migration workflows; CSV is no longer the source of truth for book CRUD routes.

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
| `Alembic` | Database migration tooling used to recreate schema changes in a repeatable way |
| `python-dotenv` | Loads local environment variables from `.env` |

---

## Database Development Setup

PostgreSQL is available for local development through Docker Compose and is the active storage layer for book CRUD routes.

### Environment Variables

Create a local `.env` file in the repository root:

```bash
cp .env.example .env
```

Required backend environment variables:

| Variable | Purpose | Local development value |
| --- | --- | --- |
| `DATABASE_URL` | SQLAlchemy PostgreSQL connection string for book CRUD | `postgresql+psycopg://shelftxt:shelftxt_dev_password@localhost:5432/shelftxt` |

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

### Stop PostgreSQL

Stop the local database container without deleting the volume:

```bash
docker compose down
```

### Reset PostgreSQL

Delete the local PostgreSQL volume, recreate the container, and rebuild the schema:

```bash
docker compose down -v
docker compose up -d
alembic upgrade head
```

To reload legacy CSV data after a reset:

```bash
python -m backend.scripts.migrate_csv_to_postgres --csv backend/data/processed/books.csv
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

The SQLAlchemy foundation is used by the PostgreSQL-backed book CRUD API.

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
* `Book` maps to the `books` table with fields for title, authors, stable external id, status, rating, pages, progress, and date values.

---

## Alembic Migrations

Alembic is used to manage database schema changes. A schema is the structure of the database, such as which tables exist and which columns each table has.

Instead of creating tables by hand every time, Alembic stores schema changes in migration files. These files make database setup reproducible: a developer can start with an empty PostgreSQL database and run the migrations to create the same tables.

Current Alembic migration work:

* Alembic has been initialized.
* Alembic is connected to SQLAlchemy metadata.
* The initial migration has been generated.
* The initial migration has been applied to local PostgreSQL.
* The `books` table has been created.
* The `alembic_version` table has been created.
* Schema creation was verified directly through PostgreSQL.

The `alembic_version` table is managed by Alembic. It records which migration has been applied so Alembic knows the current database version.

### Run Migrations

Apply all migrations from the repository root after PostgreSQL is running:

```bash
alembic upgrade head
```

### Create a Migration

After changing SQLAlchemy models in `backend/db/models.py`, generate a migration:

```bash
alembic revision --autogenerate -m "describe schema change"
```

Review the generated file in `alembic/versions/`, then apply it:

```bash
alembic upgrade head
```

---

## Repository Layer

The repository layer is responsible for database operations. It acts as a bridge between application code and the database.

Application code should not need to know the details of SQLAlchemy queries. Instead, it can call repository functions such as "get all books" or "create a book." The repository handles the database session and the SQLAlchemy model operations.

Current repository file:

| File | Purpose |
| --- | --- |
| `backend/repository/postgres_books_repository.py` | Provides CRUD operations for `Book` records in PostgreSQL |

Implemented repository operations:

* `get_all_books()`
* `get_book_by_id()`
* `create_book()`
* `update_book()`
* `delete_book()`

CRUD means create, read, update, and delete. These are the basic operations needed to manage records in a database.

The repository CRUD operations are used by book CRUD routes through `backend/services/postgres_books.py`.

---

## Storage Architecture

PostgreSQL is the source of truth for book CRUD operations.

| Layer | File | Responsibility |
| --- | --- | --- |
| Database setup | `backend/db/database.py` | Loads `.env`, reads `DATABASE_URL`, creates the SQLAlchemy engine, configures `SessionLocal`, defines `Base`, and provides `get_db()` |
| Models | `backend/db/models.py` | Defines SQLAlchemy models, including the `Book` model mapped to the `books` table |
| Repository | `backend/repository/postgres_books_repository.py` | Isolates SQLAlchemy queries and CRUD operations |
| Services | `backend/services/postgres_books.py` | Applies book business rules while preserving API response shapes |
| Routes | `backend/routes/books.py` | Handles HTTP requests and injects database sessions |

Routes and services should not directly manipulate CSV files for primary book storage. CSV paths are compatibility boundaries for import, export, offline ingest, and migration utilities.

## CSV Migration and Compatibility

### Migrate Legacy CSV Data

Run this after `docker compose up -d` and `alembic upgrade head`:

```bash
python -m backend.scripts.migrate_csv_to_postgres --csv backend/data/processed/books.csv
```

The `--csv` option is optional; the default path is `backend/data/processed/books.csv`. Imported rows are written to PostgreSQL. The migration utility skips duplicates by existing `ISBN/UID` or title, skips invalid rows, and prints a summary.

### Import and Export

CSV remains supported for compatibility:

* `POST /books/import` accepts parsed CSV rows from the frontend, creates PostgreSQL rows, and skips duplicate titles.
* `GET /books/export` returns the current PostgreSQL library as CSV.
* The offline ingest pipeline in `backend/ingest/` can process external CSV schemas, but it does not replace PostgreSQL as the app storage backend.

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

The CLI may still use the legacy CSV helper path. Prefer the API for PostgreSQL-backed CRUD behavior.

---

## Testing

Run all tests:

```bash
pytest
```

If `pytest` is not available in the active environment, install development dependencies with `pip install -r requirements-dev.txt`.

The unittest runner is also supported:

```bash
python -m unittest discover -s tests -v
```

### Test Coverage

| File | Coverage |
| --- | --- |
| `tests/test_api.py` | API routes and services |
| `tests/test_flexible_pipeline.py` | Ingest, validation, ranking pipeline |
| `tests/test_recommendation_builder.py` | Recommendation response construction |
| `tests/test_score.py` | Ranking score helpers |

DB-backed behavior should be tested through routes/services using database sessions or explicit test doubles. Keep CSV-specific tests focused on import/export compatibility and offline ingest behavior.

See:

* [architecture.md](engineering/architecture.md)
* [contributing.md](contributors/contributing.md)

for development workflow and architecture guidelines.

---

## Data Storage

### Current Storage

ShelfTxt currently uses PostgreSQL for book CRUD operations. CSV remains available for export/import compatibility and local migration-adjacent workflows.

### Data Directories

| Path | Git Status | Purpose |
| --- | --- | --- |
| `backend/data/raw/` | Tracked with `.gitkeep` | Optional CSV staging |
| `backend/data/processed/books.csv` | Gitignored | Legacy CSV/import-export compatibility data |

Legacy CSV helpers may create an empty `books.csv` if one does not exist.

---

## Environment Variables

### Backend

| Variable | Purpose |
| --- | --- |
| `DATABASE_URL` | PostgreSQL connection string for SQLAlchemy-backed book CRUD |

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
