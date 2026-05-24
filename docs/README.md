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
| [architecture.md](architecture.md) | System layout, layers, production topology, repo structure |
| [deployment.md](deployment.md) | Render + Vercel runbook, env vars, verification |
| [decisions.md](decisions.md) | Architecture decision records (ADRs) |
| [development.md](development.md) | Local setup, tests, CLI |
| [contributing.md](contributing.md) | Conventions, PR checklist, refactor roadmap |
| [troubleshooting.md](troubleshooting.md) | Common errors and fixes |

## Domain docs

| Doc | Description |
|-----|-------------|
| [data-model.md](data-model.md) | App CSV schema, canonical fields, shelf mapping |
| [api.md](api.md) | FastAPI REST reference |
| [ranking.md](ranking.md) | Scoring formulas and recommendation behavior |
| [pipeline.md](pipeline.md) | Flexible CSV ingest, mapping config, validation |
| [frontend.md](frontend.md) | Next.js app structure and UI behavior |

---

## Quick links

- Local API docs: http://127.0.0.1:8000/docs
- Mapping template: [`backend/ingest/mapping.example.json`](../backend/ingest/mapping.example.json)
- Persistence: [`backend/book_data.py`](../backend/book_data.py)
- Render Blueprint: [`render.yaml`](../render.yaml)

---

## Doc map (what to read when)

| Task | Start here |
|------|------------|
| First time cloning | [development.md](development.md) |
| Deploy or fix prod | [deployment.md](deployment.md) → [troubleshooting.md](troubleshooting.md) |
| Add an API endpoint | [architecture.md](architecture.md) → [contributing.md](contributing.md) → [api.md](api.md) |
| Change scoring | [ranking.md](ranking.md) → [decisions.md](decisions.md) if trade-off is non-obvious |
| Import / batch CSV | [pipeline.md](pipeline.md) |
