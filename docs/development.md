# Development & Operations

Local setup and day-to-day commands. For production deployment, see [deployment.md](engineering/deployment.md).

## Current Storage Status

ShelfTxt still uses CSV storage as the active production storage layer.

Live application data is stored at:

```txt
backend/data/processed/books.csv
```

The PostgreSQL migration is in progress. PostgreSQL infrastructure, the initial SQLAlchemy foundation, Alembic migrations, and the first repository layer have been added. Routes and services have not been fully migrated yet, and CSV storage has not been removed.

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
* Routes and services have not been fully migrated to PostgreSQL yet.
* CSV remains the active production storage layer.

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

---

## Repository Layer

The repository layer is responsible for database operations. It acts as a bridge between application code and the database.

Application code should not need to know the details of SQLAlchemy queries. Instead, it can call repository functions such as "get all books" or "create a book." The repository handles the database session and the SQLAlchemy model operations.

Current repository file:

| File | Purpose |
| --- | --- |
| `backend/repository/books_repository.py` | Provides CRUD operations for `Book` records in PostgreSQL |

Implemented repository operations:

* `get_all_books()`
* `get_book_by_id()`
* `create_book()`
* `update_book()`
* `delete_book()`

CRUD means create, read, update, and delete. These are the basic operations needed to manage records in a database.

The repository CRUD operations have been successfully tested against PostgreSQL.

Important current limitation:

* The repository layer exists, but routes and services have not been fully migrated to use it yet.

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

### Phase 4: Alembic Migrations

* Initialized Alembic.
* Connected Alembic to SQLAlchemy metadata.
* Generated the initial migration.
* Applied the migration to PostgreSQL.
* Created the `books` table.
* Created the `alembic_version` table.
* Verified schema creation through PostgreSQL.
* Confirmed the database schema can be recreated through migration files.

### Phase 5: Repository Layer

* Implemented repository CRUD operations in `backend/repository/books_repository.py`.
* Added `get_all_books()`.
* Added `get_book_by_id()`.
* Added `create_book()`.
* Added `update_book()`.
* Added `delete_book()`.
* Verified create, read, update, and delete operations against PostgreSQL.

The migration is not complete. The application has not fully migrated away from CSV storage yet. Routes and services have not been fully migrated to PostgreSQL, and PostgreSQL should not be treated as the active production storage layer.

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
