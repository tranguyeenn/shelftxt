# PostgreSQL Migration Audit

**Phase 0** — inventory only. No application code, PostgreSQL, SQLAlchemy, or API behavior changes.

**Audit date:** 2026-06-06  
**Live storage path:** `backend/data/processed/books.csv` (gitignored)  
**Column definition:** `BOOKS_COLUMNS` in `backend/book_data.py`

---

## CSV Read Operations

Operations that read from the **live library** (`books.csv`) or call `load_data()` / `get_all_books()`.

| File | Function | Purpose |
|------|----------|---------|
| `backend/book_data.py` | `load_data()` | Primary read: `pd.read_csv(PROCESSED_PATH)`, column repair, `Read Status` normalization, datetime coercion |
| `backend/book_data.py` | `ensure_books_file()` | Checks file existence before read; may create empty CSV first |
| `backend/repository/books_repository.py` | `get_all_books()` | Facade → `load_data()` |
| `backend/repository/books_repository.py` | `book_exists(title)` | Loads full library to check title membership (**unused elsewhere in repo**) |
| `backend/routes/books.py` | `get_books()` | **Bypasses repository** — calls `load_data()` directly, paginates in memory |
| `backend/services/books.py` | `add_book_service` | `get_all_books()` before append |
| `backend/services/books.py` | `export_library_csv` | `get_all_books()` before serialization |
| `backend/services/books.py` | `clear_library_service` | `get_all_books()` to count rows before clear |
| `backend/services/books.py` | `delete_book_by_id` | `get_all_books()` before row removal |
| `backend/services/books.py` | `delete_book_by_title` | `get_all_books()` before row removal |
| `backend/services/books.py` | `patch_book_service` | `get_all_books()` before in-place updates |
| `backend/services/books.py` | `update_book_progress_by_id` | `get_all_books()` before progress update |
| `backend/services/books.py` | `import_books_service` | `get_all_books()` before bulk append |
| `backend/services/recommendation.py` | `get_recommendation()` | **Bypasses repository** — calls `load_data()` directly for ranking input |
| `cli/manage_books.py` | `mark_finished`, `mark_dnf`, `add_to_tbr` | Each calls `load_data()` before mutation |

### Batch / offline reads (not `books.csv`)

These read **arbitrary user-uploaded CSV files** via the ingest pipeline. They do not touch live storage unless an operator manually merges output.

| File | Function | Purpose |
|------|----------|---------|
| `backend/ingest/load_csv.py` | `load_csv()` | `pd.read_csv(csv)` + column mapping to canonical schema |
| `backend/ingest/pipeline.py` | `validate_uploaded_csv()` | `pd.read_csv(path, nrows=100)` preview for validation gate |

---

## CSV Write Operations

Operations that write to the **live library** or serialize library data to CSV format.

| File | Function | Purpose |
|------|----------|---------|
| `backend/book_data.py` | `ensure_books_file()` | Creates headers-only `books.csv` via `pd.DataFrame(columns=BOOKS_COLUMNS).to_csv()` |
| `backend/book_data.py` | `save_data(df)` | **Primary write:** `df.to_csv(PROCESSED_PATH, index=False)` — full-file overwrite |
| `backend/repository/books_repository.py` | `save_books(df)` | Facade → `save_data()` |
| `backend/services/books.py` | `add_book_service` | `save_books(df)` after `pd.concat` append |
| `backend/services/books.py` | `clear_library_service` | `save_books(empty DataFrame)` — wipes all rows |
| `backend/services/books.py` | `delete_book_by_id` | `save_books(df)` after `df.loc[~row]` |
| `backend/services/books.py` | `delete_book_by_title` | `save_books(df)` after title filter |
| `backend/services/books.py` | `patch_book_service` | `save_books(df)` after legacy shelf PATCH |
| `backend/services/books.py` | `update_book_progress_by_id` | `save_books(df)` after progress fields updated |
| `backend/services/books.py` | `import_books_service` | `save_books(df)` when `imported > 0` |
| `backend/services/books.py` | `export_library_csv` | `df.to_csv(index=False)` — **in-memory** CSV string for `GET /books/export` (no file write) |
| `cli/manage_books.py` | `mark_finished`, `mark_dnf`, `add_to_tbr` | Each calls `save_data(df)` after mutation |

