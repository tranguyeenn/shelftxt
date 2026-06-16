# Future roadmap

Roadmap split into **reader-facing** outcomes and **engineering** enablers. Items are informed by early anonymous reader feedback (TBR overwhelm, wanting reasons for picks, tracking why books were added, mood/context, reading challenges)—not fixed commitments or dates.

ShelfTxt remains **pre-release**; order and scope will change.

---

## Reader-facing roadmap

### Near-term (aligns with current codebase)

| Feature | Status / direction |
|---------|-------------------|
| Library with status + progress | **Shipped** — Library, book detail |
| Top recommendations with explanations | **Shipped** — Dashboard, Recommendations page |
| CSV import / export | **Shipped** — Settings |
| Reading insights (non-technical) | **Shipped** — Insights page |
| Delete book / clear library | **Shipped** |
| Recommendation style (balanced / popular / discovery) | **Shipped** — client setting + query param |
| Appearance toggles (theme, accent, compact) | **Shipped** — client-only |
| Account login + private libraries | **Shipped** — Supabase Auth, profiles, user-owned books |

### Near-term (gaps vs feedback)

| Feature | Notes |
|---------|-------|
| **Better filtering** | Genre/mood/status combinations on library and recommendations |
| **Recommendation explanations polish** | Clearer “similar to” reasoning; surface when history is thin |
| **Book detail notes** | `user_notes`, `why_added` capture at add/import time |
| **DNF as first-class UI** | Explicit did-not-finish flow vs completed |

### Mid-term

| Feature | Notes |
|---------|-------|
| **Mood tags** | Tag books; filter/rank by current mood |
| **“Why I added this” context** | Store `why_added`; use in explanations |
| **Reading challenge support** | Challenge prompts, progress within a subset |
| **Pick for me** | One-tap choice from ranked pool |
| **Server-synced preferences** | Settings follow account/device |

### Long-term

| Feature | Notes |
|---------|-------|
| **Libby / library availability** | Possible integration to prefer borrowable titles — **speculative**, rights/API constraints |
| **Social / shared lists** | Shared TBR or recommendations — builds on existing auth model |
| **Smarter similarity** | Genre, theme, pace — beyond author-only |
| **Import from Goodreads/StoryGraph** | Dedicated mappers |

---

## Engineering roadmap

### Near-term

| Item | Rationale |
|------|-----------|
| Deterministic ranking tests | Safe refactors to scoring |
| PostgreSQL/Auth follow-up | SQL-level pagination, remaining CSV-adjacent paths, DB/auth integration tests |
| Remove / archive `api_draft.py` | Reduce confusion |
| Document OpenAPI ↔ system-design parity | Keep docs trustworthy |
| Expand progress + patch test coverage | Shelf edge cases |

### Mid-term

| Item | Rationale |
|------|-----------|
| Repository + service tests with real DB | Integration confidence |
| UI pagination on Library (server `GET /books` already paginated) | Large libraries |
| Structured response schemas beyond book CRUD | OpenAPI completeness |
| Optional Redis cache | Multi-instance recommend cache |

### Long-term

| Item | Rationale |
|------|-----------|
| Background jobs | Recompute ranks on schedule |
| Analytics (privacy-preserving) | Which explanations help picks |
| Serverless / edge evaluation | Cost vs latency tradeoffs |

---

## Feedback themes (anonymous summary)

Early conversations with prospective readers highlighted:

- **TBR guilt / overwhelm** — want help choosing one next book, not a longer list
- **Transparency** — prefer knowing *why* something was suggested
- **Context at add time** — “why is this on my list?” forgotten later
- **Mood and energy** — matching book to current capacity, not only past ratings
- **Challenges** — seasonal or themed reading goals
- **Filtering noise** — hide genres/authors temporarily

These inform mid-term product design; they do not imply committed delivery dates.

---

## How to propose changes

1. Check overlap with this roadmap and [ROADMAP.md](../../ROADMAP.md)
2. Open a feature request with problem + minimal solution
3. For scoring changes, include fixture library + expected order
4. For data model additions, describe CSV backward compatibility

---

## Document maintenance

Update this file when:

- A near-term item ships (move to architecture/recommendation docs as **current**)
- A long-term item is explicitly rejected (note why)
- Storage or auth strategy is decided (update scalability doc too)
