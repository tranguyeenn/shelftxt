# Frontend

Vite + React + Tailwind app under `frontend/`. Client-side routing via React Router.

## Stack

- React 19, Vite 6, Tailwind CSS 4
- `react-router-dom` for pages
- `papaparse` for CSV import (Settings — planned)

## Routes

| Path | Page |
|------|------|
| `/` | Dashboard — primary recommendation + score breakdown |
| `/ranking` | TBR ranking table |
| `/book/:id` | Book detail (explainability tabs) |
| `/add` | Add book form |
| `/system` | Model notes & roadmap |
| `/settings` | Preferences, import/export, danger zone |

## How the browser reaches the API

| Environment | Mechanism |
|-------------|-----------|
| **Local dev** | `/api/*` → Vite proxy → `127.0.0.1:8000` |
| **Production (Vercel)** | `VITE_API_BASE_URL` or direct Render default; `/api/*` rewrites in `vercel.json` |

```typescript
// src/lib/api.ts
apiUrl("/books")  // dev → /api/books → proxy → backend
```

Copy [`frontend/.env.local.example`](../frontend/.env.local.example) for `VITE_API_BASE_URL`.

## Dev

```bash
cd frontend && npm install && npm run dev
```

Open http://localhost:3000 (API on :8000).

## Build

```bash
cd frontend && npm run build
```

Output: `frontend/dist/` (static SPA).
