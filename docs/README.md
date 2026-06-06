# ShelfTxt Documentation

**Production:** [shelftxt.vercel.app](https://shelftxt.vercel.app) · **API:** [shelftxt.onrender.com](https://shelftxt.onrender.com) · **OpenAPI:** [/docs](https://shelftxt.onrender.com/docs)

---

## Product

* [Vision](product/vision.md)
* [Roadmap](product/roadmap.md)
* [Decisions](product/decisions.md)
* [User Research](product/user-research/README.md)

---

## Engineering

* [Architecture](engineering/architecture.md)
* [API](engineering/api.md)
* [Data Model](engineering/data-model.md)
* [Backend](engineering/backend.md)
* [Frontend](engineering/frontend.md)
* [Recommendation System](engineering/recommendation-system.md)
* [Import / Export](engineering/import-export.md)
* [Deployment](engineering/deployment.md)
* [Scalability](engineering/scalability.md)

---

## Contributors

* [Contributing](contributors/contributing.md)
* [Development Setup](contributors/development.md)
* [Development Workflow](contributors/development-workflow.md)
* [Open Source](contributors/opensource.md)

---

## History

* [Devlogs](history/devlogs)
* [Audits](history/audits/repository-audit.md)

---

## Quick start paths

| Goal | Start here |
|------|------------|
| Clone and run locally | [contributors/development.md](contributors/development.md) |
| Contribute a change | [contributors/contributing.md](contributors/contributing.md) → [contributors/development-workflow.md](contributors/development-workflow.md) |
| Understand the full system | [engineering/architecture.md](engineering/architecture.md) |
| Call or extend the API | [engineering/api.md](engineering/api.md) |
| Deploy or fix production | [engineering/deployment.md](engineering/deployment.md) |
| Understand reader needs | [product/user-research/README.md](product/user-research/README.md) |

---

## Code anchors

- Persistence: [`backend/book_data.py`](../backend/book_data.py)
- Routes: [`backend/routes/`](../backend/routes)
- Services: [`backend/services/`](../backend/services)
- Frontend API client: [`frontend/src/lib/api.ts`](../frontend/src/lib/api.ts)
- Mapping template: [`backend/ingest/mapping.example.json`](../backend/ingest/mapping.example.json)
