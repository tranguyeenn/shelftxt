# Reader archetypes

Simplified models to discuss **who ShelfTxt is for** and who it may not serve well yet. Archetypes are **hypotheses** derived from early feedback themes—not statistically validated segments.

Each archetype includes relevance to ShelfTxt: **low**, **medium**, **high**, or **very high**.

---

## Catalog Reader

**Characteristics**

- Sorts by genre, author, or series deliberately
- Maintains spreadsheets, tags, or app shelves with clear rules
- Often finishes books in planned order (series, awards lists)

**Current workflow**

- Uses Goodreads, StoryGraph, Notion, or custom trackers
- Adds books with metadata already in mind
- Chooses next read from pre-sorted lists or schedules

**Pain points**

- Minimal decision pain; occasional sync annoyance across tools
- Time to maintain system, not confusion about what to read

**ShelfTxt relevance:** **Low**

- May use import/export but unlikely to need ranking heavily
- Value prop is organizational overlap unless ShelfTxt adds unique context (notes, mood)

---

## Mood Reader

**Characteristics**

- Chooses based on current mood, energy, or desired emotional experience
- Alternates genres intentionally (e.g., heavy vs. light)
- Less attached to strict TBR order

**Current workflow**

- Browses shelves intuitively
- Asks “what do I feel like tonight?”
- May abandon planned picks if mood shifts

**Pain points**

- Narrowing many options to one that *fits today*
- TBR lists do not encode mood/intent

**ShelfTxt relevance:** **High**

- Needs mood/context signals not fully in product today
- Explanation + shortlist helps; mood filters would help more

---

## Overwhelmed Reader

**Characteristics**

- Large or aging TBR; difficulty committing to one book
- Forgets titles or why items were added
- Describes guilt, paralysis, or random selection as coping

**Current workflow**

- Random pick, coin flip, or “close eyes and point”
- Sometimes re-buys books already owned
- Avoids opening full TBR lists

**Pain points**

- Decision fatigue
- Shame about unread pile
- Lack of trusted nudge toward *one* reasonable next choice

**ShelfTxt relevance:** **Very high**

- Core audience for “recommended next” and top-10 with explanations
- Risk: showing *more* ranked options could worsen overwhelm—UI framing matters

---

## Goal-Oriented Reader

**Characteristics**

- Participates in reading challenges (seasonal, themed, prompt-based)
- Tracks progress toward numeric or thematic goals
- Willing to defer “want” reads for challenge fit

**Current workflow**

- Filters TBR mentally by challenge tags
- Maintains separate lists or notes for prompts
- Uses spreadsheets or challenge-specific threads

**Pain points**

- Matching owned TBR books to specific prompts
- Splitting attention between challenge queue and general TBR

**ShelfTxt relevance:** **Medium**

- Could benefit from challenge tags/filters
- Current ranker does not model challenge context

---

## Intuitive Browsers

**Characteristics**

- Enjoys discovering within an existing pile
- Less interested in scores; more in covers, vibes, recency of addition
- May read samples or first chapters before committing

**Current workflow**

- Physical shelf scanning or app browsing
- Picks what “calls to them” visually or emotionally

**Pain points**

- Tools that feel overly algorithmic or rigid
- Pressure to optimize reading

**ShelfTxt relevance:** **Low–medium**

- May appreciate “discovery” recommendation style
- May dislike numeric scores unless framed softly

*Evidence strength: lower than other archetypes— inferred from contrast with goal-oriented and overwhelmed patterns.*

---

## Series / Continuity Reader

**Characteristics**

- Strong preference for finishing series in order
- Remembers where they left off across multiple books
- Frustrated when tools treat series entries as unrelated

**Current workflow**

- Tracks series externally or by memory
- Prioritizes “book 2” over new standalone TBR entries

**Pain points**

- Series context missing in flat TBR lists
- Accidentally starting book 3 before book 2

**ShelfTxt relevance:** **Medium** (until series metadata exists)

- Author-based ranking partially helps same-author picks
- No series field in current CSV schema

*Evidence strength: moderate in genre/community discussions; not yet a top feedback theme in ShelfTxt logs.*

---

## Using archetypes

- Do not treat readers as one archetype only—**combinations are common** (e.g., Overwhelmed + Mood)
- Feature priority should weight **very high** and **high** relevance archetypes first
- Validate archetypes with interviews before marketing or positioning claims

Update this doc when [research-log.md](./research-log.md) entries support new patterns or weaken existing ones.
