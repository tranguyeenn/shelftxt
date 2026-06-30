# ShelfTxt project state

**Audit date:** 2026-06-30  
**Purpose:** Map what the codebase actually does today so maintenance, tests, and docs can catch up before new features ship.

ShelfTxt is a full-stack reading-management app centered on **reducing TBR decision fatigue**: track books, understand habits, import/export data, and get explainable recommendations from the reader's own library.

**Production:** [shelftxt.vercel.app](https://shelftxt.vercel.app) · **API:** [shelftxt.onrender.com](https://shelftxt.onrender.com)

---

## Documentation map

Existing docs live under `docs/` (not a flat `docs/*.md` root). Use this table as the index:

| Topic | Canonical doc | Code anchors |
|-------|---------------|--------------|
| Architecture | [engineering/architecture.md](engineering/architecture.md) | `backend/api.py`, `frontend/src/main.tsx` |
| Data model | [engineering/data-model.md](engineering/data-model.md) | `backend/db/models.py` |
| API | [engineering/api.md](engineering/api.md) | `backend/routes/` |
| Frontend | [engineering/frontend.md](engineering/frontend.md) | `frontend/src/` |
| Recommendations | [engineering/recommendation-system.md](engineering/recommendation-system.md) | `backend/ranking/score.py`, `backend/services/recommendation_builder.py` |
| Import / export | [engineering/import-export.md](engineering/import-export.md) | `backend/services/postgres_books.py`, `frontend/src/features/settings/CsvImportSection.tsx` |
| Deployment | [engineering/deployment.md](engineering/deployment.md) | Render + Vercel env vars |
| Decisions (ADRs) | [product/decisions.md](product/decisions.md) | — |
| Prior repo audit | [history/audits/repository-audit.md](history/audits/repository-audit.md) | 2026-05-30 snapshot |

**Missing dedicated docs (create when touching those areas):**

- `auth.md` — Supabase verification flow (`backend/auth/dependencies.py`)
- `metadata-enrichment.md` — Open Library / Google Books / Goodreads fallback (`backend/services/page_lookup.py`)

---

## Feature inventory (verified in code)

### Authentication and profiles

| Piece | Status | Notes |
|-------|--------|-------|
| Supabase Bearer token verification | ✅ | `GET {SUPABASE_URL}/auth/v1/user` in `get_current_user` |
| `GET/PATCH /profile/me` | ✅ | `backend/routes/profile.py` |
| User-scoped book queries | ✅ | All `/books/*` routes pass `current_user.id` |
| Profile fields | ✅ | username, display_name, bio, reading_goal, avatar_url, favorite_genres |
| Avatar / profile UI | ✅ | `ProfilePage.tsx` |

**Risk:** `Book.user_id` is nullable in the schema. New code must always set and filter by `user_id`; never assume orphan rows cannot exist from legacy data.

### Book library

Core CRUD via `backend/routes/books.py` and `postgres_books.py`. Books expose CSV-compatible keys in API responses (`Title`, `ISBN/UID`, etc.) plus snake_case aliases where useful.

**Stored fields (high-signal):**

| Field | Role |
|-------|------|
| `read_status` | `to-read`, `read`, `dnf` (in-progress = `to-read` + progress/pages > 0) |
| `star_rating` | float, typically 0–5; fractional supported |
| `last_date_read` | Legacy finish date; still written on completion |
| `start_date` / `end_date` | Explicit reading window; UI prefers `end_date` for “finished on” |
| `progress_percent` / `pages_read` / `total_pages` | Progress tracking |
| `tracking_mode` | `percentage` or `pages` (inferred from `total_pages` if unset) |
| `description`, `subjects`, `genres`, `cover_url`, … | Metadata enrichment |

**Risk:** Date fields overlap (`last_date_read` vs `end_date`). Finish display uses `end_date` first, then `Last Date Read` (`finishDateValue` in `frontend/src/lib/books.ts`). Completion PATCH sets both when newly completed; re-completion preserves existing dates.

### Reading progress

| Behavior | Implementation |
|----------|----------------|
| UI statuses | `not_started`, `reading`, `completed`, `dnf` — derived, not stored |
| Percentage mode | `progress_percent` can drive completion at 100% |
| Pages mode | `pages_read` / `total_pages`; auto-completes at full pages |
| Finish date preservation | `_apply_status_and_progress`: only sets `last_date_read`/`end_date` on *new* completion |
| Validation | Client (`bookProgress.ts`) + server (`postgres_books.py`) |

**Risk:** Highest regression area. Status, progress, pages, and dates interact in `_apply_status_and_progress`.

### Ratings

| Piece | Status |
|-------|--------|
| Storage | `star_rating` float on `Book` |
| Import aliases | `Star Rating`, `star_rating`, `rating`, `Rating`, `Stars`, `My Rating` |
| Fractional values | Supported (e.g. 4.75 in `ImportRow` schema example) |
| Validation split | Import/PATCH-by-id: 0–5; legacy title PATCH `rating`: 1–5 |
| `parse_rating_value` | Parses numeric strings; does **not** clamp to 0–5 |

**Risk:** Pydantic validates on API boundaries, but unvalidated paths could store out-of-range values. Frontend star components should stay aligned with backend.

### CSV import / export

**Import (UI → `POST /books/import`):** Parses title, author, isbn, status, tracking_mode, ratings, start/end dates, pages, progress, and `Dates Read` ranges. Server normalizes status, dedupes by **title** (case-sensitive) or **isbn_uid**.

**Export (`GET /books/export`):** Writes Title, Authors, ISBN/UID, Read Status, Star Rating, Last Date Read, Start/End Date (duplicated snake_case headers), Progress, Pages, Total Pages, tracking_mode.

**Round-trip gaps (important):**

| Exported on import path | Re-imported on export path |
|-------------------------|----------------------------|
| Full progress + status + ratings + dates | ✅ |
| `ISBN/UID` preserved if present in CSV | ✅ (dedupe by isbn) |
| Genres, subjects, description, cover | ❌ not in export CSV |
| Metadata enrichment timestamps | ❌ |

Re-import is **additive only** (duplicates skipped, not updated).

### Metadata enrichment

| Source | Module |
|--------|--------|
| Open Library | `page_lookup.py` (primary) |
| Google Books | fallback on rate limit / timeout |
| Goodreads-style CSV | `goodreads_metadata.py` |
| Manual overrides | `MANUAL_METADATA_OVERRIDES` in `page_lookup.py` |

Genre cleaning: `metadata_normalization.py` — strips broad subjects, caps genres (`MAX_GENRES_PER_BOOK = 3`), junk patterns, identifier-like subjects.

Background jobs: `MetadataJob` model + routes in `backend/routes/metadata.py`.

**Risk:** External APIs time out (2s lookup timeout). Missing metadata triggers recommendation fallback copy.

### Recommendations

**Entry:** `GET /recommend?style=balanced|popular|discovery` → `get_recommendation` → `build_recommendations`.

**What counts as completed:** `read_status == read` (stored value).

**What counts as “liked” (scoring input):** Finished books with `star_rating >= 4`; if fewer than 3, threshold relaxes to `>= 3.5` (`score_tbr_books`).

**TBR candidates:** `to-read` / `not_started` with **zero** pages and progress (in-progress TBR excluded from ranking).

**Scoring (current — differs from older docs):**

| Signal | Weight (approx.) |
|--------|------------------|
| Genre overlap with liked books | 40% |
| Subject / theme overlap | 25% |
| Same author as liked books | 15% |
| Description keyword overlap | 10% |
| Page-length similarity | 10% |

If no metadata signal clears the 0.35 threshold, **fallback** ranks by author affinity + recency + rating_norm.

**Explanations:** Template strings from matched genres, subjects, authors, and liked books (`recommendation_builder.py`). Honest fallback when metadata missing.

**Related books:** Up to 3 highly rated completed reads with meaningful similarity (genre/subject/author/keywords).

**Doc drift:** [recommendation-system.md](engineering/recommendation-system.md) still describes author-only ranking and says genre is unused. **Update that doc before trusting it.**

### Stats

| Surface | Logic |
|---------|-------|
| Dashboard “At a glance” | TBR count, completed, avg rating (`ReadingStats.tsx`) |
| Reading momentum | Completed this month, pages tracked (`dashboardMetrics.ts`) |
| Insights monthly chart | `computeMonthlyCompletions` — excludes future dates, undated books, wrong year |
| Genre patterns | Uses `Genres` when present; empty state if metadata not generated |

**Risk:** Stats depend on consistent finish dates (`end_date` vs `Last Date Read`).

### Deployment

| Piece | Status |
|-------|--------|
| Backend | Render (`backend.api:app`) |
| Frontend | Vercel |
| Database | PostgreSQL (Supabase-hosted in production) |
| Health | `/health`, `/ready` |
| Demo mode | Read-only middleware for shared demo account |

---

## Test coverage snapshot

**17 test modules** under `tests/` (~200+ test cases in `test_api.py` alone).

| Area | Tests | Gap |
|------|-------|-----|
| API routes | `test_api.py` (broad) | Many paths mocked at service boundary |
| Status normalization | `test_status.py` | Requires pytest |
| TBR scoring | `test_score.py` | Good |
| Recommendation builder | `test_recommendation_builder.py` | Smoke-level; no fixed-seed rank assertions |
| Metadata normalization | `test_metadata_normalization.py` | Good |
| Page lookup / Goodreads | `test_page_lookup.py`, `test_goodreads_metadata.py` | Good |
| Auth dependencies | `test_auth_dependencies.py` | Partial |
| CSV batch pipeline | `test_flexible_pipeline.py` | Separate from live UI import |
| Progress / finish dates | `test_repair_completed_book_progress.py` | Narrow |
| Ratings from CSV | `test_backfill_ratings_from_csv.py` | Script-focused |

**Not covered:** export→clear→import round-trip, fractional rating edge cases end-to-end, recommendation fallback with empty metadata, frontend (no automated UI tests).

**CI:** `.github/workflows/tests.yml` runs Python tests. Local venv may lack `sqlalchemy`/`pytest` unless `pip install -r requirements.txt` (and dev deps) is run.

---

## Database field audit

| Field | Still needed? | Notes |
|-------|---------------|-------|
| `last_date_read` | Yes (legacy + export) | Keep until export/UI fully standardize on `end_date` |
| `start_date` / `end_date` | Yes | Preferred for reading window and stats |
| `progress_percent` | Yes | Percentage tracking mode |
| `pages_read` / `total_pages` | Yes | Pages tracking mode |
| `tracking_mode` | Yes | Drives UI editors |
| `star_rating` | Yes | Recommendations + display |
| `subjects` / `genres` (JSON) | Yes | Recommendations + insights |
| `page_count_checked` / `page_count_source` | Yes | Avoids repeat external lookups |
| `work_key` / `edition_key` | Yes | Open Library identity for re-enrichment |
| `language` | Yes | Language-aware recommendation penalty |
| `cover_url` | Yes | UI covers |
| `description` | Yes | Keyword similarity in recommendations |

**Cleanup candidates (low priority):** duplicate date semantics; duplicate export column names (`Start Date` + `start_date`).

---

## Intentionally out of scope (product guardrails)

Do **not** add without clear product reason:

- OpenSearch / distributed search
- Social / public profiles / community recommendations
- Native mobile app
- Heavy AI / LLM recommendation layer
- Another metadata provider
- New dashboard sections without TBR/decision value

PostgreSQL search / trigram is enough until library scale demands more.

---

## Recommended next actions (ordered)

1. **Freeze major features** until docs match code (especially recommendations + import/export).
2. **Update stale docs:**
   - [recommendation-system.md](engineering/recommendation-system.md) — genre scoring, liked-book threshold, in-progress TBR exclusion
   - [import-export.md](engineering/import-export.md) — full import field list; export round-trip gaps
   - [data-model.md](engineering/data-model.md) — metadata columns, `tracking_mode`, date fields
3. **Add tests before refactors:**
   - Rating validation (0, 4.5, 4.75, 5, invalid)
   - Status transitions + finish date preservation
   - CSV export/import round-trip for core fields
   - Recommendation fallback when `genres` empty (fixed random seed)
   - User scoping (cannot read another user's book)
4. **Export improvement (medium):** include genres/subjects/description in CSV or document that metadata must be re-enriched after import.
5. **Optional doc splits:** `engineering/auth.md`, `engineering/metadata-enrichment.md`.

---

## Product principle

The best version of ShelfTxt is **understandable, stable, and useful** — not the biggest. Every change should help track books, understand habits, choose what to read next, move data in/out, or improve recommendation trust.
