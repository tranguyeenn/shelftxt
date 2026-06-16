# Frontend

The ShelfTxt web UI is a **reader-facing** tool for managing a personal library and understanding recommendations—not a developer console for the API.

Stack: **Vite 6**, **React 19**, **TypeScript**, **Tailwind CSS 4**, **React Router 7**.

Entry: `frontend/src/main.tsx` → `App.tsx` with `AuthProvider` and `UserSettingsProvider` wrapping routes.

---

## Route map

| Path | Page | Role |
|------|------|------|
| `/login` | Login | Supabase email/password login |
| `/register` | Register | Supabase signup + profile creation |
| `/` | Dashboard | Top recommendation + stats |
| `/library` | Library | Full shelf with status/progress editing |
| `/ranking` | Recommendations | Top 10 with explanations |
| `/book/:id` | Book detail | Progress editor, delete, insight if ranked |
| `/add` | Add book | Manual TBR entry |
| `/insights` | Insights | Reading patterns (replaces old System page) |
| `/settings` | Settings | Import/export, preferences, appearance |
| `/system` | redirect → `/insights` | Backward compatibility |

Router: `frontend/src/App.tsx` · Protected routes: `components/auth/ProtectedRoute.tsx` · Layout: `AppShell` + `Sidebar`

---

## Main user flows

### Authenticate

1. Register on `/register` with email, password, and username.
2. Supabase creates the auth user; the frontend creates a matching `profiles` row when a session is available.
3. Login on `/login` with `supabase.auth.signInWithPassword()`.
4. Supabase persists and refreshes the browser session.
5. Logout calls `supabase.auth.signOut()`.

Protected app routes require a session. API helpers attach the current Supabase access token as `Authorization: Bearer <token>`.

### View library

1. `GET /books` with Bearer token (paginated; UI uses `fetchAllLibraryBooks()` to load all pages at max `limit=100`)
2. Map rows to `ApiBook` via `recordToApiBook()` (`lib/books.ts`)
3. Filter by status: not started, reading, completed
4. Cards show title, author, pages, progress, status badge

### Add book

1. Form on `/add` → `POST /books` with title, author, optional total pages and Bearer token
2. Redirect or refresh library data

### Edit status / progress

1. Library or book detail → `BookProgressEditor`
2. Client validation (`lib/bookProgress.ts`) — non-negative pages, within total, completed rules
3. `PATCH /books/{id}/progress` with `{ status, pages_read }`
4. Refresh local state from response `book` object

Legacy shelf moves via `PATCH /books` + `move_to` exist but are not the primary UI path.

### Import CSV

1. Settings → file input → Papa Parse client-side
2. Preview first rows
3. `POST /books/import` with parsed JSON and Bearer token

### Export CSV

1. Settings → Export library → `GET /books/export` → browser download

### Clear / delete

- **Clear all:** Settings → confirm → `POST /books/clear`
- **Delete one:** Library card or book detail → confirm → `DELETE /books/{id}`

### View recommendations

1. Dashboard or `/ranking` → `GET /recommend?style=` from user settings
2. Cards show rank, score, explanation, similar books
3. Explanation block hidden when user disables it in settings

### Understand recommendations

- Copy comes from backend `explanation` string
- Optional "Similar to" list from finished reads
- Insights page summarizes patterns without exposing API routes

---

## Reader-focused boundary

**Do show:** reading status, progress, why a book ranked, library stats

**Do not show:** endpoint lists, stack names, CSV file paths, cache implementation

The old "System" page was removed for this reason. Technical docs belong in `docs/engineering/`, not the product UI.

---

## API access

| Environment | How |
|-------------|-----|
| **Local dev** | `/api/*` → Vite proxy → `127.0.0.1:8000` (`vite.config.ts`) |
| **Production** | Direct Render URL via `apiUrl()` in `src/lib/api.ts` |

Optional: set `VITE_API_BASE_URL` for a custom API host.

Recommendations pass `?style=` from user settings (`src/lib/userSettings.ts`).

`frontend/src/lib/api.ts`:

- `apiUrl(path)` — Render in prod, `/api` proxy locally
- `apiFetch(path, init)` — attaches Supabase `Authorization: Bearer <access_token>`
- `fetchJson<T>()` — throws with server `detail` when available

Types: `lib/types.ts` for `ApiBook`, `RecommendationItem`, etc.

---

## State and settings

| State | Storage | Synced to backend |
|-------|---------|-------------------|
| Auth session | Supabase browser storage | yes, through Supabase Auth |
| Profile | PostgreSQL `profiles` | yes |
| Library | PostgreSQL via authenticated API; CSV import/export compatibility | yes |
| Recommendation style | `localStorage` | no (passed as query param only) |
| Show explanations | `localStorage` | no |
| Compact mode | `localStorage` + `data-compact` on `<html>` | no |
| Accent color | `localStorage` + CSS variables | no |
| Theme (dark/light) | `localStorage` + `data-theme` | no |

`UserSettingsContext` provides settings to recommendation components.

---

## Key modules

| Path | Role |
|------|------|
| `src/lib/supabase.ts` | Supabase browser client and session persistence settings |
| `src/lib/api.ts` | API URL resolution, auth header attachment, fetch helpers |
| `src/lib/books.ts` | CSV row → `ApiBook`, `fetchAllLibraryBooks()` (paginated GET /books) |
| `src/lib/bookProgress.ts` | Progress validation + PATCH helper |
| `src/lib/libraryExport.ts` | Export download, clear library, delete book |
| `src/lib/insights.ts` | Insights page aggregations |
| `src/contexts/AuthContext.tsx` | Session state, login, register, logout, profile creation |
| `src/contexts/UserSettingsContext.tsx` | Theme, accent, recommendation style |
| `components/auth/ProtectedRoute.tsx` | Redirect unauthenticated users away from app routes |
| `components/books/BookProgressEditor.tsx` | Status + pages editor |
| `features/recommendations/` | Recommendation cards and list |

---

## Design priorities

1. **Clarity** — labels like "Not started", "Reading", "Completed"; plain recommendation text
2. **Low friction** — edit progress inline; minimal steps to import
3. **Useful filtering** — library status filters; insights summaries
4. **Minimal overthinking** — no heavy configuration required to get value
5. **Mobile-friendly direction** — responsive grids and sidebar; dedicated mobile polish not complete

Visual language: dark default, card-based layout, accent highlights (`Card`, `Badge`, `StatCard` components).

---

## Component organization

```text
frontend/src/
├── pages/           # Route-level screens
├── features/        # Domain UI (dashboard, recommendations, settings)
├── components/      # Shared UI (layout, books, settings)
├── lib/             # API, books helpers, insights, user settings
└── contexts/        # AuthProvider, UserSettingsProvider
```

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

---

## Future UI ideas (not implemented)

| Idea | Notes |
|------|-------|
| **Mood filters** | Requires mood data on books |
| **Challenge view** | Reading challenge grouping |
| **Book detail notes** | `user_notes`, `why_added` fields |
| **"Pick for me" mode** | Single random/top pick UX from ranked list |
| **Server-synced settings** | Account-backed preferences |
| **Offline / PWA** | Local cache of library |

Mark these as exploratory in design reviews until backend fields and APIs exist.

---

## Related docs

- [api.md](api.md)
- [recommendation-system.md](recommendation-system.md)
