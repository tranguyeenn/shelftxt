# Development & Operations

Local setup and day-to-day commands. For production deployment, see [deployment.md](../engineering/deployment.md).

## Requirements

* Python 3.12+
* Node.js 20+
* Docker Desktop (required for local PostgreSQL development)

---

## Install Python Dependencies

From the repository root:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### Database Migration Dependencies

The PostgreSQL migration stack includes:

* SQLAlchemy (ORM and database access)
* psycopg (PostgreSQL driver)
* Alembic (database migrations)
* python-dotenv (environment variable loading)

These dependencies are installed through `requirements.txt`.

---

## Database Development Setup

ShelfTxt uses PostgreSQL as the primary storage backend for profiles and user-owned book CRUD operations. Local Docker Postgres is useful for isolated backend work; Supabase Auth integration testing must use the same Postgres database that contains the Supabase `profiles` rows.

### Environment Variables

Create a local `.env` file in the repository root:

```env
DATABASE_URL=postgresql+psycopg://shelftxt:shelftxt_dev_password@localhost:5432/shelftxt
SUPABASE_URL=https://your-project.supabase.co
SUPABASE_SERVICE_ROLE_KEY=your_service_role_key
```

Alternatively:

```bash
cp .env.example .env
```

For local multi-user auth testing, replace the local `DATABASE_URL` with the Supabase Postgres connection string for the same project used by `SUPABASE_URL` and `VITE_SUPABASE_URL`. The backend validates the Supabase JWT, then looks up `profiles.id` in the database named by `DATABASE_URL`.

Local Docker Postgres works only if you manually insert profile rows whose `id` values match the Supabase auth user UUIDs used in your test tokens.

### Start PostgreSQL

From the repository root:

```bash
docker compose up -d
```

Verify the container is running:

```bash
docker compose ps
```

Expected container:

```txt
shelftxt-postgres
```

### Connect to PostgreSQL

```bash
docker exec -it shelftxt-postgres psql -U shelftxt -d shelftxt
```

Exit PostgreSQL:

```sql
\q
```

### Local Database Credentials

| Setting  | Value                 |
| -------- | --------------------- |
| Host     | localhost             |
| Port     | 5432                  |
| Database | shelftxt              |
| Username | shelftxt              |
| Password | shelftxt_dev_password |

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

| Mode                | Config                | Browser Calls                            |
| ------------------- | --------------------- | ---------------------------------------- |
| Local API (default) | None                  | `/api/*` → Vite proxy → `127.0.0.1:8000` |
| Remote API          | `frontend/.env.local` | Direct requests to deployed API          |

Create local frontend environment variables:

```bash
cp frontend/.env.local.example frontend/.env.local
```

Restart the frontend after modifying environment variables.

`frontend/.env.local` must include Supabase browser credentials:

```env
VITE_SUPABASE_URL=https://your-project.supabase.co
VITE_SUPABASE_ANON_KEY=your_anon_or_publishable_key
VITE_API_BASE_URL=http://127.0.0.1:8000
```

`VITE_API_BASE_URL` is optional when using the Vite proxy. The Supabase anon key is public by design; never put the service role key in frontend env.

The frontend creates missing `profiles` rows through the Supabase browser client in the project configured by `VITE_SUPABASE_URL`. Keep that project aligned with backend `SUPABASE_URL`.

### CLI

```bash
python -m cli.manage_books
```

The CLI may still use the legacy CSV helper path. Prefer the API when verifying PostgreSQL-backed CRUD behavior.

---

## Testing

Run all tests:

```bash
./.venv/bin/python -m unittest discover -s tests -v
```

### Test Coverage

| File                              | Coverage                             |
| --------------------------------- | ------------------------------------ |
| `tests/test_api.py`               | API routes and services              |
| `tests/test_flexible_pipeline.py` | Ingest, validation, ranking pipeline |

See:

* [architecture.md](../engineering/architecture.md)
* [contributing.md](contributing.md)

for development workflow and architecture guidelines.

---

## Data Storage

### Current Storage

ShelfTxt currently uses PostgreSQL for profiles and user-owned book CRUD operations.

The book CRUD flow is:

```txt
Supabase session -> Route -> Service -> Repository -> SQLAlchemy -> PostgreSQL
```

CSV remains available for import/export compatibility and legacy helper paths. It is not the primary storage layer.

### Data Directories

| Path                               | Git Status           | Purpose              |
| ---------------------------------- | -------------------- | -------------------- |
| `backend/data/raw/`                | Tracked (`.gitkeep`) | Optional CSV staging |
| `backend/data/processed/books.csv` | Gitignored           | Legacy CSV/import-export compatibility data |

Legacy CSV helpers may create an empty `books.csv` if one does not exist.

---

## Environment Variables

### Backend

| Variable       | Purpose                                         |
| -------------- | ----------------------------------------------- |
| `DATABASE_URL` | PostgreSQL connection string for SQLAlchemy-backed profiles and book CRUD; use Supabase Postgres for Supabase Auth integration testing |
| `SUPABASE_URL` | Supabase project URL for backend token verification |
| `SUPABASE_SERVICE_ROLE_KEY` | Server-only service role key for backend Supabase client |

### Frontend

| Variable            | Purpose                  |
| ------------------- | ------------------------ |
| `VITE_SUPABASE_URL` | Supabase project URL for browser auth |
| `VITE_SUPABASE_ANON_KEY` | Public anon/publishable key for browser auth |
| `VITE_API_BASE_URL` | Override backend API URL |

Full deployment configuration:

[deployment.md](../engineering/deployment.md#environment-variable-reference)

---

## Deployment

Production deployment documentation:

* [deployment.md](../engineering/deployment.md)

Troubleshooting:

* [troubleshooting.md](troubleshooting.md)

---

## Related Documentation

* [architecture.md](../engineering/architecture.md)
* [api.md](../engineering/api.md)
* [import-export.md](../engineering/import-export.md#batch-pipeline)
* [decisions.md](../product/decisions.md)
