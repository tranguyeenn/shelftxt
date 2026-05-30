# Frontend

Reader-facing SPA built with **Vite 6**, **React 19**, **TypeScript**, and **Tailwind CSS 4**.

Design goals and flows: [system-design/frontend-design.md](system-design/frontend-design.md).

---

## Routes

| Path | Page |
|------|------|
| `/` | Dashboard — top recommendation + stats |
| `/library` | Full shelf, status/progress editing, delete |
| `/ranking` | Top 10 recommendations with explanations |
| `/book/:id` | Book detail, progress editor, delete |
| `/add` | Add book form |
| `/insights` | Reading patterns (non-technical) |
| `/settings` | Import/export, preferences, appearance |
| `/system` | Redirects to `/insights` |

Router: `frontend/src/App.tsx` · Layout: `AppShell` + `Sidebar`

---

## API access

| Environment | How |
|-------------|-----|
| **Local dev** | `/api/*` → Vite proxy → `127.0.0.1:8000` (`vite.config.ts`) |
| **Production** | Direct Render URL via `apiUrl()` in `src/lib/api.ts` |

Optional: set `VITE_API_BASE_URL` for a custom API host.

Recommendations pass `?style=` from user settings (`src/lib/userSettings.ts`).

---

## Key modules

| Path | Role |
|------|------|
| `src/lib/books.ts` | CSV row → `ApiBook`, shelf derivation |
| `src/lib/bookProgress.ts` | Progress validation + PATCH helper |
| `src/lib/libraryExport.ts` | Export download, clear library, delete book |
| `src/lib/insights.ts` | Insights page aggregations |
| `src/contexts/UserSettingsContext.tsx` | Theme, accent, recommendation style |
| `components/books/BookProgressEditor.tsx` | Status + pages editor |
| `features/recommendations/` | Recommendation cards and list |

User settings (theme, accent, compact mode, recommendation style) persist in **localStorage** only.

---

## Commands

```bash
cd frontend && npm install && npm run dev   # http://localhost:3000
cd frontend && npm run build              # tsc + vite → dist/
```

Backend must run on `:8000` for local proxy unless using `VITE_API_BASE_URL`.

---

## Deployment

Static build on Vercel. Rewrites in `frontend/vercel.json` proxy `/api/*` to Render when needed.

See [deployment.md](deployment.md).
