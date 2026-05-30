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

Shelftxt exposes a FastAPI service over a CSV-backed library (Postgres-ready layering). A Next.js UI and CLI share the same data model. Recommendation scoring runs in Python (`preprocess/` + `ranking/`) with transparent, inspectable logic—not a black-box API.

The project is maintained in the open: architecture notes, ADRs, and [devlogs](docs/devlogs/) document how the backend evolves.

---

## Features

- **Shelf management** — want-to-read, reading (progress %), read (ratings), DNF
- **TBR ranking** — `GET /recommend` scores your to-read list from read-history author preferences
- **REST API** — OpenAPI at `/docs`; Pydantic schemas in `backend/schemas/`
- **CSV import** — bulk add via `POST /books/import`; duplicates skipped
- **Batch ingest pipeline** — map external exports to a canonical schema ([pipeline docs](docs/pipeline.md))
- **CLI** — `python -m cli.manage_books` for local shelf edits

`backend/data/processed/books.csv` is created empty on first use (not committed).

---

## Tech stack

| Layer | Stack |
|-------|--------|
| **API** | Python, FastAPI, uvicorn, pandas |
| **Ranking** | Custom scoring in `backend/ranking/`, features in `backend/preprocess/` |
| **Persistence** | CSV today (`backend/book_data.py` + `backend/repository/`) |
| **UI** | Vite, React, TypeScript |
| **Deploy** | Render (API), Vercel (frontend) |

---

## Architecture

```text
HTTP → routes/ → services/ → repository/ → book_data.py → books.csv
                    ↘ preprocess/ + ranking/  (no I/O)
```

| Layer | Role |
|-------|------|
| `backend/api.py` | App shell: CORS, lifespan, router registration |
| `routes/` | HTTP only — parse request, call services |
| `services/` | Business logic (shelves, recommendations) |
| `repository/` | Persistence facade (swap for Postgres later) |
| `schemas/` | Pydantic request/response models |
| `ingest/` | Offline CSV pipeline (not live UI import) |

Deeper docs: [system design](./docs/system-design/README.md) · [system overview](./docs/architecture/system-overview.md) · [architecture.md](./docs/architecture.md) · [decisions.md](./docs/decisions.md)

---

## Local setup

### Backend (required for API work)

```bash
git clone https://github.com/tranguyeenn/shelftxt.git
cd shelftxt
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn backend.api:app --reload
```

- API: http://127.0.0.1:8000  
- Swagger: http://127.0.0.1:8000/docs  

Run commands from the **repo root** so `backend` resolves as a package.

### Frontend (optional)

```bash
cd frontend && npm install && npm run dev
```

Open http://localhost:3000. See [docs/development.md](docs/development.md) for env vars and remote API mode.

### Tests

```bash
python -m unittest discover -s tests -v
```

Optional local tooling (if you prefer `pytest`):

```bash
pip install -r requirements-dev.txt
python -m pytest -q
```

---

## API routes

| Method | Path | Description |
|--------|------|-------------|
| `GET` / `HEAD` | `/health` | Health check |
| `GET` | `/books` | List library |
| `POST` | `/books` | Add book (TBR) |
| `PATCH` | `/books` | Update / move shelf |
| `PATCH` | `/books/{id}/progress` | Update status and pages read |
| `GET` | `/books/export` | Download library CSV |
| `POST` | `/books/clear` | Clear entire library |
| `POST` | `/books/import` | Bulk import |
| `DELETE` | `/books/{id}` | Delete by book id |
| `GET` | `/recommend?style=` | Top 10 TBR suggestions |

Full reference: [docs/api.md](docs/api.md) · [System design](docs/system-design/README.md)

---

## Roadmap

See [ROADMAP.md](ROADMAP.md) for current capabilities and planned work (Postgres, caching, auth, analytics).

Engineering history: [DEVLOG.md](DEVLOG.md) · [docs/devlogs/](docs/devlogs/)

---

## Documentation

Backend services and repository functions include docstrings documenting their purpose and return behavior. See `backend/services/`, `backend/repositories/`, `preprocess/`, and `backend/ranking/` for inline documentation.

---

## Contributing

Shelftxt is open source and contributions, bug reports, discussions, and feature ideas are welcome.

See [CONTRIBUTING.md](CONTRIBUTING.md) for development guidelines.

Use GitHub templates under `.github/` for bugs and pull requests.

---

## License

MIT — see [LICENSE](LICENSE).

Additional docs: [docs/README.md](docs/README.md) · [System design](docs/system-design/README.md) · [SECURITY.md](SECURITY.md) · [CHANGELOG.md](CHANGELOG.md)
