# ShelfTxt weekly update — foundation work

| | |
|---|---|
| **Date** | 2026-05-30 |
| **Feature / Refactor** | Reliability, documentation, pagination review, and Postgres migration planning |
| **Problem** | ShelfTxt still carries assumptions from its origins as a personal tool: shared CSV storage, broad exception handling, and API contracts that need careful evolution as the project opens up |
| **Old approach** | Catch-all `except Exception` blocks, monolithic docs, unpaginated library listing, and a single shared dataset on disk |
| **New approach** | Narrower exception handling in production paths, expanded system-design and inline docs, paginated `GET /books`, stronger recommendation test coverage, and early planning for user-specific PostgreSQL storage |
| **Files changed** | `backend/ingest/pipeline.py`, `backend/services/books.py`, `backend/api.py`, `backend/routes/books.py`, `docs/`, `tests/` (see commit history since 2026-05-24) |
| **Lessons learned** | [Below](#lessons-learned) |
| **Next steps** | PostgreSQL migration; user-specific libraries; recommendation improvements; continued OSS review |

---

## Context

This week was focused on improving the foundation of the project rather than adding major user-facing features. Most of the work wasn't flashy, but it was the kind of maintenance and architecture work that makes future features possible.

One thing that became clear from both feedback and code reviews is that ShelfTxt still carries a lot of assumptions from when it was originally built as a personal tool. The next major step is moving toward user-specific data storage so the project can support individual libraries instead of relying on a shared dataset.

---

## Highlights

### Community contributions

Reviewed and merged multiple community pull requests. Keeping review cycles tight helps the project stay approachable for new contributors while protecting API contracts and test coverage.

### Backend reliability — exception handling

Replaced broad `except Exception` handlers with more specific catches in production code:

| Location | Change |
|----------|--------|
| `backend/ingest/pipeline.py` | Catch `ParserError` / `EmptyDataError` on CSV preview instead of all exceptions |
| `backend/services/books.py` | Catch `ValueError`, `TypeError`, and `ParserError` in `parse_date_or_today` |
| `backend/api.py` | Catch `httpx.RequestError` in scheduled self-ping instead of all exceptions |

Goal: expected failures (bad CSV, bad date strings, network blips on keep-alive) stay handled; unexpected bugs surface normally instead of being swallowed.

### Documentation

- Expanded backend and system-design documentation (`docs/engineering/`, architecture guides).
- Added user research section for reader feedback and archetypes.
- Documented paginated `GET /books` across architecture guides.
- Added docstrings to backend services and repository functions.

### Pagination and API design

Shipped and reviewed pagination for `GET /books` (`page`, `limit`, structured response with `total` and `results`). Review focused on backward compatibility: existing consumers that assumed a flat array needed explicit migration, and query validation (bounds, invalid params → 422) was verified in tests.

### Recommendation system

Continued refining recommendation test coverage and validation — ranking unit tests, API test mock fixes, cache invalidation on shelf mutations, and enriched recommendation payloads on the frontend.

### Demo mode

Added read-only demo banner for the shared public deployment so visitors understand the library is not theirs to mutate.

---

## Lessons learned

1. **Foundation work compounds** — docs, tests, and narrow error handling don't show up in a screenshot, but they unblock Postgres, auth, and multi-user libraries.
2. **Personal-tool assumptions linger in storage and API shape** — a shared CSV on Render works for a demo; it does not scale to individual libraries without a deliberate migration.
3. **Exception narrowing needs domain knowledge** — CSV validation should still reject encoding failures gracefully; network keep-alive should not catch programming errors. Code review caught gaps worth fixing before merge.
4. **Pagination is a contract change** — even additive query params need documentation and frontend caller updates so nothing silently breaks.
5. **Open source maintenance is part of the roadmap** — reviewing community PRs is not separate from product work; it shapes reliability and contributor experience.

---

## Current focus

- **PostgreSQL migration** — move off ephemeral CSV storage on Render
- **User-specific libraries** — per-user data instead of a shared dataset
- **Recommendation system improvements** — coverage, validation, and UX
- **Continued open source contributions and code review**

---

## Related docs

- [System overview](../../engineering/architecture.md)
- [Backend design](../../engineering/backend.md)
- [API design](../../engineering/api.md)
- [Future roadmap](../../product/roadmap.md)
- [Previous devlog: backend refactor](2026-05-24-backend-refactor.md)
