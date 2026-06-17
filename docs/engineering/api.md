# API reference

Reference for HTTP behavior as implemented in `backend/routes/`. OpenAPI lives at `/docs` when the API is running.

All book and recommendation endpoints are multi-user and require a Supabase access token. `/health` is public.

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

## Authentication

Protected requests must include:

```http
Authorization: Bearer <supabase_access_token>
```

The frontend gets this token from the persisted Supabase session in `frontend/src/lib/api.ts` and attaches it automatically. Direct API clients must do the same.

Backend verification happens in `backend/auth/dependencies.py`:

- `HTTPBearer` requires the Authorization header.
- The backend validates the access token with `GET {SUPABASE_URL}/auth/v1/user`,
  using `Authorization: Bearer <token>` and backend `SUPABASE_ANON_KEY` as the
  Supabase `apikey`.
- The backend loads the matching `profiles` row.
- Book CRUD and recommendation services receive `current_user.id` and scope data by that user id.

Missing, expired, or invalid tokens return **401**. Missing Supabase backend configuration returns **500**.

### Login and registration flow

Registration uses `supabase.auth.signUp({ email, password, options: { data: { username } } })`. When Supabase returns an immediate session, the frontend creates a `profiles` row. If email confirmation is enabled and no session is returned, the profile is created after confirmation/session restoration.

Login uses `supabase.auth.signInWithPassword({ email, password })`. Session persistence is configured in `frontend/src/lib/supabase.ts` with `persistSession: true`, `autoRefreshToken: true`, and `detectSessionInUrl: true`. Protected frontend routes render only after the session is known.

Logout uses `supabase.auth.signOut()` and clears the local session.

### Authenticated request examples

```ts
const { data, error } = await supabase.auth.signInWithPassword({
  email: "reader@example.com",
  password: "correct-horse-battery-staple"
});

const token = data.session?.access_token;
```

```bash
curl -H "Authorization: Bearer $SUPABASE_ACCESS_TOKEN" \
  http://127.0.0.1:8000/books
```

```bash
curl -X POST http://127.0.0.1:8000/books \
  -H "Authorization: Bearer $SUPABASE_ACCESS_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"title":"Dune","author":"Frank Herbert","total_pages":688}'
```

```bash
curl -X PATCH http://127.0.0.1:8000/books/book-id-or-isbn/progress \
  -H "Authorization: Bearer $SUPABASE_ACCESS_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"status":"reading","pages_read":120}'
```

```bash
curl -X DELETE http://127.0.0.1:8000/books/book-id-or-isbn \
  -H "Authorization: Bearer $SUPABASE_ACCESS_TOKEN"
```

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

Each object in `results` uses CSV-compatible column names. NaN values → `null`.

**Notes:** Pagination reduces response payload size and the route uses the PostgreSQL-backed repository layer scoped by authenticated user. Invalid `page` / `limit` (zero, negative, non-integer, `limit` > 100) return **422**. Empty library: `total: 0`, `results: []`.

---

### Books — create / update (title key)

| Method | Path | Description |
|--------|------|-------------|
| POST | `/books` | Add TBR book for current user |
| PATCH | `/books` | Update current user's book metadata or shelf via `move_to` |
| DELETE | `/books?title=` | Delete current user's book by exact title |

**POST body:** `{ "title", "author", "total_pages"? }` → `{ "message": "Book added" }`

**Side effects:** New PostgreSQL row with `Read Status=to-read`, a new `ISBN/UID`, and `user_id` set to the authenticated profile id.

**PATCH body:** `{ "title" (required), "new_title"?, "author"?, "total_pages"?, "pages_read"?, "move_to"?, "rating"?, "date_read"? }`

`move_to`: `want` | `reading` | `read` | `dnf`

**Errors:** 404 title not found; 400 rename collision, reading without pages, read without valid rating.

---

### Books — progress (id key, UI primary)

| Method | Path | Description |
|--------|------|-------------|
| GET | `/books/{book_id}` | Get one current-user book |
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

**Errors:** 404 unknown id for the current user; 400 invalid pages, missing total pages for reading/completed.

---

### Import / export / clear

| Method | Path | Description |
|--------|------|-------------|
| POST | `/books/import` | Bulk add from JSON |
| GET | `/books/export` | Download `shelftxt-library.csv` |
| POST | `/books/clear` | Remove all books |

**Import body:** `{ "books": [{ "title", "author"?, "total_pages"? }] }`  
**Import response:** `{ "imported", "skipped" }`

**Skip rules:** empty title; duplicate `Title` in the current user's library (case-sensitive).

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

Empty current-user TBR → `[]`. Cache invalidated automatically when books change.

**Caching:** in-process LRU; invalidated on book mutations.

---

## Errors

| Code | Meaning |
|------|---------|
| 400 | Business rule violation (`detail` string) |
| 401 | Missing, invalid, expired, or profile-less Supabase token |
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
- `/books` returns a pagination wrapper; recommendations return a top-level array
- CSV export is raw file download of the authenticated user's library, not JSON

### Clear validation

- Request bodies validated by Pydantic at the boundary
- Response models document paginated book list and common response shapes
- Progress rules enforced in service layer with explicit HTTPException messages

### Stable CSV compatibility

- `BOOKS_COLUMNS` order preserved on export
- Import/export is compatibility I/O; PostgreSQL is the source of truth

### Frontend-friendly JSON

- NaN → `null` on `GET /books`
- Progress endpoint returns normalized `status` enum for UI
- Recommendation items bundle explanation + similar books to avoid N+1 client calls

---

## Future API ideas (not implemented)

Clearly marked as **not current**:

- Server-persisted user settings (theme, recommendation style)
- Webhook or async import for large files
- Cursor-based pagination for very large libraries

Do not document these as available until routes exist in `backend/routes/`.
