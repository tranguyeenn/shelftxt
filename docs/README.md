# ShelfTxt documentation

Developer reference for architecture, APIs, local development, and deployment.

**Production:** [shelftxt.vercel.app](https://shelftxt.vercel.app) · **API:** [shelftxt.onrender.com](https://shelftxt.onrender.com) · **OpenAPI:** [/docs](https://shelftxt.onrender.com/docs)

---

## Start here

| If you want to… | Read |
|-----------------|------|
| Understand the full system | [system-design/README.md](system-design/README.md) |
| Clone and run locally | [development.md](development.md) |
| Call or extend the API | [api.md](api.md) |
| Change recommendation scoring | [ranking.md](ranking.md) → [system-design/recommendation-system.md](system-design/recommendation-system.md) |
| Deploy or fix production | [deployment.md](deployment.md) → [troubleshooting.md](troubleshooting.md) |
| Contribute a change | [contributing.md](contributing.md) → [development-workflow.md](development-workflow.md) |
| Understand reader needs | [user-research/README.md](user-research/README.md) |

---

## User research

Reader behavior, feedback themes, and validated assumptions (non-technical):

| Document | Topic |
|----------|--------|
| [user-research/README.md](user-research/README.md) | Index and research principles |
| [research-summary.md](user-research/research-summary.md) | Assumptions vs learnings |
| [reader-archetypes.md](user-research/reader-archetypes.md) | Reader models |
| [decision-making-patterns.md](user-research/decision-making-patterns.md) | How readers choose books |
| [assumptions-validation.md](user-research/assumptions-validation.md) | Evidence tracker |
| [feature-opportunities.md](user-research/feature-opportunities.md) | Observations → ideas |
| [research-log.md](user-research/research-log.md) | Chronological feedback log |

---

## System design (in-depth)

Multi-page technical design for contributors:

| Document | Topic |
|----------|--------|
| [system-design/README.md](system-design/README.md) | Index and overview |
| [architecture-overview.md](system-design/architecture-overview.md) | Components, diagrams, boundaries |
| [backend-design.md](system-design/backend-design.md) | Routes, services, flows |
| [data-model.md](system-design/data-model.md) | CSV fields, validation, future columns |
| [recommendation-system.md](system-design/recommendation-system.md) | Scoring, explanations, limits |
| [api-design.md](system-design/api-design.md) | Endpoint categories and principles |
| [frontend-design.md](system-design/frontend-design.md) | UI routes and reader-focused flows |
| [import-export-flow.md](system-design/import-export-flow.md) | CSV import/export |
| [scalability-and-limitations.md](system-design/scalability-and-limitations.md) | CSV limits, Render, migration |
| [future-roadmap.md](system-design/future-roadmap.md) | Planned reader and engineering work |

---

## Quick reference

| Doc | Purpose |
|-----|---------|
| [architecture.md](architecture.md) | Short architecture summary + links |
| [architecture/system-overview.md](architecture/system-overview.md) | Folder map and layer rules |
| [data-model.md](data-model.md) | CSV column cheat sheet |
| [api.md](api.md) | REST endpoint reference |
| [ranking.md](ranking.md) | Scoring formulas |
| [frontend.md](frontend.md) | Vite + React app |
| [pipeline.md](pipeline.md) | Offline batch CSV ingest |
| [decisions.md](decisions.md) | Architecture decision records |

---

## Operations & process

| Doc | Purpose |
|-----|---------|
| [deployment.md](deployment.md) | Render + Vercel |
| [development.md](development.md) | Local setup, tests, env vars |
| [development-workflow.md](development-workflow.md) | Branching, PR checklist, CI |
| [troubleshooting.md](troubleshooting.md) | Common failures |
| [contributing.md](contributing.md) | PR workflow and conventions |
| [repository-audit.md](repository-audit.md) | Repo health snapshot and gaps |
| [opensource.md](opensource.md) | Project ethos |
| [../DEVLOG.md](../DEVLOG.md) | Engineering timeline |
| [devlogs/](devlogs/) | Dated refactor notes |

---

## Code pointers

- Persistence: [`backend/book_data.py`](../backend/book_data.py)
- Routes: [`backend/routes/`](../backend/routes/)
- Services: [`backend/services/`](../backend/services/)
- Frontend API client: [`frontend/src/lib/api.ts`](../frontend/src/lib/api.ts)
- Mapping template: [`backend/ingest/mapping.example.json`](../backend/ingest/mapping.example.json)
