# Ranking

Scoring implementation: `backend/ranking/score.py`  
Normalization: `backend/preprocess/normalize.py`  
HTTP orchestration: `backend/services/recommendation_builder.py`

Conceptual overview: [system-design/recommendation-system.md](system-design/recommendation-system.md).

---

## Feature normalization

### `normalize_rating(df)`

Column: `Star Rating` or `rating`.

- Coerce numeric; fill NaN with column mean (or 0.5 if all missing)
- Min–max → `rating_norm` in [0, 1]

### `compute_recency(df)`

Column: `Last Date Read` or `last_date_read`.

- `days_since_read` = days from finish date to today
- `recency_norm` = min–max reversed (more recent → higher)
- Default 0.5 when no dates

---

## Read books: `score_read_books`

Filter: `Read Status` == `read`

```text
score = 0.7 × rating_norm + 0.3 × recency_norm
```

Used in batch pipeline output. **Not** the primary HTTP recommendation path today.

---

## TBR books: `score_tbr_books`

Filter: `Read Status` == `to-read`

1. Dedupe `(title, author)` on TBR rows
2. Mean `rating_norm` per author from **read** rows → `author_score`
3. Left join onto TBR; fill unknown authors with global read average (or 0.5)
4. Add uniform noise ± `randomness_strength` (default 0.05)
5. Clip to [0, 1], sort descending
6. Optional: one book per author (`diverse_authors`)

| Parameter | Default | Effect |
|-----------|---------|--------|
| `randomness_strength` | 0.05 | Score jitter |
| `diverse_authors` | True in discovery style | Author diversity |

---

## Recommendation styles

Applied in `recommendation_builder._rank_tbr_for_style`:

| Style | `randomness_strength` | `diverse_authors` |
|-------|----------------------|-------------------|
| `balanced` | 0.05 | false |
| `popular` | 0.0 | false |
| `discovery` | 0.12 | true |

Query: `GET /recommend?style=balanced|popular|discovery`

---

## HTTP response pipeline

`build_recommendations(df, top_n=10, style)`:

1. Normalize + score TBR
2. Take top 10
3. Attach `explanation` (template from author history)
4. Attach `similar_books` (up to 3 finished reads, same author preferred)

Cached in `get_recommendation()` (`@lru_cache`, per style). Invalidated on book writes.

---

## Legacy: `recommend_one`

Samples one random book from top 5 TBR rows. **Not used** by current `GET /recommend` (returns top 10 structured list instead).

---

## Column resolution

`_resolve_column(df, candidates)` maps app columns (`Title`, `Read Status`) and canonical columns (`title`, `read_status`).

---

## Storage

Scores and normalized features are **computed in memory** — not written back to `books.csv`.

| Call site | Functions |
|-----------|-----------|
| `GET /recommend` | normalize → score_tbr → build explanations |
| Batch pipeline | above + `score_read_books` |
