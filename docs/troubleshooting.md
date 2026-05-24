# Troubleshooting

Symptoms → likely cause → fix. See also [deployment.md](deployment.md).

---

## Backend (local)

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

### `AttributeError: module 'api' has no attribute 'normalize_rating'`

**Cause:** Tests patch old import paths after service extraction.

**Fix:** Patch where the name is bound, e.g. `backend.api.get_recommendation` or `backend.services.recommendation.load_data`.

---

## Still stuck?

Gather:

1. URL in browser address bar
2. One failing Network request (URL + status)
3. Render/Vercel Root Directory settings
4. Last 20 lines of deploy log

Open an issue or fix docs in `docs/` for the next person.
