# Troubleshooting

Symptoms → likely cause → fix. See also [deployment.md](../engineering/deployment.md).

---

## Backend (local)

### Protected endpoints return `401` with `Authorization: Bearer ...`

**Cause:** The local backend may be running without the same root `.env`
configuration used by production, or it may point at a different Supabase
project/database than the frontend.

**Fix:** Run uvicorn from the repository root and keep backend env in
`./.env`:

```bash
source .venv/bin/activate
uvicorn backend.api:app --reload
```

Required backend variables:

```env
SUPABASE_URL=https://your-project.supabase.co
SUPABASE_ANON_KEY=your_anon_or_publishable_key
SUPABASE_SERVICE_ROLE_KEY=your_service_role_key
DATABASE_URL=postgresql+psycopg://...
```

`SUPABASE_URL` must match `frontend/.env.local` `VITE_SUPABASE_URL`, and
`DATABASE_URL` must point at the database containing that user's
`public.profiles` row. `SUPABASE_JWT_SECRET` is not required.

Do not rely on `frontend/.env.local` for backend values. The frontend uses
`VITE_SUPABASE_ANON_KEY`; the root backend-loaded `.env` uses
`SUPABASE_ANON_KEY`. The values can be the same, but the names cannot. For
local compatibility only, root `.env` may contain `VITE_SUPABASE_ANON_KEY` and
the backend will alias it to `SUPABASE_ANON_KEY`; the backend does not read
frontend env files.

On local auth failures, backend logs include only safe diagnostics:
authorization header presence, backend Supabase env presence, Supabase
`/auth/v1/user` status, and whether a profile row was found.

### `User profile not found`

**Cause:** The backend received a valid Supabase JWT, but the database configured by `DATABASE_URL` does not contain a `profiles.id` row matching that Supabase auth user id. This usually happens when the frontend uses hosted Supabase Auth and creates `profiles` rows in Supabase Postgres, while the backend still points at local Docker Postgres.

**Fix:** For Supabase Auth integration testing, set backend `DATABASE_URL` to the same Supabase Postgres database where `public.profiles` lives. If you intentionally use local Docker Postgres, manually insert a local profile row with the same UUID as the Supabase auth user.

### `ModuleNotFoundError: No module named 'apscheduler'`

**Cause:** System Python or wrong venv.

**Fix:**

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
.venv/bin/uvicorn backend.api:app --reload
```

In Cursor: **Python: Select Interpreter** → `./.venv/bin/python`.

### `ModuleNotFoundError: No module named 'backend'`

**Cause:** Running uvicorn from wrong directory or wrong module path.

**Fix:** Run from **repo root**:

```bash
uvicorn backend.api:app --reload
```

### Pyright: `DataFrame | Series` not assignable to `save_data`

**Cause:** Pandas stub inference on boolean indexing.

**Fix:** Use `.loc[mask].copy()` instead of `df[mask].copy()`.

---

## Backend (Render)

### Build: `requirements.txt` not found

**Cause:** Render Root Directory set to `backend` or `frontend`.

**Fix:** Settings → Root Directory → **empty** → redeploy.

### Start: `Could not import module "api"`

**Cause:** Start command still `uvicorn api:app` without root shim deployed, or wrong root.

**Fix:** Start command `uvicorn backend.api:app --host 0.0.0.0 --port $PORT`, or deploy root `api.py` shim.

### `/health` OK but library empty after redeploy

**Cause:** Render free tier ephemeral filesystem.

**Fix:** Expected on free tier. Re-import books or attach persistent disk / external storage.

### Cold start / first request timeout

**Cause:** Render spins down idle free services (~15 min).

**Fix:** Wait 30–60s, retry. Keep-warm scheduler in `backend/api.py` reduces but does not eliminate cold starts.

---

## Frontend (local)

### Library won't load / 502 on `/api/books`

**Cause:** Dev defaults to `127.0.0.1:8000`; local API not running.

**Fix (pick one):**

```bash
# Option A — local API
.venv/bin/uvicorn backend.api:app --reload

# Option B — remote API
cp frontend/.env.local.example frontend/.env.local
# API_BASE_URL=https://shelftxt.onrender.com
cd frontend && npm run dev
```

Restart `npm run dev` after env changes.

---

## Frontend (Vercel production)

### `GET shelftxt.vercel.app/api/books` → 404

**Cause:** Expected after ADR-003. Production no longer uses Vercel `/api/*`.

**Fix:** Verify Network tab shows `GET shelftxt.onrender.com/books` → 200. Redeploy frontend with latest `apiUrl.ts` code.

### CORS error in browser console

**Cause:** Backend missing Vercel origin in `allow_origins`.

**Fix:** Confirm `https://shelftxt.vercel.app` in `backend/api.py`, redeploy Render.

### Stale API URL after rename

**Cause:** Old build or missing `NEXT_PUBLIC_API_BASE_URL`.

**Fix:** Vercel → Environment Variables → set `NEXT_PUBLIC_API_BASE_URL=https://shelftxt.onrender.com` → redeploy.

### Root Directory wrong

**Cause:** Vercel building repo root instead of `frontend/`.

**Fix:** Settings → Root Directory → `frontend` → redeploy.

---

## Git

### Push rejected: remote contains work

**Fix:**

```bash
git pull --rebase origin main
git push origin main
```

Update remote after repo rename:

```bash
git remote set-url origin https://github.com/tranguyeenn/shelftxt.git
```

---

## Tests

### `AttributeError` or wrong status in API tests

**Cause:** Tests patch the wrong layer after the routes/services split.

**Fix:** Use `TestClient(backend.api.app)` and patch where names are **used**:

| Endpoint | Patch |
|----------|--------|
| Add / patch / import | `backend.services.postgres_books` or `backend.repository.postgres_books_repository` |
| Delete / remove | `backend.services.postgres_books` or `backend.repository.postgres_books_repository` |
| Recommend | `backend.routes.recommendation.get_recommendation` |

---

## Performance Verification

Manual checklist after changing clear/import/library/recommendation behavior:

1. Start the backend.
2. Login as a test user.
3. Load Library and confirm there are no Open Library or Google Books logs.
4. Run `SELECT count(*) FROM books WHERE user_id = '<test_user_id>';`.
5. Click Clear library.
6. Confirm the response is fast.
7. Verify the books count for that user becomes `0`.
8. If a search index exists, verify it has no visible records for deleted books.
9. Import a CSV.
10. Confirm the import response is fast.
11. Confirm there are no external API logs during import.
12. Load Library again and confirm it is fast.
13. Open Settings and click Generate Metadata.
14. Confirm the UI returns control immediately and Metadata Progress updates.
15. Confirm Open Library or Google Books logs only appear after the explicit metadata action.

---

## Still stuck?

Gather:

1. URL in browser address bar
2. One failing Network request (URL + status)
3. Render/Vercel Root Directory settings
4. Last 20 lines of deploy log

Open an issue or fix docs in `docs/` for the next person.
