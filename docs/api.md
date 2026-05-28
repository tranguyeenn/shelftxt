# API reference

## Base URLs

| Environment | Backend | Browser (UI) |
|-------------|---------|--------------|
| Local dev | `http://127.0.0.1:8000` | `http://localhost:3000` — calls `/api/*` proxy |
| Production | `https://shelftxt.onrender.com` | `https://shelftxt.vercel.app` — calls backend directly |

OpenAPI (Swagger): `{backend}/docs`

## Client vs proxy paths

**Production:** Browser uses `frontend/lib/apiUrl.ts` → Render paths (`/books`, `/recommend`, …).

**Local dev:** Browser uses `/api/books`, etc.; Next.js route handlers forward via `frontend/lib/backendUrl.ts`.

| Client call (prod) | Backend path | Methods |
|--------------------|----------------|---------|
| `apiUrl("/books")` | `/books` | GET, POST, PATCH, DELETE |
| `apiUrl("/books/{id}/progress")` | `/books/{book_id}/progress` | PATCH |
| `apiUrl("/books/import")` | `/books/import` | POST |
| `apiUrl("/recommend")` | `/recommend` | GET |

Override with `NEXT_PUBLIC_API_BASE_URL` (prod) or `API_BASE_URL` (dev proxy).

---

## `GET` / `HEAD` `/health`

**Response 200**

```json
{ "status": "healthy", "service": "ShelfTxt" }
```

Used by Render keep-warm scheduler (see [deployment.md](deployment.md)).

---

## `GET` `/books`

Returns all rows from `books.csv`.

**Response 200** — JSON array of objects; `NaN` → `null`.

Example row:

```json
{
  "Title": "Dune",
  "Authors": "Frank Herbert",
  "ISBN/UID": "1710000000.0",
  "Read Status": "to-read",
  "Star Rating": null,
  "Last Date Read": null,
  "Progress (%)": 0,
  "Pages Read": 0,
  "Total Pages": 688
}
```

---

## `POST` `/books`

Add a book to the want-to-read shelf.

**Body**

```json
{
  "title": "string",
  "author": "string",
  "total_pages": 400
}
```

`total_pages` is optional.

**Response 200**

```json
{ "message": "Book added" }
```

New rows: `Read Status` = `to-read`, `Progress (%)` = 0, `Pages Read` = 0, new `ISBN/UID` from timestamp.

---

## `PATCH` `/books`

Update metadata or move between shelves.

**Body**

```json
{
  "title": "Current Title",
  "new_title": "Optional Rename",
  "author": "Optional Author",
  "total_pages": 500,
  "pages_read": 120,
  "move_to": "want | reading | read | dnf",
  "rating": 4.5,
  "date_read": "2024-06-01"
}
```

Only `title` is required. Unset fields are left unchanged.

**Errors**

| Status | Condition |
|--------|-----------|
| 404 | Title not found |
| 400 | Rename collision; reading without total pages; read without rating 1–5 |

**Response 200**

```json
{ "message": "Book updated" }
```

---

## `DELETE` `/books`

**Query:** `title` (required, min length 1)

**Response 200**

```json
{ "message": "Book deleted" }
```

**404** if title not found.

---

## `PATCH` `/books/{book_id}/progress`

Update reading status and pages read. `book_id` is the `ISBN/UID` value.

**Body**

```json
{
  "status": "not_started | reading | completed",
  "pages_read": 120
}
```

**Response 200**

```json
{
  "book": {
    "id": "1700000000.0",
    "title": "Dune",
    "author": "Frank Herbert",
    "status": "reading",
    "total_pages": 500,
    "pages_read": 120,
    "progress_pct": 24.0
  }
}
```

**Validation**

- `pages_read >= 0`
- `pages_read <= total_pages` when total pages is set
- `completed` requires `pages_read == total_pages`
- If `pages_read == total_pages` while status is `reading`, status becomes `completed` automatically

---

## `POST` `/books/import`

Bulk import from UI CSV tab (not the flexible Python pipeline).

**Body**

```json
{
  "books": [
    { "title": "Snow Crash", "author": "Neal Stephenson", "total_pages": 480 },
    { "title": "Duplicate", "author": "Someone" }
  ]
}
```

**Response 200**

```json
{ "imported": 1, "skipped": 1 }
```

Skipped when title is empty or already exists (case-sensitive title match on stored `Title`).

---

## `GET` `/recommend`

Returns up to **10** ranked TBR recommendations with explanations and similar finished books.

**Response 200**

- Empty TBR: `[]`
- Otherwise: array of recommendation objects

```json
[
  {
    "book": { "id": "1", "title": "Snow Crash", "author": "Neal Stephenson" },
    "score": 0.82,
    "explanation": "Recommended because you have finished 2 book(s) by Neal Stephenson…",
    "similar_books": [
      { "id": "2", "title": "Cryptonomicon", "author": "Neal Stephenson" }
    ]
  }
]
```

See [ranking.md](ranking.md) for scoring details.

Recommendation cache is cleared automatically when books are added, updated, deleted, or imported.

---

## Schema reference (Pydantic)

**Handlers:** `backend/routes/` · **Models:** `backend/schemas/books.py` · **App:** `backend/api.py`

`backend/api_draft.py` is legacy — not loaded by `uvicorn backend.api:app`.

| Model | Used by |
|-------|---------|
| `AddBook` | POST `/books` |
| `PatchBook` | PATCH `/books` |
| `BookProgressPatch` | PATCH `/books/{book_id}/progress` |
| `ImportBooks` / `ImportRow` | POST `/books/import` |
