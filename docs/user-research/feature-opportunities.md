# Feature opportunities

**Observations** describe reader behavior or pain. **Opportunities** are possible product responses—they are **not commitments**, roadmap guarantees, or approved specs.

Priority: **High** / **Medium** / **Low**  
Evidence strength: **Strong** / **Moderate** / **Weak**  
Implementation complexity: **Low** / **Medium** / **High** (rough engineering estimate)

---

## Observation

Readers often forget **why** they added a book to their TBR.

## Opportunity

Optional **“why I added this”** note at add/import time; surface on book detail and in recommendation context.

| | |
|--|--|
| Priority | **High** |
| Evidence | **Strong** |
| Complexity | **Low–Medium** (CSV column + UI; see [data-model](../system-design/data-model.md)) |

---

## Observation

Readers choose based on **mood and energy**, not only past ratings.

## Opportunity

**Mood tags** on books and **mood-based filtering** (or “match my mood tonight” on recommendations).

| | |
|--|--|
| Priority | **High** |
| Evidence | **Moderate** |
| Complexity | **Medium** (schema + UI + ranker integration) |

---

## Observation

**Decision fatigue** peaks when faced with full TBR lists.

## Opportunity

**“Pick for me”** mode—one tap selects from a high-confidence shortlist (e.g., top 3–5), with optional explanation.

| | |
|--|--|
| Priority | **High** |
| Evidence | **Moderate** |
| Complexity | **Low** (mostly UI + existing `/recommend` data) |

---

## Observation

Readers want to know **why** a book was recommended.

## Opportunity

Continue improving **plain-language explanations** and “Similar to” finished reads; hide jargon scores by default.

| | |
|--|--|
| Priority | **Medium** (partially **shipped**) |
| Evidence | **Strong** |
| Complexity | **Low** (copy + UI polish; backend templates exist) |

*Status: explanations shipped; polish and empty-state copy remain.*

---

## Observation

Some readers participate in **reading challenges** with themed prompts.

## Opportunity

**Challenge-aware filtering**—tag books with prompts; filter/rank within active challenge.

| | |
|--|--|
| Priority | **Medium** |
| Evidence | **Moderate** (subset of users) |
| Complexity | **Medium–High** (model + UX for challenges) |

---

## Observation

Readers use **genre** heavily when self-organizing.

## Opportunity

Add **genre** to app CSV; genre filters on Library and Recommendations.

| | |
|--|--|
| Priority | **Medium** |
| Evidence | **Moderate** |
| Complexity | **Medium** (import mapping, UI filters, optional ranker weight) |

---

## Observation

**Series order** matters for continuity readers.

## Opportunity

Series name + position fields; warn or boost “next in series” picks.

| | |
|--|--|
| Priority | **Medium** |
| Evidence | **Weak–Moderate** |
| Complexity | **Medium** (metadata entry burden on users) |

---

## Observation

Readers temporarily want to **hide** genres or authors (burnout, repetition).

## Opportunity

**Snooze / exclude** author or genre from recommendations for a period.

| | |
|--|--|
| Priority | **Medium** |
| Evidence | **Weak** (inferred from “filtering noise” theme) |
| Complexity | **Medium** |

---

## Observation

Final choice depends on **library availability** (Libby/borrowability).

## Opportunity

Surface availability hints or prefer borrowable TBR titles.

| | |
|--|--|
| Priority | **Low** (long-term) |
| Evidence | **Weak** for ShelfTxt-specific demand |
| Complexity | **High** (APIs, regions, partnerships) |

---

## Observation

Readers abandon books (**DNF**) but tools treat them like unread or finished.

## Opportunity

First-class **DNF flow** with optional reason; exclude from positive similarity signals.

| | |
|--|--|
| Priority | **Low–Medium** |
| Evidence | **Weak** |
| Complexity | **Low–Medium** (status exists in API; UI incomplete) |

---

## Observation

**Catalog readers** with working spreadsheets may not need ranking.

## Opportunity

**Export-first** workflow, minimal UI, optional “ranking off” mode.

| | |
|--|--|
| Priority | **Low** |
| Evidence | **Moderate** for segment size unknown |
| Complexity | **Low** |

---

## Observation

Recommendation **style** preferences (safe vs adventurous) vary by reader.

## Opportunity

Expand styles or expose “how adventurous” slider tied to ranker parameters.

| | |
|--|--|
| Priority | **Low** (partially **shipped**) |
| Evidence | **Weak** (shipped without usage study) |
| Complexity | **Low** |

*Status: balanced / popular / discovery styles exist client-side.*

---

## Observation

Readers forget **progress** on in-progress books across devices.

## Opportunity

Server-synced library and accounts.

| | |
|--|--|
| Priority | **Medium** (platform) |
| Evidence | **Insufficient** pre-release |
| Complexity | **High** (auth + database migration) |

---

## How opportunities become roadmap items

1. Repeated evidence in [research-log.md](./research-log.md)
2. Status upgrade in [assumptions-validation.md](./assumptions-validation.md)
3. Alignment with archetype **high** / **very high** relevance
4. Engineering capacity and [future-roadmap](../system-design/future-roadmap.md) fit

Reject opportunities explicitly when evidence stays **Weak** after follow-up.
