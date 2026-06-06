# User research

Documentation of reader behavior, feedback themes, and product assumptions for ShelfTxt. This section is about **understanding readers**—not APIs, scoring formulas, or deployment.

ShelfTxt is pre-release. Research here is **early and evolving**. Conclusions are provisional until validated with more users and structured studies.

---

## Purpose

- Capture what readers say they need when choosing books from a personal TBR
- Record assumptions before building features—and whether feedback supports or challenges them
- Give contributors context for *why* product choices exist (explanations, insights page, recommendation styles, etc.)
- Separate **what we observed** from **what we might build**

---

## Why feedback is collected

Early conversations (online reading communities and direct outreach) suggested that many readers do not lack books—they lack **confidence in the next choice**. ShelfTxt aims to reduce decision fatigue with transparent, library-based suggestions—not to replace Goodreads, StoryGraph, or spreadsheet systems entirely.

Feedback helps answer:

- Who feels overwhelmed vs. who already has a system that works
- Which decision signals matter (mood, author, challenge prompts, availability)
- Whether “better rankings” alone solve the problem readers describe

---

## How research influences product

| Research output | Product influence (examples) |
|-----------------|------------------------------|
| Desire for transparency | Recommendation explanations + “Similar to” finished reads |
| TBR overwhelm | Top pick on dashboard, “pick one next” framing—not infinite lists |
| Forgotten context | `why_added` noted as future field in [engineering/data-model.md](../../engineering/data-model.md) |
| Mood/context | Recommendation styles; mood tags flagged as opportunity—not shipped |
| Non-technical users | Insights page replaces API-focused “System” page |

Research does **not** automatically become a roadmap commitment. See [feature-opportunities.md](./feature-opportunities.md) and [product/roadmap.md](../roadmap.md).

---

## Types of information

| Type | Definition | Example |
|------|------------|---------|
| **User observation** | Something readers described doing or feeling | “I forget why I added half my TBR.” |
| **Validated finding** | Pattern seen repeatedly or confirmed by behavior change requests | Multiple readers asked *why* a book was suggested |
| **Feature idea** | A possible product response—not evidence | Optional “why I added this” note field |
| **Archetype** | A simplified reader model for discussion | Overwhelmed Reader |

When in doubt, label content as **observation** or **hypothesis** until stronger evidence exists.

---

## Table of contents

| Document | Contents |
|----------|----------|
| [research-summary.md](./research-summary.md) | Executive summary, assumptions vs learnings |
| [reader-archetypes.md](./reader-archetypes.md) | Reader models and ShelfTxt relevance |
| [decision-making-patterns.md](./decision-making-patterns.md) | How readers choose books |
| [assumptions-validation.md](./assumptions-validation.md) | Assumption tracker with status |
| [feature-opportunities.md](./feature-opportunities.md) | Observations → opportunities (not commitments) |
| [research-log.md](./research-log.md) | Chronological log of feedback sources |

---

## Related docs

- [product/roadmap.md](../roadmap.md) — engineering/product direction informed by themes here
- [opensource.md](../../contributors/opensource.md) — mission: reading accessibility, less overwhelm
- [engineering/frontend.md](../../engineering/frontend.md) — reader-focused UI principles

---

## Contributing research notes

When adding feedback:

1. Append an entry to [research-log.md](./research-log.md) (no usernames, no direct quotes)
2. Update [assumptions-validation.md](./assumptions-validation.md) if an assumption shifts
3. Add or refine archetypes/patterns only when supported by multiple observations
4. Propose features in [feature-opportunities.md](./feature-opportunities.md)—not as confirmed scope
