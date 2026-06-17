# shelftxt

![Open Source](https://img.shields.io/badge/Open%20Source-Yes-green)
![Python](https://img.shields.io/badge/Python-3.x-blue)
![FastAPI](https://img.shields.io/badge/FastAPI-backend-teal)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Tests](https://github.com/tranguyeenn/shelftxt/actions/workflows/tests.yml/badge.svg)](https://github.com/tranguyeenn/shelftxt/actions/workflows/tests.yml)

Shelftxt is an open-source multi-user recommendation system for organizing and ranking personal TBR libraries. It combines Supabase authentication, PostgreSQL-backed user-owned book storage, and transparent recommendation logic.

**Live:** [shelftxt.vercel.app](https://shelftxt.vercel.app) · **API docs:** [shelftxt.onrender.com/docs](https://shelftxt.onrender.com/docs)

---

## Overview

Shelftxt exposes a FastAPI service over a PostgreSQL-backed, authenticated book CRUD API. Supabase handles registration, login, session persistence, and token verification; each book row belongs to one authenticated user through `books.user_id`. A Vite + React UI manages login-protected routes and attaches the current Supabase access token to backend requests. CSV import/export remains available for backups and spreadsheet workflows, but PostgreSQL is the source of truth.

The project is maintained in the open: architecture notes, ADRs, and [devlogs](docs/history/devlogs/) document how the backend evolves.

---

## Features

- **Multi-user shelf management** — want-to-read, reading (progress %), read (ratings), DNF, scoped per authenticated user
- **Supabase authentication** — email/password registration, login, persisted browser sessions, logout
- **TBR ranking** — `GET /recommend` scores the signed-in user's to-read list from their read-history author preferences
- **Authenticated REST API** — OpenAPI at `/docs`; Pydantic schemas in `backend/schemas/`; protected routes require `Authorization: Bearer <access_token>`
- **CSV import** — bulk add via `POST /books/import`; duplicates skipped within the current user's PostgreSQL library
- **Batch ingest pipeline** — map external exports to a canonical schema ([pipeline docs](docs/engineering/import-export.md#batch-pipeline))
- **CLI** — `python -m cli.manage_books` for local shelf edits

CSV export remains available for backups and spreadsheet workflows.

---

## Tech stack

| Layer | Stack |
|-------|--------|
| **API** | Python, FastAPI, uvicorn, pandas |
| **Auth** | Supabase Auth (`@supabase/supabase-js` frontend, service-role token verification backend) |
| **Ranking** | Custom scoring in `backend/ranking/`, features in `backend/preprocess/` |
| **Persistence** | PostgreSQL for profiles and user-owned book CRUD (`backend/db/` + `backend/repository/postgres_books_repository.py`) |
| **UI** | Vite, React, TypeScript |
| **Deploy** | Render (API), Vercel (frontend) |

---

## Architecture

```text
Browser → Supabase Auth → FastAPI routes → services → repository → SQLAlchemy → PostgreSQL
                         ↘ preprocess/ + ranking/  (no I/O)
```

| Layer | Role |
|-------|------|
| `backend/api.py` | App shell: CORS, lifespan, router registration |
| `auth/` | Supabase Bearer token verification and current profile dependency |
| `routes/` | HTTP only — parse request, call services |
| `services/` | Business logic (shelves, recommendations) |
| `repository/` | Persistence layer for PostgreSQL-backed book CRUD |
| `schemas/` | Pydantic request/response models |
| `ingest/` | Offline CSV pipeline (not live UI import) |

Deeper docs: [documentation index](./docs/README.md) · [architecture](./docs/engineering/architecture.md) · [decisions](./docs/product/decisions.md)

---

## Local setup

### Backend (required for API work)

PostgreSQL is the primary storage backend for profiles and book CRUD data. Local development can use Docker Compose for isolated database work, but Supabase Auth integration testing must use the same Postgres database that contains the Supabase-backed `profiles` rows.

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

Required backend variables:

```env
DATABASE_URL=postgresql+psycopg://shelftxt:shelftxt_dev_password@localhost:5432/shelftxt
SUPABASE_URL=https://your-project.supabase.co
SUPABASE_ANON_KEY=your_anon_or_publishable_key
SUPABASE_SERVICE_ROLE_KEY=your_service_role_key
```

`SUPABASE_ANON_KEY` is used by the backend as the Supabase Auth API key when validating incoming user access tokens.
`SUPABASE_SERVICE_ROLE_KEY` is server-only. Do not expose it in frontend code or committed examples.
The frontend uses `VITE_SUPABASE_ANON_KEY`; the backend root `.env` uses
`SUPABASE_ANON_KEY`. The values can be the same, but Python does not read
frontend env files.

For multi-user auth testing, `DATABASE_URL` cannot point at an empty local Docker database while the frontend uses hosted Supabase Auth. The backend verifies the Supabase JWT, then queries `profiles.id` in the database named by `DATABASE_URL`. Use one of these setups:

| Setup | `DATABASE_URL` | Profile rows |
| --- | --- | --- |
| Supabase integration test | Supabase Postgres connection string for the same project as `SUPABASE_URL` / `VITE_SUPABASE_URL` | Created by the frontend in Supabase `public.profiles` |
| Isolated local backend work | Local Docker Postgres | Manually insert local `profiles.id` values matching Supabase auth user UUIDs, or seed test users |

If `/books` or another protected endpoint returns `{"detail":"User profile not found"}`, the Supabase Auth user exists but the backend database does not contain a matching `profiles.id`. Point `DATABASE_URL` at the correct Supabase Postgres database or create that profile row in the database currently used by the backend.

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

After PostgreSQL is running and migrations have been applied, the legacy migration utility can import an old pre-auth ShelfTxt CSV:

```bash
python -m backend.scripts.migrate_csv_to_postgres --csv backend/data/processed/books.csv
```

The `--csv` option is optional; when omitted, the script uses `backend/data/processed/books.csv`. This utility is for legacy local data only; use the authenticated `/books/import` flow for day-to-day user libraries so rows are owned by the signed-in user.

#### CSV compatibility

CSV is no longer the primary storage mechanism for book CRUD. CSV import and export remain supported for backups, spreadsheet workflows, and compatibility:

- `POST /books/import` imports parsed rows into the signed-in user's PostgreSQL library and skips duplicate titles for that user.
- `GET /books/export` exports the signed-in user's PostgreSQL library as `shelftxt-library.csv`.

### Frontend (optional)

```bash
cd frontend
npm install
cp .env.local.example .env.local
npm run dev
```

Frontend variables:

```env
VITE_SUPABASE_URL=https://your-project.supabase.co
VITE_SUPABASE_ANON_KEY=your_anon_or_publishable_key
VITE_API_BASE_URL=http://127.0.0.1:8000
```

`VITE_API_BASE_URL` is optional for local proxy mode, but useful when calling a specific API host. Open http://localhost:3000. See [docs/contributors/development.md](docs/contributors/development.md) for env vars and remote API mode.

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

Except for `/health`, backend routes are protected. Send a Supabase access token with every book and recommendation request:

```http
Authorization: Bearer <supabase_access_token>
```

| Method | Path | Description |
|--------|------|-------------|
| `GET` / `HEAD` | `/health` | Health check |
| `GET` | `/books` | List library (paginated: `?page=1&limit=20`) |
| `POST` | `/books` | Add book (TBR) |
| `PATCH` | `/books` | Update / move shelf |
| `GET` | `/books/{id}` | Get one book by id |
| `PATCH` | `/books/{id}/progress` | Update status and pages read |
| `GET` | `/books/export` | Download library CSV |
| `POST` | `/books/clear` | Clear current user's library |
| `POST` | `/books/import` | Bulk import |
| `DELETE` | `/books/{id}` | Delete by book id |
| `GET` | `/recommend?style=` | Top 10 TBR suggestions |

Full reference: [docs/engineering/api.md](docs/engineering/api.md) · [Documentation index](docs/README.md)

---

## Authentication flow

Registration uses Supabase Auth email/password signup. The frontend stores `username` in user metadata, then creates a matching `profiles` row through the Supabase browser client when Supabase returns a session. If email confirmation is enabled, the profile is created after the user confirms and a session is restored. That row is created in the Supabase project configured by `VITE_SUPABASE_URL`.

Login uses `supabase.auth.signInWithPassword()`. Supabase persists and refreshes the browser session (`persistSession`, `autoRefreshToken`), and protected React routes redirect unauthenticated visitors to login/register screens. Logout calls `supabase.auth.signOut()` and clears the local session.

Backend book and recommendation routes depend on `get_current_user()`, which validates `Authorization: Bearer <token>` with Supabase, loads the matching `profiles` row, and scopes all CRUD and recommendation queries by that profile id.

### API examples

Login from a client with Supabase:

```ts
const { data, error } = await supabase.auth.signInWithPassword({
  email: "reader@example.com",
  password: "correct-horse-battery-staple"
});

const token = data.session?.access_token;
```

Authenticated book requests:

```bash
curl -H "Authorization: Bearer $SUPABASE_ACCESS_TOKEN" \
  http://127.0.0.1:8000/books

curl -X POST http://127.0.0.1:8000/books \
  -H "Authorization: Bearer $SUPABASE_ACCESS_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"title":"Dune","author":"Frank Herbert","total_pages":688}'

curl -X PATCH http://127.0.0.1:8000/books/book-id-or-isbn/progress \
  -H "Authorization: Bearer $SUPABASE_ACCESS_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"status":"reading","pages_read":120}'

curl -X DELETE http://127.0.0.1:8000/books/book-id-or-isbn \
  -H "Authorization: Bearer $SUPABASE_ACCESS_TOKEN"
```

## Roadmap

See [ROADMAP.md](ROADMAP.md) for current capabilities and planned work.

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
