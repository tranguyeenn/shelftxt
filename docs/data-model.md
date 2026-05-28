# Data model

## App persistence (`books.csv`)

**Path:** `backend/data/processed/books.csv`  
**Manager:** `backend/book_data.py` (via `backend/repository/books_repository.py` in refactored code paths)  
**Created:** Empty file with headers on first `load_data()` or `save_data()` call.

### Columns

| Column | Type (logical) | Notes |
|--------|----------------|-------|
| `Title` | string | Primary key for API updates/deletes |
| `Authors` | string | Display / author-preference scoring |
| `ISBN/UID` | string | Auto-generated timestamp id if missing |
| `Read Status` | enum string | `to-read`, `read`, `dnf` — lowercased on load |
| `Star Rating` | float 1–5 | Set when marking read; DNF forces rating `1` in PATCH |
| `Last Date Read` | datetime | Set on read or DNF; parsed with `errors="coerce"` |
| `Progress (%)` | float 0–100 | Derived from pages when moving to “reading” |
| `Pages Read` | int | Current page while in progress |
| `Total Pages` | int \| null | Required before `move_to: "reading"` |

### Read status semantics

| Value | Meaning |
|-------|---------|
| `to-read` | On TBR shelf, or in progress if `Progress (%)` > 0 |
| `read` | Finished |
| `dnf` | Did not finish; progress reset to 0 |

### UI shelf derivation

The frontend does not store shelf separately; it derives from API fields:

| UI shelf | Rule |
|----------|------|
| Want to read | `Read Status` = `to-read` AND `Progress (%)` = 0 |
| Currently reading | `Read Status` = `to-read` AND `Progress (%)` > 0 |
| Read | `Read Status` = `read` |
| DNF | `Read Status` = `dnf` |

Implementation: `shelfLabel()` in `frontend/app/page.tsx`.

### PATCH shelf transitions (`move_to`)

| `move_to` | API effect |
|-----------|------------|
| `want` | `to-read`, progress 0, pages 0 |
| `reading` | `to-read`, requires `Total Pages`; sets `Pages Read` and `Progress (%)` |
| `read` | `read`, rating 1–5, progress 100, optional finish date |
| `dnf` | `dnf`, rating 1, progress 0, optional date |

### Update pages while reading

`PATCH /books/progress` with `{ "title", "pages_read" }` — only when the book is already in progress (see UI shelf “Currently reading”). Clamps pages to `1` … `Total Pages` and recomputes `Progress (%)`.

## Canonical schema (batch pipeline)

Used by `backend/ingest/load_csv.py` and downstream preprocess/rank steps.

| Field | Required | Default |
|-------|----------|---------|
| `book_id` | no | generated random id if empty |
| `title` | yes | — |
| `author` | no | `"unknown"` |
| `genre` | no | `"unknown"` |
| `read_status` | yes | `"to-read"` if blank |
| `rating` | no | mean of column, else `3.0` |
| `last_date_read` | no | today if missing after clean |

### Allowed `read_status` values

`read`, `to-read`, `dnf`

Other values trigger a **warning** in validation, not a hard reject.

## Mapping between schemas

Default mapping in `backend/ingest/load_csv.py` bridges ShelfTxt’s own export format to canonical:

| App / export column | Canonical field |
|---------------------|-----------------|
| `ISBN/UID` | `book_id` |
| `Title` | `title` |
| `Authors` | `author` |
| `Genre` | `genre` |
| `Read Status` | `read_status` |
| `Star Rating` | `rating` |
| `Last Date Read` | `last_date_read` |

User uploads supply custom `column_mappings` (see [pipeline.md](pipeline.md)).

## Derived features (not stored in CSV)

Computed at ranking time in `backend/preprocess/normalize.py`:

| Field | Description |
|-------|-------------|
| `rating_norm` | Min–max normalized rating in [0, 1] |
| `recency_norm` | Min–max normalized days since read (recent = higher) |
| `days_since_read` | Integer days from `Last Date Read` to today |
| `score` | Combined or TBR score (see [ranking.md](ranking.md)) |
