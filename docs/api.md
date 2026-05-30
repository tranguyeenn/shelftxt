# API reference

Endpoint design principles and categories: [system-design/api-design.md](system-design/api-design.md).

OpenAPI (live): `{backend}/docs`

## Base URLs

| Environment | Backend | Browser |
|-------------|---------|---------|
| Local | `http://127.0.0.1:8000` | `http://localhost:3000` via `/api/*` Vite proxy |
| Production | `https://shelftxt.onrender.com` | `https://shelftxt.vercel.app` → Render direct |

Client helper: `frontend/src/lib/api.ts` (`apiUrl`, `fetchJson`).

Override production API: `VITE_API_BASE_URL` in frontend env.

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

### Books — list

| Method | Path | Description |
|--------|------|-------------|
| GET | `/books` | Full library as JSON array of CSV rows |

NaN values → `null`.

---

### Books — create / update (title key)

| Method | Path | Description |
|--------|------|-------------|
| POST | `/books` | Add TBR book |
| PATCH | `/books` | Update metadata or shelf via `move_to` |
| DELETE | `/books?title=` | Delete by exact title |

**POST body:** `{ "title", "author", "total_pages"? }` → `{ "message": "Book added" }`

**PATCH body:** `{ "title" (required), "new_title"?, "author"?, "total_pages"?, "pages_read"?, "move_to"?, "rating"?, "date_read"? }`

`move_to`: `want` | `reading` | `read` | `dnf`

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

---

### Import / export / clear

| Method | Path | Description |
|--------|------|-------------|
| POST | `/books/import` | Bulk add from JSON |
| GET | `/books/export` | Download `shelftxt-library.csv` |
| POST | `/books/clear` | Remove all books |

**Import body:** `{ "books": [{ "title", "author"?, "total_pages"? }] }`  
**Import response:** `{ "imported", "skipped" }`

**Clear body:** `{ "confirm": true }` (required)  
**Clear response:** `{ "message", "deleted" }`

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

---

## Errors

| Code | Meaning |
|------|---------|
| 400 | Business rule violation (`detail` string) |
| 404 | Book not found |
| 422 | Invalid request body (Pydantic) |

---

## Pydantic models

Defined in `backend/schemas/books.py`: `AddBook`, `PatchBook`, `ImportBooks`, `BookProgressPatch`, `ClearLibraryRequest`.

Legacy monolith `backend/api_draft.py` is **not** loaded by production app.
