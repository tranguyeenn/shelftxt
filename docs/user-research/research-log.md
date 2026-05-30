# Research log

Chronological record of feedback sources and synthesized insights. **Do not include usernames, profile links, or verbatim quotes** that could identify individuals.

Use the template below for each entry.

---

## Entry template

```markdown
### YYYY-MM-DD — [Short title]

**Source:** (e.g., online community thread, informal interview, issue comment)  
**Community:** (e.g., book subreddit, beta tester DM, GitHub discussion)  
**Feedback summary:** (2–4 sentences, anonymous)  
**Insights:** (bullets)  
**Potential follow-up questions:** (bullets)
```

---

## 2026-03 — Early online reading community discussions

**Source:** Informal threads and comments in online book/reading communities (including Reddit-style discussion forums among prospective readers). Specific posts are **not archived in this repository**; themes below are maintainer-synthesized summaries used in project planning.

**Community:** Public reading/TBR communities (English-language); small sample of engaged commenters and thread participants

**Feedback summary:**  
Participants frequently discussed **TBR guilt** and difficulty choosing a single next book despite owning many unread titles. Several described **forgetting why** titles were added after weeks or months. A common thread was skepticism toward opaque algorithmic picks—preference for understanding **why** something was suggested. Multiple commenters organized by **mood**, **genre**, or **reading challenges** rather than strict list order. Some reported satisfaction with existing tools (Goodreads, StoryGraph, spreadsheets) and saw limited need for another organizer unless it reduced decisions or captured missing context.

**Insights:**

- Core pain aligns with **decision fatigue**, not necessarily discovery
- **Transparency** in recommendations appears as trust requirement, not nice-to-have
- **Mood/context** and **challenge prompts** are decision signals the current author-only ranker underweights
- Audience includes **Overwhelmed Readers** (high fit) and **Catalog Readers** (lower fit)
- “Pick one for me” framing resonated more than “here is your sorted list of 50”
- Practical constraints (**availability**, format, length) mentioned as final gatekeepers

**Potential follow-up questions:**

- When you open your TBR, do you want one suggestion, a shortlist, or the full list?
- What do you wish you had written down when you added your last three books?
- How often does mood override your “planned” next read?
- Do reading challenges change your queue weekly or occasionally?
- Would you trust a rule-based explanation if you could read the logic?
- What would make you export from your current tool into ShelfTxt?

**Documentation actions taken:**

- Themes captured in [research-summary.md](./research-summary.md)
- Archetypes drafted in [reader-archetypes.md](./reader-archetypes.md)
- Product direction cross-linked in [system-design/future-roadmap.md](../system-design/future-roadmap.md)
- Shipped: explainable recommendations, Insights page, recommendation styles

---

## 2026-03 — Internal product review (pre-release)

**Source:** Maintainer synthesis after implementing Library, Insights, Settings, and top-10 recommendations

**Community:** N/A (internal)

**Feedback summary:**  
Building reader-facing Insights surfaced a gap: early UI leaned technical. Feedback themes implied users want **stats and patterns**, not API documentation. Explanation toggles and recommendation styles address preference variance but lack usage validation.

**Insights:**

- Documentation split (user research vs system design) is necessary
- Need real user sessions before prioritizing mood vs challenges vs notes

**Potential follow-up questions:**

- Run 5–8 moderated sessions with Overwhelmed Reader archetype
- Add optional in-app “was this helpful?” on explanations (privacy-preserving)

---

## Future entries

Add new entries above this line (newest first). Link assumption or opportunity updates when applicable.
