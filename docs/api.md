# API reference

## Base URLs

| Environment | Backend | Browser-facing (proxied) |
|-------------|---------|---------------------------|
| Local dev | `http://127.0.0.1:8000` | `http://localhost:3000/api/...` |
| Production | `https://shelftxt.onrender.com` (default) | Same host as deployed Next app |

OpenAPI (Swagger): `{backend}/docs`

## Next.js proxy routes

The browser calls same-origin routes; route handlers forward to the backend using `frontend/lib/backendUrl.ts`.

| Proxy path | Methods | Upstream |
|------------|---------|----------|
| `/api/books` | GET, POST, PATCH, DELETE | `/books` |
| `/api/books/import` | POST | `/books/import` |
| `/api/books/remove` | POST | `/books/remove` |
| `/api/recommend` | GET | `/recommend` |

Override backend target with `API_BASE_URL` or `NEXT_PUBLIC_API_BASE_URL` in `frontend/.env.local`.

---

## `GET` / `HEAD` `/health`

**Response 200**

```json
{ "status": "healthy", "service": "LibroRank" }
```

Used by Render keep-warm scheduler (see [development.md](development.md)).

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

## `POST` `/books/remove`

Same behavior as `DELETE /books`. Accepts JSON body for hosts that return **405** on DELETE.

**Body**

```json
{ "title": "Book Title" }
```

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

Runs normalization and TBR scoring on loaded data, then `recommend_one()`.

**Response 200**

- Empty TBR: `[]`
- Otherwise: array with **one** book (top-5 sample), including `score` when present

```json
[
  {
    "Title": "Snow Crash",
    "Authors": "Neal Stephenson",
    "Read Status": "to-read",
    "score": 0.82
  }
]
```

See [ranking.md](ranking.md) for algorithm details.

---

## Pydantic models

Defined in `backend/api.py`:

| Model | Used by |
|-------|---------|
| `AddBook` | POST `/books` |
| `PatchBook` | PATCH `/books` |
| `ImportBooks` / `ImportRow` | POST `/books/import` |
| `RemoveBook` | POST `/books/remove` |
| `UpdateProgress`, `FinishBook`, `DNFBook` | Legacy/unused in current routes |