### Write pattern summary

Every mutation follows **read entire file → modify DataFrame → write entire file**. There is no row-level I/O, locking, or transactional safety.

---

## Pandas / DataFrame Dependencies

### Live application path (migration impact: **high**)

| File | Dependency usage | Migration impact |
|------|------------------|------------------|
| `backend/book_data.py` | `pd.read_csv`, `pd.to_csv`, `pd.DataFrame`, `pd.to_datetime`, `np.nan` | **Replace entirely** — this is the persistence boundary |
| `backend/repository/books_repository.py` | Returns/saves `pd.DataFrame` | **Refactor interface** — should return domain objects or query results, not DataFrames |
| `backend/routes/books.py` | `load_data()`, `df.iloc`, `df.to_dict`, `np.nan` → JSON | **High** — needs DB-level pagination; remove direct `load_data()` |
| `backend/services/books.py` | Full DataFrame CRUD: `pd.concat`, `df.loc`, `pd.isna`, `pd.Timestamp`, `df.to_csv` | **High** — all shelf logic is row-slice mutations on in-memory frames |
| `backend/services/book_api.py` | `pd.DataFrame`, `pd.Series` typing; `series_to_api_book(row)` | **Medium** — map from ORM/dict instead of Series |
| `backend/services/recommendation.py` | `load_data()` → passes DataFrame to builder | **Medium** — swap load path; may keep in-memory scoring |
| `backend/services/recommendation_builder.py` | `pd.DataFrame` filtering, `pd.concat`, `iterrows`, `sort_values` | **Low–medium** — can accept DataFrame built from DB rows or refactor to list[dict] |
| `backend/preprocess/normalize.py` | `pd.to_numeric`, `pd.Timestamp`, `pd.Series`, column mutation | **Low** — in-memory only; can run on DataFrame built from query results |
| `backend/ranking/score.py` | DataFrame API (`df.columns`, `groupby`, `merge`, `sort_values`); `numpy` for noise | **Low** — duck-typed on DataFrame; no pandas import; works if query results are loaded into a frame |
| `cli/manage_books.py` | `load_data` / `save_data`, `pd.concat`, `pd.Timestamp` | **High** — must use new repository or service layer |

### Batch ingest path (migration impact: **low** for Phase 1)

| File | Dependency usage | Migration impact |
|------|------------------|------------------|
| `backend/ingest/load_csv.py` | `pd.read_csv`, `pd.DataFrame`, type coercion | **Defer** — offline tool; independent of live DB |
| `backend/ingest/pipeline.py` | `pd.read_csv` preview, empty DataFrame returns | **Defer** |
| `backend/preprocess/clean_books.py` | `pd.to_numeric`, `pd.to_datetime`, `pd.Timestamp` | **Defer** — batch canonical schema only |

### Tests (migration impact: **high** — must update mocks and fixtures)

| File | Dependency usage | Migration impact |
|------|------------------|------------------|
| `tests/test_api.py` | `pd.DataFrame` fixtures; mocks `load_data`, `get_all_books`, `save_books` | Rewrite mocks for repository/DB layer |
| `tests/test_recommendation_builder.py` | `pd.DataFrame` fixture library | May keep if builder still accepts DataFrames |
| `tests/test_score.py` | `pd.DataFrame` scoring fixtures | Low — ranking unit tests |
| `tests/test_flexible_pipeline.py` | stdlib `csv` module only for temp files | Unaffected by live DB migration |

### Frontend (migration impact: **low–medium**)

| File | Dependency usage | Migration impact |
|------|------------------|------------------|
| `frontend/src/lib/books.ts` | `BookRecord` uses **CSV column names** (`Title`, `ISBN/UID`, etc.) for `GET /books` | Stable if API keeps CSV-shaped list response; otherwise update mapping |
| `frontend/src/lib/types.ts` | `ApiBook` normalized shape from progress endpoint | Stable if `PATCH /books/{id}/progress` response unchanged |
| `frontend/src/features/settings/CsvImportSection.tsx` | Client-side CSV parse → JSON import | Unaffected — posts to `/books/import`, not file I/O |

### Numpy usage (secondary)

