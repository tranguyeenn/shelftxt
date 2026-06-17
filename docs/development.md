# Development & Operations

Local setup and day-to-day commands. For production deployment, see [deployment.md](engineering/deployment.md).

## Current Storage Status

ShelfTxt now uses PostgreSQL as the primary storage backend for profiles and user-owned book CRUD operations. Supabase provides registration, login, persisted sessions, and backend token verification.

The active book CRUD path is:

```txt
Supabase session -> Route -> Service -> Repository -> SQLAlchemy -> PostgreSQL
```

During Supabase Auth integration testing, the final PostgreSQL hop must be the same database that contains the Supabase-backed `public.profiles` rows. Local Docker Postgres is useful for isolated backend work, but it will not automatically contain profiles created by hosted Supabase Auth.

The PostgreSQL migration is complete for book CRUD. Routes use database session injection through `get_db()`, validate the current Supabase user through `get_current_user()`, and call the PostgreSQL-backed service/repository layer with that user id. CSV support remains for import/export compatibility and migration workflows; CSV is no longer the source of truth for book CRUD routes.

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
| `DATABASE_URL` | SQLAlchemy PostgreSQL connection string for profiles and book CRUD | Supabase Postgres for auth integration tests; local Docker Postgres for isolated backend work |
| `SUPABASE_URL` | Supabase project URL used by the backend auth dependency | `https://your-project.supabase.co` |
| `SUPABASE_ANON_KEY` | Supabase anon/publishable key used as the `/auth/v1/user` API key while validating incoming user tokens | Same project as `SUPABASE_URL` |
| `SUPABASE_SERVICE_ROLE_KEY` | Server-only key for admin/server-side Supabase operations | Supabase service role key |

`.env` files are gitignored. `.env.example` is committed as the local development template.

Do not put `SUPABASE_SERVICE_ROLE_KEY` in frontend environment files.

### Supabase Auth integration database

The frontend creates `profiles` rows through the Supabase browser client, so those rows are stored in the Supabase project configured by `VITE_SUPABASE_URL`. The backend validates the JWT with `SUPABASE_URL`, then queries `profiles` through SQLAlchemy using `DATABASE_URL`.

For end-to-end local auth testing:

* `SUPABASE_URL` and `VITE_SUPABASE_URL` must refer to the same Supabase project.
* `DATABASE_URL` must point to that project's Postgres database, where `public.profiles` lives.
* Keep `SUPABASE_SERVICE_ROLE_KEY` backend-only. Use the frontend anon/publishable key in `frontend/.env.local`.

Local Docker Postgres is valid only when the `profiles` table in that local database contains rows whose `id` values match the Supabase auth user UUIDs in your test tokens.

### Troubleshooting `User profile not found`

**Error:** `{"detail":"User profile not found"}`

**Cause:** The Supabase Auth user exists and the JWT is valid, but the backend database named by `DATABASE_URL` does not contain a matching `profiles.id`.

**Fix:** Point backend `DATABASE_URL` to the same Supabase Postgres database where the frontend creates `public.profiles`, or manually create the matching profile row in the database currently used by the backend.

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
| `backend/db/models.py` | Defines `Profile` and `Book` SQLAlchemy models |

Current database foundation:

* `load_dotenv()` loads local environment variables.
* `DATABASE_URL` is required by `backend/db/database.py`.
* `create_engine(DATABASE_URL)` configures the SQLAlchemy engine.
* `SessionLocal` is configured with `autocommit=False`, `autoflush=False`, and the shared engine.
* `get_db()` yields a SQLAlchemy `Session` and closes it after use.
* `Base` uses SQLAlchemy `DeclarativeBase`.
* `Profile` maps Supabase users to app profiles.
* `Book` maps to the `books` table with fields for owning `user_id`, title, authors, stable external id, status, rating, pages, progress, and date values.

---

## Alembic Migrations

Alembic is used to manage database schema changes. A schema is the structure of the database, such as which tables exist and which columns each table has.

Instead of creating tables by hand every time, Alembic stores schema changes in migration files. These files make database setup reproducible: a developer can start with an empty PostgreSQL database and run the migrations to create the same tables.

Current Alembic migration work:

