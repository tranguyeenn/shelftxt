# Shelftxt — Technical documentation

Developer reference for architecture, APIs, deployment, and operations.

## Production

| Service | URL |
|---------|-----|
| Frontend | https://shelftxt.vercel.app |
| Backend API | https://shelftxt.onrender.com |
| OpenAPI | https://shelftxt.onrender.com/docs |

---

## Core docs

| Doc | Description |
|-----|-------------|
| [system-design/README.md](system-design/README.md) | **Multi-page system design** — architecture, backend, data model, recommendations, API/frontend, scalability, roadmap |
| [architecture.md](architecture.md) | System layout, layers, production topology, repo structure |
| [system-design.md](system%20design/system-design.md) | End-to-end design: goals, components, flows, scaling strategy |
| [system-design-1page.md](system%20design/system-design-1page.md) | 1-page interview-style system design summary |
| [system-design-rfc.md](system%20design/system-design-rfc.md) | RFC-style deep design for engineering collaboration |
| [deployment.md](deployment.md) | Render + Vercel runbook, env vars, verification |
| [decisions.md](decisions.md) | Architecture decision records (ADRs) |
| [development.md](development.md) | Local setup, tests, CLI |
| [contributing.md](contributing.md) | Workflow detail — PR checklist, commit style |
| [opensource.md](opensource.md) | Why the project is open source, devlogs, transparency |
| [troubleshooting.md](troubleshooting.md) | Common errors and fixes |

## Engineering notes

| Doc | Description |
|-----|-------------|
| [../DEVLOG.md](../DEVLOG.md) | Devlog index — timeline and refactors |
| [devlogs/](devlogs/) | Dated entries + [template](devlogs/README.md) |
| [architecture/system-overview.md](architecture/system-overview.md) | Folder responsibilities (`backend/`, `services/`, …) |
| [screenshots/](screenshots/) | Optional visuals for devlogs |

## Domain docs

| Doc | Description |
|-----|-------------|
| [data-model.md](data-model.md) | App CSV schema, canonical fields, shelf mapping |
| [api.md](api.md) | FastAPI REST reference |
| [ranking.md](ranking.md) | Scoring formulas and recommendation behavior |
| [pipeline.md](pipeline.md) | Flexible CSV ingest, mapping config, validation |
| [frontend.md](frontend.md) | Vite + React app structure and UI behavior |

---

## Quick links

- Local API docs: http://127.0.0.1:8000/docs
- Mapping template: [`backend/ingest/mapping.example.json`](../backend/ingest/mapping.example.json)
- Persistence: [`backend/book_data.py`](../backend/book_data.py) · [`backend/repository/books_repository.py`](../backend/repository/books_repository.py)
- Routes: [`backend/routes/`](../backend/routes/)
- Render Blueprint: [`render.yaml`](../render.yaml)

---

## Doc map (what to read when)

| Task | Start here |
|------|------------|
| First time cloning | [development.md](development.md) |
| Deploy or fix prod | [deployment.md](deployment.md) → [troubleshooting.md](troubleshooting.md) |
| Add an API endpoint | [system-design/backend-design.md](system-design/backend-design.md) → [contributing.md](contributing.md) → [api.md](api.md) |
| Change scoring | [system-design/recommendation-system.md](system-design/recommendation-system.md) → [ranking.md](ranking.md) |
| Import / batch CSV | [pipeline.md](pipeline.md) |
| Understand a past refactor | [../DEVLOG.md](../DEVLOG.md) → [devlogs/](devlogs/) |