Used alongside pandas for `np.nan`, `np.isnan`, `np.random.uniform` in `book_data.py`, `books.py`, `routes/books.py`, `book_api.py`, `ranking/score.py`, and tests. Migration may reduce numpy reliance if null handling moves to SQL/ORM.

---

## Existing Book Fields

### App CSV / database columns (`BOOKS_COLUMNS`)

Source of truth: `backend/book_data.py`.

| Field name | Type (logical) | Required | Notes |
|------------|----------------|----------|-------|
| `Title` | string | **Required** on add/import | Legacy PATCH/DELETE key; import dedupe key (case-sensitive) |
| `Authors` | string | **Required** on add (defaults `"Unknown"` on import) | Used in author-preference scoring |
| `ISBN/UID` | string | **Auto-generated** | Stable id for UI routes, progress, delete-by-id |
| `Read Status` | enum string | **Auto** on add (`to-read`) | Values: `to-read`, `read`, `dnf` (lowercased on load) |
| `Star Rating` | float 1–5 or null | Optional (required when marking `read` via legacy PATCH) | Nullable |
| `Last Date Read` | datetime or null | Optional | Parsed with `errors="coerce"` on load |
| `Progress (%)` | float 0–100 | Derived | From pages / total while in progress |
| `Pages Read` | int | Derived | Current page count |
| `Total Pages` | int or null | Optional | Required before tracking reading progress |

### Derived fields (not stored)

Computed at recommendation time in `backend/preprocess/normalize.py` and `backend/ranking/score.py`:

| Field | Type | Source |
|-------|------|--------|
| `rating_norm` | float [0, 1] | `Star Rating` |
| `recency_norm` | float [0, 1] | `Last Date Read` |
| `days_since_read` | int | `Last Date Read` |
| `author_score` | float | Mean `rating_norm` per author from read rows |
| `score` | float [0, 1] | TBR rank (author preference + noise) |

### API request schemas (`backend/schemas/books.py`)

| Schema | Fields | Maps to storage |
|--------|--------|-----------------|
| `AddBook` | `title`, `author`, `total_pages?` | New TBR row |
| `PatchBook` | `title`, `new_title?`, `author?`, `total_pages?`, `pages_read?`, `move_to?`, `rating?`, `date_read?` | Legacy title-keyed update |
| `ImportRow` | `title`, `author?`, `total_pages?` | Bulk import row |
| `BookProgressPatch` | `status` (`not_started` \| `reading` \| `completed`), `pages_read` | Id-keyed progress update |
| `ClearLibraryRequest` | `confirm: bool` | Wipes all rows |

### API response contracts

| Endpoint | Response shape | Storage coupling |
|----------|----------------|------------------|
| `GET /books` | `{ page, limit, total, results[] }` — each result uses **raw CSV column names** | Reads full library; paginates in memory |
| `PATCH /books/{id}/progress` | `{ book: ApiBook }` — normalized fields (`id`, `title`, `status`, …) | Read + write full CSV |
| `GET /books/export` | `text/csv` with `BOOKS_COLUMNS` headers | Read full library |
| `GET /recommend` | `[{ book, score, explanation, similar_books }]` | Read full library |
| Mutations (`POST`, `PATCH`, `DELETE`) | `{ message }` or import counts | Read + write full CSV |

### Frontend types (`frontend/src/lib/types.ts`, `books.ts`)

- **`BookRecord`** — mirrors CSV columns from `GET /books` results
- **`ApiBook`** — normalized book from progress response and client-side `recordToApiBook()`
- **`ReadingStatus`** — `not_started` \| `reading` \| `completed` (derived, not stored)

### Batch canonical schema (not in live storage)

Separate lowercase fields in `backend/ingest/` (`title`, `author`, `genre`, `book_id`, `read_status`, `rating`, `last_date_read`). Not part of PostgreSQL Phase 1 unless ingest is merged into live storage.

### Planned fields (documented, not implemented)

From `docs/engineering/data-model.md`: `mood_tags`, `why_added`, `source`, `challenge_prompt`, `user_notes`, `dnf_reason`.

---

## Affected API Endpoints

All book-related endpoints depend on CSV storage today. Health check is unaffected.

