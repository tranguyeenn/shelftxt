# Deployment

Production split: **API on Render**, **UI on Vercel**. Both deploy from the same GitHub repo (`tranguyeenn/shelftxt`).

| Service | URL | Platform |
|---------|-----|----------|
| Backend | https://shelftxt.onrender.com | Render (Python) |
| Frontend | https://shelftxt.vercel.app | Vercel (Vite SPA) |
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

Alternative: leave Start Command empty and use root [`Procfile`](../Procfile).

Legacy start command `uvicorn api:app` works via root [`api.py`](../api.py) shim (re-exports `backend.api`).

Production entrypoint is always **`backend.api:app`** — not `backend.api_draft`.

Optional Blueprint: [`render.yaml`](../render.yaml).

### Common Render mistakes

| Symptom | Cause | Fix |
|---------|-------|-----|
| `requirements.txt` not found | Root Directory = `backend` or `frontend` | Clear Root Directory |
| `Could not import module "api"` | Old start command after `backend/` move | Use `backend.api:app` or deploy shim |
| Empty library after redeploy | Ephemeral disk on free tier | Expected — plan persistent disk or external DB later |

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

Remove legacy `NEXT_PUBLIC_API_BASE_URL` if still set.

See [`frontend/.env.local.example`](../frontend/.env.local.example).

### Post-deploy verification

1. https://shelftxt.onrender.com/health → `{"status":"healthy",...}`
2. https://shelftxt.vercel.app/ → library loads (empty `[]` is OK)
3. Browser DevTools → Network → requests go to **`shelftxt.onrender.com`**, not `vercel.app/api/*`

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
| `NEXT_PUBLIC_API_BASE_URL` | Vercel | `frontend/lib/apiUrl.ts` | Production browser → API |
| `API_BASE_URL` | Vercel / `.env.local` | `frontend/lib/backendUrl.ts` | Next.js server proxy (dev) |
| `NODE_ENV` | Build/runtime | Next.js | Dev vs production defaults |

---

## Persistence (production)

`backend/data/processed/books.csv` lives on Render's filesystem. Free-tier instances may **lose data** on redeploy or long spin-down. Document this for users; plan Postgres/S3 when the product outgrows CSV.

---

## Related

- [troubleshooting.md](troubleshooting.md)
- [architecture.md](architecture.md)
- [development.md](development.md) — local setup
