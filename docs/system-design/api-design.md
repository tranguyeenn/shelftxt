# API design

Reference for HTTP behavior as implemented in `backend/routes/`. OpenAPI lives at `/docs` when the API is running.

**Base URLs:** see [api.md](../api.md). Production UI calls Render directly; local dev uses Vite proxy `/api/*` → `127.0.0.1:8000`.

---

## Endpoint categories

### Health

| Method | Path | Purpose |
|--------|------|---------|
| GET, HEAD | `/health` | Liveness for Render and keep-warm job |

**Response:** `{ "status": "healthy", "service": "ShelfTxt" }`

---

### Books — read

| Method | Path | Purpose |
|--------|------|---------|
| GET | `/books` | List entire library as JSON array of CSV rows |

**Output:** Array of objects with columns `Title`, `Authors`, `ISBN/UID`, `Read Status`, `Star Rating`, `Last Date Read`, `Progress (%)`, `Pages Read`, `Total Pages`. NaN → `null`.

**Errors:** None specific; empty library returns `[]`.

---

### Books — create / update (legacy title key)

| Method | Path | Purpose |
|--------|------|---------|
| POST | `/books` | Add TBR book |
| PATCH | `/books` | Update metadata or shelf via `move_to` |
| DELETE | `/books?title=` | Delete by exact title |

#### POST `/books`

**Input:** `{ "title", "author", "total_pages"? }`

**Output:** `{ "message": "Book added" }`

**Side effects:** New row with `Read Status=to-read`, new `ISBN/UID`, cache invalidation.

#### PATCH `/books`

**Input:** `{ "title" (required), "new_title"?, "author"?, "total_pages"?, "pages_read"?, "move_to"?, "rating"?, "date_read"? }`

**Output:** `{ "message": "Book updated" }`

**Errors:** 404 title not found; 400 rename collision, reading without pages, read without valid rating.

#### DELETE `/books`

**Input:** query `title`

**Output:** `{ "message": "Book deleted" }`

**Errors:** 404

---

### Books — progress (id key, UI primary)

| Method | Path | Purpose |
|--------|------|---------|
| PATCH | `/books/{book_id}/progress` | Update reading status and pages |

**Input:**

```json
{
  "status": "not_started | reading | completed",
  "pages_read": 0
}
```

**Output:**

```json
{
  "book": {
    "id", "title", "author", "status",
    "total_pages", "pages_read", "progress_pct",
    "rating", "read_status"
  }
}
```

**Errors:** 404 unknown id; 400 invalid pages, missing total pages for reading/completed.

---

### Books — delete by id

| Method | Path | Purpose |
|--------|------|---------|
| DELETE | `/books/{book_id}` | Remove one book (UI uses this) |

**Output:** `{ "message": "Book deleted" }`

**Errors:** 404

---

### Import / export

| Method | Path | Purpose |
|--------|------|---------|
| POST | `/books/import` | Bulk add from JSON (UI CSV tab) |
| GET | `/books/export` | Download library CSV |

#### POST `/books/import`

**Input:** `{ "books": [{ "title", "author"?, "total_pages"? }] }`

**Output:** `{ "imported": n, "skipped": n }`

**Skip rules:** empty title; duplicate `Title` (case-sensitive).

#### GET `/books/export`

**Output:** `text/csv` attachment `shelftxt-library.csv`

---

### Library clear

| Method | Path | Purpose |
|--------|------|---------|
| POST | `/books/clear` | Remove all books |

**Input:** `{ "confirm": true }` — must be literal `true`

**Output:** `{ "message": "Library cleared", "deleted": n }`

**Errors:** 400 if `confirm` is not true

---

### Recommendations

| Method | Path | Purpose |
|--------|------|---------|
| GET | `/recommend` | Top 10 TBR recommendations |

**Query:** `style` optional — `balanced` (default), `popular`, `discovery`

**Output:** Array of:

```json
{
  "book": { "id", "title", "author" },
  "score": 0.0,
  "explanation": "string",
  "similar_books": [{ "id", "title", "author" }]
}
```

Empty TBR → `[]`.

**Caching:** in-process LRU; invalidated on book mutations.

---

## Error handling expectations

| Code | When |
|------|------|
| 200 | Success |
| 400 | Business rule violation (validation message in `detail`) |
| 404 | Book not found |
| 422 | Pydantic request validation (malformed body) |

Frontend should display `detail` when present (`frontend/src/lib/api.ts`).

---

## API design principles

### Predictable responses

- Mutations return small JSON messages or the updated `book` object for progress
- Lists return arrays (never `{ data: ... }` wrapper today)
- CSV export is raw file download, not JSON

### Clear validation

- Request bodies validated by Pydantic at the boundary
- Progress rules enforced in service layer with explicit HTTPException messages

### Stable CSV behavior

- `BOOKS_COLUMNS` order preserved on export
- Load repairs missing columns without crashing

### Frontend-friendly JSON

- NaN → `null` on `GET /books`
- Progress endpoint returns normalized `status` enum for UI
- Recommendation items bundle explanation + similar books to avoid N+1 client calls

---

## Future API ideas (not implemented)

Clearly marked as **not current**:

- `GET /books/{book_id}` single resource
- Server-persisted user settings (theme, recommendation style)
- Auth and multi-tenant libraries
- Webhook or async import for large files
- Paginated `GET /books`

Do not document these as available until routes exist in `backend/routes/`.
