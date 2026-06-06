# Assumptions validation

Tracker for product assumptions vs. early evidence. Status definitions:

| Status | Meaning |
|--------|---------|
| **Supported** | Multiple independent observations or strong alignment with built feedback |
| **Partially Supported** | Some evidence; exceptions or weak sample |
| **Not Supported** | Feedback contradicts or audience doesn't care |
| **Insufficient Evidence** | Mentioned once or inferred; needs more research |

---

## Assumption table

| Assumption | Evidence | Status | Rationale |
|------------|----------|--------|-----------|
| Readers struggle primarily because TBRs are too **large** | Many describe guilt/paralysis with long lists; some large-TBR users are fine with catalogs | **Partially Supported** | Size correlates with overwhelm for some archetypes, not all. Problem may be **choice**, not count. |
| Readers choose based on **mood** in the moment | Recurring theme in community summaries; Mood Reader archetype | **Partially Supported** | Frequently described; not measured in-app. Ranker does not encode mood yet. |
| Readers **forget why** books were added | Repeated in early feedback themes; aligns with “context at add time” | **Supported** | Consistent theme; motivates `why_added` discussions. |
| Readers want **transparency** in recommendations | Requests for explanations; skepticism of black-box picks | **Supported** | D drove explanation UI and non-technical Insights. |
| Readers use **external systems** for choosing (GR, StoryGraph, sheets) | Many report existing workflows; Catalog readers satisfied | **Supported** | ShelfTxt must complement, not assume greenfield users. |
| **Efficiency** (fastest pick) is the primary goal | Overwhelmed readers want fewer decisions; browsers want exploration | **Partially Supported** | Subgroups differ. One-tap pick vs ranked list both requested. |
| **Author history** is sufficient for good TBR ranking | Aligns with initial ranker; feedback says mood/genre/challenge also matter | **Partially Supported** | Good baseline signal, not complete model. |
| Readers want **more ranked options** (long lists) | Some want top 10; others want single suggestion | **Partially Supported** | Risk of overwhelm if list is primary UX. |
| **Reading challenges** influence next-book choice | Mentioned by goal-oriented participants | **Partially Supported** | Smaller vocal subset; not universal. |
| **Library/Libby availability** drives final choice | Practical discussions of borrowing; limited ShelfTxt-specific validation | **Insufficient Evidence** | Plausible; needs targeted interviews. |
| Readers will trust **rule-based** explanations over ML marketing | Open-source/transparency mission resonates with early audience | **Partially Supported** | Self-selected open-source curious users may skew positive. |
| Genre sorting is essential for all users | Catalog readers yes; overwhelmed readers want reduction | **Partially Supported** | Important segment, not universal need. |
| Recommendation **styles** (balanced/popular/discovery) map to real preferences | Shipped from settings feedback; minimal usage data | **Insufficient Evidence** | Needs analytics or interviews post-launch. |
| CSV + simple library is acceptable for early adopters | No mass complaint in pre-release; dev audience tolerant | **Insufficient Evidence** | Durability/multi-device not tested at scale. |
| DNF / abandoned books should be tracked explicitly | Less frequent than overwhelm/mood themes | **Insufficient Evidence** | Noted in roadmap; weak direct feedback so far. |

---

## Former assumptions revised

| Original assumption | Revision |
|--------------------|----------|
| “Build System page explaining ranker to users” | Reader-facing **Insights** instead—technical docs for contributors |
| “Single random recommendation is enough” | Top **10 with explanations** + dashboard pick—more alignment with transparency theme |
| “Everyone needs full shelf CRUD” | Catalog readers may only need light touch + export |

---

## How to update

When new feedback arrives:

1. Add row or change status with one-sentence rationale
2. Link to [research-log.md](./research-log.md) entry
3. If **Supported**, consider updating [feature-opportunities.md](./feature-opportunities.md)
4. If **Not Supported**, document what **not** to build

Avoid upgrading status on single anecdotes.
