# Deployment

Production split: **API on Render**, **UI on Vercel**, **Auth on Supabase**. All application code deploys from the same GitHub repo (`tranguyeenn/shelftxt`).

| Service | URL | Platform |
|---------|-----|----------|
| Backend | https://shelftxt.onrender.com | Render (Python) |
| Frontend | https://shelftxt.vercel.app | Vercel (Vite SPA) |
| Auth | Supabase project URL | Supabase Auth |
| API docs | https://shelftxt.onrender.com/docs | Swagger (Render) |

---

## Backend — Render

### Service settings

| Setting | Value |
|---------|--------|
| **Root Directory** | *(empty — repo root)* |
| **Runtime** | Python 3.14 |
| **Build Command** | `pip install -r requirements.txt` |
| **Start Command** | `uvicorn backend.api:app --host 0.0.0.0 --port $PORT` |

Alternative: leave Start Command empty and use root [`Procfile`](../../Procfile).

Legacy start command `uvicorn api:app` works via root [`api.py`](../../backend/api.py) shim (re-exports `backend.api`).

Production entrypoint is always **`backend.api:app`** — not `backend.api_draft`.

Optional Blueprint: [`render.yaml`](../../render.yaml).

### Common Render mistakes

| Symptom | Cause | Fix |
|---------|-------|-----|
| `requirements.txt` not found | Root Directory = `backend` or `frontend` | Clear Root Directory |
| `Could not import module "api"` | Old start command after `backend/` move | Use `backend.api:app` or deploy shim |
| `Supabase environment variables are not configured` | Missing backend auth env | Set `SUPABASE_URL` and `SUPABASE_SERVICE_ROLE_KEY` on Render |
| 401 on protected routes | Missing/expired frontend Bearer token or missing profile | Log in again and verify profile creation |

### Health check

Render should use `/health`. Keep-warm job in `backend/api.py` pings the same path every 14 minutes.

---

## Frontend — Vercel

### Project settings

| Setting | Value |
|---------|--------|
| **Root Directory** | `frontend` |
| **Framework Preset** | **Vite** (not Next.js) |
| **Build Command** | `npm run build` (or leave default — set in `frontend/vercel.json`) |
| **Output Directory** | `dist` |

If deploy fails with “No Next.js version detected”, the project is still on the old Next preset. In Vercel → Project → Settings → General → Framework Preset, choose **Vite**, then redeploy.

### Environment variables

| Key | Environments | Value |
|-----|--------------|-------|
| `VITE_API_BASE_URL` | Production | `https://shelftxt.onrender.com` |
| `VITE_SUPABASE_URL` | Production | Supabase project URL |
| `VITE_SUPABASE_ANON_KEY` | Production | Supabase anon/publishable key |

Remove legacy `NEXT_PUBLIC_API_BASE_URL` if still set.

Only public Supabase browser credentials belong in Vercel. Never set `SUPABASE_SERVICE_ROLE_KEY` in frontend/Vercel env.

See [`frontend/.env.local.example`](../../frontend/.env.local.example).

### Post-deploy verification

1. https://shelftxt.onrender.com/health → `{"status":"healthy",...}`
2. https://shelftxt.vercel.app/ → unauthenticated users see login/register, authenticated users see the app
3. Browser DevTools → Network → protected API requests include `Authorization: Bearer ...`
4. Browser DevTools → Network → requests go to **`shelftxt.onrender.com`**, not `vercel.app/api/*`

### CORS

Backend must list the Vercel origin in `backend/api.py` `allow_origins`. Redeploy Render after CORS changes.

---

## Deploy order

When both code and config change:

1. **Push to `main`**
2. **Render** redeploys (backend + CORS)
3. **Vercel** redeploys (frontend)
4. Hard-refresh browser (Cmd+Shift+R)

First request after idle may wait 30–60s (Render cold start).

---

## Environment variable reference

| Variable | Where set | Consumed by | Purpose |
|----------|-----------|-------------|---------|
| `PORT` | Render (injected) | uvicorn | Listen port |
| `DATABASE_URL` | Render / `.env` | SQLAlchemy | PostgreSQL connection string for profiles and book CRUD |
| `SUPABASE_URL` | Render / `.env` | `backend/auth/dependencies.py` | Supabase project URL for backend token verification |
| `SUPABASE_SERVICE_ROLE_KEY` | Render / `.env` | `backend/auth/dependencies.py` | Server-only Supabase key for validating users |
| `VITE_SUPABASE_URL` | Vercel / `.env.local` | `frontend/src/lib/supabase.ts` | Supabase project URL for browser auth |
| `VITE_SUPABASE_ANON_KEY` | Vercel / `.env.local` | `frontend/src/lib/supabase.ts` | Public anon/publishable key for browser auth |
| `VITE_API_BASE_URL` | Vercel / `.env.local` | `frontend/src/lib/api.ts` | Production or custom API base URL |

---

## Persistence (production)

Profiles and user-owned book CRUD data live in PostgreSQL through SQLAlchemy. Supabase Auth owns identity and session issuance. CSV import/export compatibility still exists, but CRUD routes do not rely on Render's filesystem as the source of truth.

---

## Related

- [troubleshooting.md](../contributors/troubleshooting.md)
- [architecture.md](architecture.md)
- [development.md](../contributors/development.md) — local setup
