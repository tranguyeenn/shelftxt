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

ShelfTxt uses PostgreSQL as the primary storage backend for book CRUD operations. Local development uses Docker Compose for PostgreSQL.

### Environment Variables

Create a local `.env` file in the repository root:

```env
DATABASE_URL=postgresql+psycopg://shelftxt:shelftxt_dev_password@localhost:5432/shelftxt
```

Alternatively:

```bash
cp .env.example .env
```

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

ShelfTxt currently uses PostgreSQL for book CRUD operations.

The book CRUD flow is:

```txt
Route -> Service -> Repository -> SQLAlchemy -> PostgreSQL
```

CSV remains available for import/export compatibility and legacy helper paths.

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
| `DATABASE_URL` | PostgreSQL connection string for SQLAlchemy-backed book CRUD |

### Frontend

| Variable            | Purpose                  |
| ------------------- | ------------------------ |
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