* Alembic has been initialized.
* Alembic is connected to SQLAlchemy metadata.
* The initial migration has been generated.
* The initial migration has been applied to local PostgreSQL.
* The `profiles` and `books` tables have been created.
* The `books.user_id` ownership column scopes libraries by Supabase profile id.
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

Implemented repository operations are scoped by `user_id`:

* `get_all_books()`
* `get_book_by_id()`
* `create_book()`
* `update_book()`
* `delete_book()`

CRUD means create, read, update, and delete. These are the basic operations needed to manage records in a database.

The repository CRUD operations are used by book CRUD routes through `backend/services/postgres_books.py`. Routes pass `current_user.id` from the Supabase auth dependency into those services.

---

## Storage Architecture

PostgreSQL is the source of truth for profiles and user-owned book CRUD operations.

| Layer | File | Responsibility |
| --- | --- | --- |
| Database setup | `backend/db/database.py` | Loads `.env`, reads `DATABASE_URL`, creates the SQLAlchemy engine, configures `SessionLocal`, defines `Base`, and provides `get_db()` |
| Models | `backend/db/models.py` | Defines SQLAlchemy models, including the `Book` model mapped to the `books` table |
| Auth | `backend/auth/dependencies.py` | Validates Supabase Bearer tokens and loads the current profile |
| Repository | `backend/repository/postgres_books_repository.py` | Isolates user-scoped SQLAlchemy queries and CRUD operations |
| Services | `backend/services/postgres_books.py` | Applies book business rules while preserving API response shapes |
| Routes | `backend/routes/books.py` | Handles HTTP requests and injects database sessions |

Routes and services should not directly manipulate CSV files for primary book storage. CSV paths are compatibility boundaries for import, export, offline ingest, and migration utilities.

## CSV Migration and Compatibility

### Migrate Legacy CSV Data

Run this after `docker compose up -d` and `alembic upgrade head`:

```bash
python -m backend.scripts.migrate_csv_to_postgres --csv backend/data/processed/books.csv
```

The `--csv` option is optional; the default path is `backend/data/processed/books.csv`. This utility is for old pre-auth local data. For normal multi-user libraries, import through the authenticated UI/API path so rows are created for the signed-in user.

### Import and Export

CSV remains supported for compatibility:

* `POST /books/import` accepts parsed CSV rows from the frontend, creates PostgreSQL rows for the signed-in user, and skips duplicate titles in that user's library.
* `GET /books/export` returns the signed-in user's PostgreSQL library as CSV.
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
cp .env.local.example .env.local
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

Required frontend auth variables:

| Variable | Purpose |
| --- | --- |
| `VITE_SUPABASE_URL` | Supabase project URL used by the browser client |
| `VITE_SUPABASE_ANON_KEY` | Public anon/publishable key used by the browser client |
| `VITE_API_BASE_URL` | Optional backend API override; omit for Vite proxy mode |

The frontend login/register flow stores the Supabase session in the browser through `@supabase/supabase-js`. `frontend/src/lib/api.ts` reads the current session and attaches `Authorization: Bearer <access_token>` to backend requests.

On registration/session restore, `frontend/src/contexts/AuthContext.tsx` checks `profiles` for the Supabase user id and inserts a row with `id`, `email`, and `username` when needed. This uses the Supabase project configured in `frontend/.env.local`.

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

ShelfTxt currently uses PostgreSQL for profiles and user-owned book CRUD operations. CSV remains available for export/import compatibility and local migration-adjacent workflows.

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
| `DATABASE_URL` | PostgreSQL connection string for SQLAlchemy-backed profiles and book CRUD. Use Supabase Postgres for Supabase Auth integration testing. |
| `SUPABASE_URL` | Supabase project URL for backend token verification |
| `SUPABASE_ANON_KEY` | Supabase anon/publishable key used as the `/auth/v1/user` API key while validating incoming user tokens |
| `SUPABASE_SERVICE_ROLE_KEY` | Server-only service role key for admin/server-side Supabase operations |

### Frontend

| Variable | Purpose |
| --- | --- |
| `VITE_SUPABASE_URL` | Supabase project URL for browser auth |
| `VITE_SUPABASE_ANON_KEY` | Public anon/publishable key for browser auth |
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
