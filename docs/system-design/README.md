# ShelfTxt system design

Technical documentation for contributors and future maintainers. It describes how ShelfTxt is structured today, how data and recommendations flow through the system, and where the project is likely headed.

ShelfTxt is a **reader-focused TBR and recommendation tool**: users maintain a personal library, track reading progress, and receive ranked suggestions derived from their own history—not from a generic bestseller feed.

The product is **pre-release and evolving**. Behavior, storage, and UI will change as early reader feedback is incorporated. Documents in this section label **current behavior** separately from **planned or exploratory** work.

---

## Table of contents

| Document | Summary |
|----------|---------|
| [Architecture overview](./architecture-overview.md) | High-level components, request flow, deployment topology |
| [Backend design](./backend-design.md) | Routes, services, repositories, ranking modules, sequence diagrams |
| [Data model](./data-model.md) | Book fields, validation, CSV schema, future fields |
| [Recommendation system](./recommendation-system.md) | Rule-based scoring, explanations, limitations, testing direction |
| [API design](./api-design.md) | Endpoint categories, inputs/outputs, error expectations |
| [Frontend design](./frontend-design.md) | User flows, UI principles, reader-focused boundaries |
| [Import / export flow](./import-export-flow.md) | CSV import (UI + API), export, validation |
| [Scalability and limitations](./scalability-and-limitations.md) | CSV storage, Render constraints, caching, migration path |
| [Future roadmap](./future-roadmap.md) | Near-, mid-, and long-term reader and engineering goals |

---

## Related documentation

These docs live outside `system-design/` but complement it:

- [API reference](../api.md) — endpoint-level detail and examples
- [Ranking](../ranking.md) — scoring formulas for TBR and read books
- [Architecture](../architecture.md) — monorepo layout and production topology
- [Data model (quick reference)](../data-model.md) — CSV column cheat sheet
- [Deployment](../deployment.md) — Render + Vercel
- [User research](../user-research/README.md) — reader feedback, archetypes, assumptions
- [ROADMAP.md](../../ROADMAP.md) — high-level engineering directions

---

## How to use this section

1. Start with **architecture overview** if you are new to the repo.
2. Read **backend design** and **data model** before changing persistence or shelf logic.
3. Read **recommendation system** before changing scoring or explanation text.
4. Read **frontend design** before adding UI that exposes internal API details to readers.
5. Check **future roadmap** before proposing large features—some may already be planned.

When something in the codebase is ambiguous, prefer updating these docs after confirming behavior in code and tests.