| Method | Path | Storage interaction | Service / route |
|--------|------|---------------------|-----------------|
| `GET` | `/books` | **Read** full CSV; paginate in route | `routes/books.py` → `load_data()` |
| `GET` | `/books/export` | **Read** full CSV; serialize to CSV | `export_library_csv()` |
| `POST` | `/books/clear` | **Read** + **write** (empty file) | `clear_library_service()` |
| `POST` | `/books` | **Read** + **write** (append row) | `add_book_service()` |
| `DELETE` | `/books?title=` | **Read** + **write** (remove by title) | `delete_book_by_title()` |
| `PATCH` | `/books` | **Read** + **write** (legacy title-keyed patch) | `patch_book_service()` |
| `POST` | `/books/import` | **Read** + **write** (bulk append) | `import_books_service()` |
| `PATCH` | `/books/{book_id}/progress` | **Read** + **write** (id-keyed update) | `update_book_progress_by_id()` |
| `DELETE` | `/books/{book_id}` | **Read** + **write** (remove by id) | `delete_book_by_id()` |
| `GET` | `/recommend?style=` | **Read** full CSV (cached) | `get_recommendation()` → `load_data()` |

### Not affected

| Method | Path | Notes |
|--------|------|-------|
| `GET`, `HEAD` | `/health` | No storage dependency |

### Side effects on write

All mutations in `backend/services/books.py` call `invalidate_recommendation_cache()` which clears the `@lru_cache` on `get_recommendation()`. A DB migration must preserve this invalidation semantics (or replace with query-level freshness).

---

## Migration Notes

### Risks

| Risk | Detail |
|------|--------|
| **Full-file read/write** | Every request loads or saves the entire library — hidden O(n) cost; Postgres must enable true row-level ops and paging |
| **Repository bypass** | `routes/books.py` and `services/recommendation.py` call `load_data()` directly, skipping `books_repository.py` — inconsistent swap point |
| **DataFrame-centric services** | `services/books.py` uses pandas row indexing (`df.loc`, title in `df["Title"].values`) — business logic is tightly coupled to in-memory table mutations |
| **Dual identity keys** | `Title` (legacy PATCH/DELETE, import dedupe) and `ISBN/UID` (UI primary) — schema and migration script must preserve both during transition |
| **No concurrency control** | CSV last-write-wins; Postgres needs transaction boundaries on multi-step shelf updates |
| **Recommendation cache** | In-process `@lru_cache` keyed by style — multi-instance deploy would need shared cache invalidation |
| **Export format** | `GET /books/export` returns pandas-generated CSV with `BOOKS_COLUMNS` order — export must remain compatible for user backups |
| **NaN / null semantics** | `np.nan` coerced to `null` in JSON; DB null handling must match API contract |
| **Ephemeral Render disk** | Current production data loss on redeploy — migration urgency is operational, not just architectural |

### Assumptions

| Assumption | Basis |
|------------|-------|
| Single-user, single-library | No auth; one `books.csv` per deployment |
| Repository facade is the intended swap layer | ADR-001, `docs/engineering/scalability.md` |
| API response shapes remain stable in Phase 1 | Frontend `BookRecord` / `ApiBook` depend on current contracts |
| Ranking can stay pandas-in-memory initially | Load all books into DataFrame from DB rows for `GET /recommend` is acceptable at small scale |
| Batch ingest pipeline stays separate | `backend/ingest/` does not auto-merge into live storage |
| `book_exists()` / `get_book_row()` are dead code today | Defined in repository but unused — safe to redesign |

### Areas requiring repository refactoring

| Area | Current state | Target state |
|------|---------------|--------------|
| **Persistence boundary** | `book_data.py` returns DataFrames | Repository returns models / dicts / query results |
| **`get_all_books()` / `save_books(df)`** | Load/save entire library | Granular: `list_books(page, limit)`, `get_by_id`, `insert`, `update`, `delete`, `count` |
| **`GET /books` route** | Direct `load_data()` + `iloc` slice | Repository pagination with SQL `LIMIT`/`OFFSET` or cursor |
| **`services/books.py`** | DataFrame mutations | Service methods call repository CRUD; no pandas in persistence path |
| **`services/recommendation.py`** | Direct `load_data()` | `get_all_books()` or dedicated `load_library_for_ranking()` via repository |
| **Progress / patch logic** | `df.loc[row, col]` updates | `UPDATE` by `ISBN/UID` with field-level validation |
| **Import** | In-memory dedupe by `Title` | `INSERT ... ON CONFLICT` or existence check query |
| **Clear library** | Replace with empty DataFrame | `DELETE FROM books` (or truncate) |
| **CLI** | Direct `load_data` / `save_data` | Route through services or repository |
| **Tests** | Mock DataFrame returns | Mock repository or use test DB fixtures |
| **ID generation** | `str(pd.Timestamp.now().timestamp())` | DB sequence, UUID, or preserved string id column |
| **Date parsing** | `pd.to_datetime` on load | DB `TIMESTAMP` column + driver deserialization |

