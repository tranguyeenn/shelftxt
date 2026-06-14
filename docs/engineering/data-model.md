# Data model

## Overview

ShelfTxt persists book CRUD data as rows in PostgreSQL through the SQLAlchemy `Book` model in `backend/db/models.py`. API responses still preserve the CSV-shaped field names used by the frontend and CSV export/import workflows.

Two related schemas exist:

1. **App book model** — what the API and UI use today (`Book` in `backend/db/models.py`, exposed with CSV-compatible response keys)
2. **Canonical schema** — used by the offline batch ingest pipeline (`backend/ingest/`)

This document focuses on the **app book model** unless noted.

---

## Current book fields (app model)

| Column | Required on write | Type (logical) | Meaning |
|--------|-------------------|----------------|---------|
| `Title` | yes (for identity in legacy PATCH/DELETE) | string | Display title; duplicate titles rejected on import |
| `Authors` | yes on add | string | Author name(s); used for author-preference scoring |
| `ISBN/UID` | auto-generated | string | Stable book id for UI routes and `DELETE /books/{id}` |
| `Read Status` | auto on add | enum | `to-read`, `read`, or `dnf` (lowercased on load) |
| `Star Rating` | when marking read | float 1–5 or null | User rating; DNF may force `1` via legacy PATCH |
| `Last Date Read` | optional | datetime or null | Finish date for read/DNF |
| `Progress (%)` | derived | float 0–100 | From pages read / total pages while in progress |
| `Pages Read` | derived | int | Current page count |
| `Total Pages` | optional | int or null | Required before tracking reading progress |

### Read status semantics

| `Read Status` | `Progress (%)` | Meaning |
|---------------|----------------|---------|
| `to-read` | 0 | Not started (TBR) |
| `to-read` | > 0 | In progress (UI: **reading**) |
| `read` | 100 (typical) | Completed |
| `dnf` | 0 | Did not finish |

The API progress endpoint exposes UI statuses `not_started`, `reading`, and `completed` — mapped in `backend/services/book_api.py`, not stored as separate columns.

### UI status (derived, not stored)

| UI label | Rule |
|----------|------|
| Not started | `to-read` and progress/pages = 0 |
| Reading | `to-read` and progress or pages > 0 |
| Completed | `read` |
| DNF | `dnf` |

Implementation: `recordToApiBook()` in `frontend/src/lib/books.ts`.

---

## API book object (derived, not stored)

`PATCH /books/{book_id}/progress` returns a normalized object:

```json
{
  "id": "ISBN/UID value",
  "title": "...",
  "author": "...",
  "status": "not_started | reading | completed",
  "total_pages": 500,
  "pages_read": 120,
  "progress_pct": 24.0,
  "rating": null,
  "read_status": "to-read"
}
```

`GET /books` returns paginated `{ page, limit, total, results }`; each row in `results` uses raw CSV column names. See [api.md](api.md).

---

## Validation expectations

### Add (`POST /books`)

- `title`, `author` required in schema
- `total_pages` optional

### Import (`POST /books/import`)

- Each row needs non-empty `title`
- Skips if `Title` already exists (**case-sensitive** match)
- Empty author defaults to `"Unknown"` in service

### Progress (`PATCH /books/{book_id}/progress`)

- `pages_read >= 0`
- `pages_read <= total_pages` when total is set
- `reading` / `completed` require valid `total_pages`
- `completed` requires `pages_read == total_pages`
- Auto-completes when `pages_read == total_pages` while status is `reading`

### Legacy patch (`PATCH /books`)

- Keyed by `title`
- `move_to: reading` requires total pages; clamps pages 1…total
- `move_to: read` requires rating 1–5

---

## Derived features (not stored)

Computed at recommendation time in `preprocess/normalize.py`:

| Field | Description |
|-------|-------------|
| `rating_norm` | Min–max normalized star rating in [0, 1] |
| `recency_norm` | Min–max days since read (more recent → higher) |
| `days_since_read` | Integer days from `Last Date Read` to today |
| `author_score` | Mean `rating_norm` for read books by same author |
| `score` | TBR rank score (author preference + optional noise) |

See [recommendation-system.md](recommendation-system.md) for scoring detail.

---

## CSV compatibility

### Export

`GET /books/export` writes all `BOOKS_COLUMNS` as CSV for backup and spreadsheet workflows.

### Import (UI)

Frontend accepts CSV headers: `title`/`Title`, `author`/`Author`, `total_pages`/`Total Pages`. Parsed client-side with Papa Parse, sent as JSON to the API.

### Legacy CSV load repair

Legacy CSV helpers still normalize data when `load_data()` is used by CSV-adjacent or migration workflows:

- Missing columns are added as NaN
- Column order normalized to `BOOKS_COLUMNS`
- `Read Status` lowercased and trimmed
- `Last Date Read` parsed with `errors="coerce"`

Extra columns in an uploaded file are **not** persisted through UI import today—only title, author, total_pages.

### Batch pipeline (separate)

Offline ingest can map external exports to canonical fields including **genre**. See [import-export.md](import-export.md#batch-pipeline). That path does not automatically merge into live PostgreSQL storage unless run manually.

---

## Canonical schema (batch pipeline only)

| Field | Required | Default |
|-------|----------|---------|
| `book_id` | no | generated |
| `title` | yes | — |
| `author` | no | `"unknown"` |
| `genre` | no | `"unknown"` |
| `read_status` | yes | `"to-read"` |
| `rating` | no | column mean or 3.0 |
| `last_date_read` | no | today if missing after clean |

---

## Future fields (planned — not in app model today)

These appear in early reader feedback and design discussions. **Do not assume they exist in code** until implemented.

| Field | Purpose |
|-------|---------|
| `mood_tags` | Filter or rank by mood (cozy, challenging, etc.) |
| `why_added` | User note on why a book entered the TBR |
| `source` | Where the book came from (friend, article, book club) |
| `challenge_prompt` | Reading challenge association |
| `user_notes` | Freeform notes on book detail |
| `dnf_reason` | Why a book was abandoned |

### Backward compatibility concerns

- New columns should be **optional** with safe defaults on load (same pattern as `BOOKS_COLUMNS` repair).
- API responses should tolerate null/missing values in the UI.
- Export should include new columns once added so round-trips do not lose data.
- Title-based and id-based lookups may coexist during migration—document which endpoints use which key.
- Migrating to PostgreSQL should preserve `ISBN/UID` as external id unless a deliberate migration script rekeys rows.

---

## Identity keys (current)

| Operation | Key |
|-----------|-----|
| UI book routes, progress, delete | `ISBN/UID` |
| Legacy PATCH / DELETE by title | `Title` (exact match) |
| Import deduplication | `Title` (case-sensitive) |

Using title as a key is fragile for renames and duplicates; prefer id for new features.
