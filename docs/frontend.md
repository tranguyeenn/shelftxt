# Frontend

Next.js  App Router app under `frontend/`. Single-page UI at `app/page.tsx`.

## Stack

- React client components (`"use client"`)
- `papaparse` for client-side CSV parsing on Import tab
- Route handlers proxy to FastAPI (no direct browser → :8000 in dev)

## Backend URL resolution

`frontend/lib/backendUrl.ts`:

```typescript
process.env.API_BASE_URL ??
process.env.NEXT_PUBLIC_API_BASE_URL ??
(process.env.NODE_ENV === "development"
  ? "http://127.0.0.1:8000"
  : "https://shelftxt.onrender.com")
```

## Proxy route handlers

| File | Forwards to |
|------|-------------|
| `app/api/books/route.ts` | GET/POST/PATCH/DELETE `/books` |
| `app/api/books/import/route.ts` | POST `/books/import` |
| `app/api/books/remove/route.ts` | POST `/books/remove` |
| `app/api/recommend/route.ts` | GET `/recommend` |

Errors from upstream are surfaced via `frontend/lib/upstreamError.ts`.

## Tabs

| Tab ID | Label | Behavior |
|--------|-------|----------|
| `library` | Library | Load shelves, CRUD, shelf moves |
| `import` | Import | Parse CSV, bulk POST import |
| `discover` | Discover | Fetch one recommendation |

## Library tab

**Data load:** `GET /api/books` on mount and after mutations.

**Shelves:** Client-side grouping via `shelfLabel()` — see [data-model.md](data-model.md).

**Add book:** `POST /api/books` with title, author, optional total pages.

**Edit:** Modal → `PATCH /api/books` with `new_title`, `author`, `total_pages`, or `move_to`.

**Delete:** `POST /api/books/remove` with `{ title }` (not DELETE, for hosting compatibility).

**Shelf actions (examples):**

| Action | PATCH payload |
|--------|----------------|
| Start reading | `move_to: "reading"`, `pages_read`, needs `total_pages` on book |
| Mark read | `move_to: "read"`, `rating`, optional `date_read` |
| Move to want | `move_to: "want"` |
| DNF | `move_to: "dnf"` |

## Import tab

1. User selects or drags a `.csv` file.
2. `Papa.parse` reads rows in the browser.
3. Maps flexible header names (e.g. `Title`, `title`, `Book Title`) to title/author/pages.
4. `POST /api/books/import` with `{ books: [...] }`.
5. Shows imported/skipped counts from response.

Does **not** use the Python flexible pipeline or mapping JSON.

## Discover tab

`GET /api/recommend` → displays single suggested book or empty state.

## Types (client)

Key shapes in `page.tsx`:

- `BackendBook` — mirrors CSV/API columns with quoted keys for `"Read Status"`, etc.
- `ApiBook` — recommendation payload subset
- `ShelfKind` — `"want" | "reading" | "read" | "dnf"`

## Local development

```bash
cd frontend
npm install
npm run dev
```

Requires FastAPI on port 8000 unless `API_BASE_URL` points elsewhere.

```bash
# from repo root
uvicorn backend.api:app --reload
```

Open `http://localhost:3000`.

## Deploy on Vercel

**Project settings (required for monorepo):**

| Setting | Value |
|---------|--------|
| **Root Directory** | `frontend` |
| **Framework Preset** | Next.js |

**Environment variable:**

| Key | Value |
|-----|--------|
| `API_BASE_URL` | `https://shelftxt.onrender.com` |

Redeploy after changing env vars or `backendUrl.ts`.

`frontend/vercel.json` includes rewrites that proxy `/api/*` → Render when route handlers are unavailable. After deploy, verify:

- https://shelftxt.vercel.app/api/books → JSON (not 404)
- https://shelftxt.vercel.app/ → library loads

Also add your Vercel URL to FastAPI CORS in `backend/api.py` (`https://shelftxt.vercel.app`).

## Build / deploy notes

- Production default API host is Render backend URL.
- Set `API_BASE_URL` when frontend and API are on different domains.
- CORS on the API must include the frontend origin.