### Suggested migration phases (reference only)

1. **Phase 0** (this document) — inventory dependencies
2. **Phase 1** — define SQL schema mirroring `BOOKS_COLUMNS`; implement repository with Postgres behind existing DataFrame interface (adapter pattern)
3. **Phase 2** — refactor services off DataFrame mutations; DB-level pagination for `GET /books`
4. **Phase 3** — data migration script CSV → Postgres; dual-write or cutover
5. **Phase 4** — remove `book_data.py` CSV path; optional pandas removal from persistence layer

---

## Files Requiring Changes During Migration

### Must change (live storage path)

| File | Reason |
|------|--------|
| `backend/book_data.py` | Core CSV I/O — replaced or deleted |
| `backend/repository/books_repository.py` | Persistence interface — new Postgres implementation |
| `backend/routes/books.py` | Direct `load_data()` bypass; in-memory pagination |
| `backend/services/books.py` | All CRUD is DataFrame read-modify-write |
| `backend/services/recommendation.py` | Direct `load_data()` bypass |
| `backend/services/book_api.py` | Maps `pd.Series` → API dict |
| `cli/manage_books.py` | Direct CSV access |

### Likely change (in-memory scoring — may keep pandas temporarily)

| File | Reason |
|------|--------|
| `backend/services/recommendation_builder.py` | Accepts DataFrame; may load from DB-built frame |
| `backend/preprocess/normalize.py` | DataFrame column ops |
| `backend/ranking/score.py` | DataFrame API (no pandas import today) |

### Test files

| File | Reason |
|------|--------|
| `tests/test_api.py` | Mocks `load_data`, `get_all_books`, `save_books` throughout |
| `tests/test_recommendation_builder.py` | DataFrame fixtures |
| `tests/test_score.py` | DataFrame fixtures (low priority) |

### Frontend (if API contracts change)

| File | Reason |
|------|--------|
| `frontend/src/lib/books.ts` | `BookRecord` CSV column names on `GET /books` |
| `frontend/src/lib/types.ts` | `ApiBook` shape |

### Defer (batch pipeline — independent of live DB)

| File | Reason |
|------|--------|
| `backend/ingest/load_csv.py` | Reads arbitrary upload CSVs |
| `backend/ingest/pipeline.py` | Offline validation/ranking |
| `backend/preprocess/clean_books.py` | Canonical schema cleaning |
| `tests/test_flexible_pipeline.py` | Batch pipeline tests |

### New files expected

| File | Purpose |
|------|---------|
| `backend/db/` or similar | Connection config, session management |
| `backend/models/book.py` or equivalent | ORM / row model mirroring `BOOKS_COLUMNS` |
| `backend/repository/postgres_books_repository.py` | Postgres implementation |
| Migration script(s) | CSV → Postgres data import |
| `tests/test_repository.py` (or integration tests) | DB-backed persistence tests |

### Documentation to update (post-implementation)

| File | Reason |
|------|--------|
| `docs/engineering/architecture.md` | Persistence diagram |
| `docs/engineering/data-model.md` | Storage path and field semantics |
| `docs/engineering/scalability.md` | CSV limitations section |
| `docs/engineering/deployment.md` | Postgres env vars, connection strings |
| `docs/product/decisions.md` | New ADR for Postgres migration |
| `CONTRIBUTING.md`, `README.md` | Setup instructions |

---

## Related

- [data-model.md](data-model.md) — field semantics and validation
- [scalability.md](scalability.md) — CSV limitations and migration path overview
- [architecture.md](architecture.md) — layer boundaries and repository role
- [decisions.md](../product/decisions.md) — ADR-001 (CSV as source of truth)
