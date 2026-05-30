# Research summary

Executive overview of early reader research for ShelfTxt. Based on informal community discussions, direct conversations with prospective readers, and synthesis documented in project planning—not a formal quantitative study.

**Sample limitations:** Small, self-selected audience; mostly English-language online reading communities; no in-app analytics yet. Treat findings as **directional**.

---

## Executive summary

Many prospective readers describe a **TBR management** problem more than a **book discovery** problem. They already know what they might read; they struggle to **choose one next book** with confidence. ShelfTxt’s current direction—ranking *your* list with explanations—aligns with this, but several feedback themes (mood, challenges, “why I added this”) are **not yet built**.

Readers who maintain strong external systems (spreadsheets, tags, series tracking) may see less value in another organizer unless it reduces decision steps or adds missing context.

---

## Most common themes

1. **Decision fatigue** — large TBR lists feel guilt-inducing, not motivating
2. **Transparency** — skepticism toward opaque “AI picks”; preference for knowing *why*
3. **Forgotten intent** — books added months ago without remembered context
4. **Mood and energy** — “what I feel like reading” often overrides pure rating history
5. **Reading challenges** — seasonal prompts influence what gets picked next
6. **Existing tools** — many already use Goodreads, StoryGraph, Libby, or custom spreadsheets

---

## Unexpected findings

- **Ranking alone may not be enough** — some readers wanted *one* suggestion or a random pick from a good shortlist, not a longer ranked table
- **Organization-satisfied readers exist** — a subset reported minimal pain; their barrier is time, not tooling
- **Author affinity is intuitive but incomplete** — readers agree author history matters, but mood/genre/challenge often break that pattern in the moment
- **Library availability matters in practice** — even with a perfect TBR pick, borrowability affects the final choice (not addressed in product today)

---

## How readers choose books (current understanding)

Selection is usually **multi-factor and situational**:

- Short-term: mood, energy, length, format availability
- Medium-term: series position, reading challenges, “clearing” old TBR additions
- Long-term: favorite authors, genres, trusted recommendations

ShelfTxt currently models **long-term taste** (finished books, ratings, author preference) better than **short-term context** (mood, challenge prompt, Libby hold).

---

## Key takeaways

1. Primary job-to-be-done: **help pick the next read from an existing TBR**, not find new books globally
2. Explanations and trust matter as much as score quality for early adopters
3. Context captured **at add time** may be as important as context inferred **at recommend time**
4. Different reader archetypes need different depth of features—one UI will not fit all
5. More structured research (interviews, usability tests) is needed before major scope bets

---

## What we thought

Initial product assumptions before sustained feedback:

| Assumption | Rationale at the time |
|------------|------------------------|
| Large TBRs are the core problem | ShelfTxt started as a TBR ranker |
| Recommendations are the main gap | Focus on scoring and `/recommend` |
| Efficiency is the primary goal | Optimize pick speed, reduce steps |
| Author/rating history is enough signal | Matches initial rule-based ranker |
| Readers want another full library app | Build import, shelf, progress tracking |
| Technical transparency appeals to everyone | Expose scoring concepts early in UI |

---

## What we learned

| Finding | Evidence strength | Notes |
|---------|-------------------|-------|
| Many readers feel **overwhelmed choosing**, not overwhelmed storing | Moderate | Repeated in community themes; aligns with “pick one next” framing |
| **Transparency** in suggestions is valued | Moderate | Requests for “why this book”; informed explanation UI |
| **Mood/context** often drives the final pick | Moderate | Described more than modeled in current ranker |
| **Why a book was added** is frequently forgotten | Moderate | Supports future `why_added` field discussions |
| Some readers already have **working systems** | Moderate | Catalog-style readers; lower urgency for re-organization |
| **Challenges** shape reading queues | Low–moderate | Mentioned less often but passionately by participants |
| Pure efficiency is **not** everyone’s goal—some want permission to browse | Low | Hypothesis; needs more interviews |
| Author-based similarity is **necessary but insufficient** | Moderate | Matches gap between ranker and stated decision patterns |

**Distinction:** Assumptions in the first table were design starting points. Findings in the second table are **synthesized observations**—not all are validated at scale.

---

## Implications for ShelfTxt today

**Aligned with feedback:**

- Explainable recommendations (dashboard, top 10, insights)
- Reader-facing Insights (not developer System page)
- Recommendation styles (balanced / popular / discovery) as a lightweight preference knob

**Gaps vs feedback:**

- Mood tags and filtering
- “Why I added this” notes
- Challenge-aware organization
- Availability (Libby/library) integration
- Strong genre modeling in live CSV schema

See [feature-opportunities.md](./feature-opportunities.md) for prioritized opportunities.
