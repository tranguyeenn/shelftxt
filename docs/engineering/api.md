# API reference

Reference for HTTP behavior as implemented in `backend/routes/`. OpenAPI lives at `/docs` when the API is running.

---

## Base URLs

| Environment | Backend | Browser |
|-------------|---------|---------|
| Local | `http://127.0.0.1:8000` | `http://localhost:3000` via `/api/*` Vite proxy |
| Production | `https://shelftxt.onrender.com` | `https://shelftxt.vercel.app` → Render direct |

Client helpers: `frontend/src/lib/api.ts` (`apiUrl`, `fetchJson`); `frontend/src/lib/books.ts` (`fetchAllLibraryBooks` for multi-page library loads).

Override production API: `VITE_API_BASE_URL` in frontend env.

Production UI calls Render directly; local dev uses Vite proxy `/api/*` → `127.0.0.1:8000`.

---

## Endpoints

### Health

| Method | Path | Description |
|--------|------|-------------|
| GET, HEAD | `/health` | Liveness check |

```json
{ "status": "healthy", "service": "ShelfTxt" }
```

---

### Books — list (paginated)

| Method | Path | Description |
|--------|------|-------------|
| GET | `/books` | Paginated library (`?page=1&limit=20`) |

**Query parameters:**

| Param | Default | Constraints |
|-------|---------|-------------|
| `page` | `1` | integer ≥ 1 |
| `limit` | `20` | integer 1–100 |

**Response:**

```json
{
  "page": 1,
  "limit": 20,
  "total": 120,
  "results": [
    {
      "Title": "Example",
      "Authors": "Author",
      "ISBN/UID": "…",
      "Read Status": "to-read",
      "Star Rating": null,
      "Last Date Read": null,
      "Progress (%)": 0,
      "Pages Read": 0,
      "Total Pages": null
    }
  ]
}
```

Each object in `results` uses CSV column names. NaN values → `null`.

**Notes:** Pagination reduces response payload size and the route uses the PostgreSQL-backed repository layer. Invalid `page` / `limit` (zero, negative, non-integer, `limit` > 100) return **422**. Empty library: `total: 0`, `results: []`.

---

### Books — create / update (title key)

| Method | Path | Description |
|--------|------|-------------|
| POST | `/books` | Add TBR book |
| PATCH | `/books` | Update metadata or shelf via `move_to` |
| DELETE | `/books?title=` | Delete by exact title |

**POST body:** `{ "title", "author", "total_pages"? }` → `{ "message": "Book added" }`

**Side effects:** New PostgreSQL row with `Read Status=to-read` and a new `ISBN/UID`.

**PATCH body:** `{ "title" (required), "new_title"?, "author"?, "total_pages"?, "pages_read"?, "move_to"?, "rating"?, "date_read"? }`

`move_to`: `want` | `reading` | `read` | `dnf`

**Errors:** 404 title not found; 400 rename collision, reading without pages, read without valid rating.

---

### Books — progress (id key, UI primary)

| Method | Path | Description |
|--------|------|-------------|
| PATCH | `/books/{book_id}/progress` | Update status and pages |
| DELETE | `/books/{book_id}` | Delete one book |

**Progress body:**

```json
{ "status": "not_started | reading | completed", "pages_read": 120 }
```

**Progress response:**

```json
{
  "book": {
    "id", "title", "author", "status",
    "total_pages", "pages_read", "progress_pct", "rating", "read_status"
  }
}
```

`book_id` = `ISBN/UID`.

**Errors:** 404 unknown id; 400 invalid pages, missing total pages for reading/completed.

---

### Import / export / clear

| Method | Path | Description |
|--------|------|-------------|
| POST | `/books/import` | Bulk add from JSON |
| GET | `/books/export` | Download `shelftxt-library.csv` |
| POST | `/books/clear` | Remove all books |

**Import body:** `{ "books": [{ "title", "author"?, "total_pages"? }] }`  
**Import response:** `{ "imported", "skipped" }`

**Skip rules:** empty title; duplicate `Title` (case-sensitive).

**Clear body:** `{ "confirm": true }` (required)  
**Clear response:** `{ "message", "deleted" }`

**Errors:** 400 if `confirm` is not true

---

### Recommendations

| Method | Path | Description |
|--------|------|-------------|
| GET | `/recommend?style=` | Top 10 TBR picks |

**Query `style`:** `balanced` (default), `popular`, `discovery`

**Response:** array of:

```json
{
  "book": { "id", "title", "author" },
  "score": 0.82,
  "explanation": "...",
  "similar_books": [{ "id", "title", "author" }]
}
```

Empty TBR → `[]`. Cache invalidated automatically when books change.

**Caching:** in-process LRU; invalidated on book mutations.

---

## Errors

| Code | Meaning |
|------|---------|
| 400 | Business rule violation (`detail` string) |
| 404 | Book not found |
| 422 | Invalid request body (Pydantic) |

Frontend should display `detail` when present (`frontend/src/lib/api.ts`).

---

## Pydantic models

Defined in `backend/schemas/books.py`: `AddBook`, `PatchBook`, `ImportBooks`, `BookProgressPatch`, `ClearLibraryRequest`, `BookResponse`, `BooksPage`, `MessageResponse`, and `ImportResult`.

Legacy monolith `backend/api_draft.py` is **not** loaded by production app.

---

## API design principles

### Predictable responses

- Mutations return small JSON messages or the updated `book` object for progress
- Lists return arrays (never `{ data: ... }` wrapper today)
- CSV export is raw file download, not JSON

### Clear validation

- Request bodies validated by Pydantic at the boundary
- Response models document paginated book list and common response shapes
- Progress rules enforced in service layer with explicit HTTPException messages

### Stable CSV compatibility

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
- Cursor-based pagination for very large libraries

Do not document these as available until routes exist in `backend/routes/`.
