# Data model (quick reference)

Full field semantics, validation, and future columns: **[system-design/data-model.md](system-design/data-model.md)**.

---

## App CSV

**Path:** `backend/data/processed/books.csv`  
**Columns:** defined in `BOOKS_COLUMNS` in `book_data.py`

| Column | Notes |
|--------|--------|
| `Title` | Display title; import dedupe key (case-sensitive) |
| `Authors` | Author string; used in author-preference scoring |
| `ISBN/UID` | Stable id for UI routes and `DELETE /books/{id}` |
| `Read Status` | `to-read`, `read`, or `dnf` |
| `Star Rating` | 1–5 when finished |
| `Last Date Read` | Finish date |
| `Progress (%)` | 0–100 |
| `Pages Read` | Current page count |
| `Total Pages` | Required before tracking progress |

---

## UI status (derived, not stored)

| UI label | Rule |
|----------|------|
| Not started | `to-read` and progress/pages = 0 |
| Reading | `to-read` and progress or pages > 0 |
| Completed | `read` |
| DNF | `dnf` |

Implementation: `recordToApiBook()` in `frontend/src/lib/books.ts`.

---

## API list (`GET /books`)

Paginated response: `{ page, limit, total, results }`. Defaults: `page=1`, `limit=20` (max `100`). Each item in `results` uses the CSV column names above. See [api.md](api.md).

---

## Primary keys (today)

| Operation | Key |
|-----------|-----|
| Progress update, delete by id | `ISBN/UID` |
| Legacy PATCH / DELETE | `Title` (exact match) |
| Import skip duplicate | `Title` |

---

## Batch pipeline schema

Separate canonical schema with `genre`, `book_id`, etc. Used by `backend/ingest/` — not written to live CSV unless you run the pipeline manually. See [pipeline.md](pipeline.md).

---

## Derived at recommend time (not in CSV)

`rating_norm`, `recency_norm`, `author_score`, `score` — see [ranking.md](ranking.md).
