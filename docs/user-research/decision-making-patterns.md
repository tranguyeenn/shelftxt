# Decision-making patterns

Observed and reported ways readers select their next book. Summarized **anonymously** from community discussions and early outreach—no direct quotes.

For each pattern: **description**, **supporting observations**, **implications for ShelfTxt**.

---

## Mood and energy

**Description**  
Readers choose based on how they feel today—seeking comfort, challenge, escapism, or low cognitive load—not strictly on what they rated highest historically.

**Supporting observations**

- Frequently cited when explaining why a long-planned book stays unread
- Mood Reader archetype; theme in [research-summary.md](./research-summary.md)

**Implications**

- Current ranker uses author/rating history, not mood
- Opportunity: mood tags, “what I want tonight” filter, mood-aware ranking (see [feature-opportunities.md](./feature-opportunities.md))
- Recommendation **styles** (discovery vs popular) are a partial proxy, not a full mood model

---

## Genre and tone

**Description**  
Genre labels (and subgenre vibes) narrow the candidate set before author or plot considerations.

**Supporting observations**

- Catalog readers rely on genre sorts
- Batch pipeline supports genre in canonical schema; **live app CSV does not**

**Implications**

- Genre-aware filtering is a documented gap
- Similar-books explanations today are author-based, not genre-based

---

## Author and series loyalty

**Description**  
Readers return to trusted authors or continue series in order.

**Supporting observations**

- Aligns with ShelfTxt’s author-preference scoring
- Series readers report pain when series metadata is missing

**Implications**

- **Strength today:** author affinity in TBR ranking
- **Gap:** series continuity, not modeled in CSV

---

## Reviews and ratings (external)

**Description**  
Star ratings, professional reviews, and aggregate scores influence whether a TBR book stays “eligible” mentally.

**Supporting observations**

- Less about ShelfTxt’s internal ranker; more about initial add decision
- Some readers distrust crowdsourced scores for niche tastes

**Implications**

- Internal ratings on **finished** books already feed ranker
- Importing external review metadata is out of scope today

---

## Reading challenges and prompts

**Description**  
Seasonal challenges (themed prompts, bingo cards, “read X in Y month”) reorder priorities.

**Supporting observations**

- Goal-Oriented Reader archetype
- Mentioned in early feedback themes ([future-roadmap](../system-design/future-roadmap.md))

**Implications**

- No challenge entity in data model
- Challenge-aware views would serve a subset, not all users

---

## Library / Libby availability

**Description**  
Final choice depends on whether a book is available to borrow, hold, or buy affordably now.

**Supporting observations**

- Raised in practical “what I actually read this week” discussions
- Not yet validated as top pain for ShelfTxt testers specifically

**Implications**

- Long-term integration possibility—complex (APIs, regional libraries)
- Recommendations may suggest books readers cannot access immediately

**Evidence strength:** moderate for general reader behavior; **low** for ShelfTxt-specific demand

---

## Cover and marketing appeal

**Description**  
Cover art, title, and back-copy influence impulse adds and spontaneous picks from the shelf.

**Supporting observations**

- More relevant to **adding** books than ranking existing TBR
- Intuitive Browsers archetype

**Implications**

- Low priority for backend ranker
- UI cover placeholders today are generic—fine for MVP

---

## Recent reads and recency

**Description**  
Readers avoid repeating similar tones back-to-back or chase novelty after a genre binge.

**Supporting observations**

- `recency_norm` exists in preprocess but is secondary in TBR scoring
- Some want “something different from last finish”

**Implications**

- Could extend ranker with anti-repetition or genre spacing—**not implemented**
- “Discovery” style adds randomness, not recency logic

---

## Friends and social recommendation

**Description**  
Trusted human recommendations outweigh algorithms for some readers.

**Supporting observations**

- Reported as primary discovery channel before TBR stage
- Less feedback on sharing lists inside an app

**Implications**

- ShelfTxt focuses post-discovery (TBR already populated)
- Social/shared lists are long-term, auth-dependent

---

## Randomness and “pick for me”

**Description**  
When overwhelmed, readers explicitly want permission to delegate choice—dice, random number, spouse picks.

**Supporting observations**

- Overwhelmed Reader archetype
- Legacy `recommend_one` sampled from top 5; UI now shows top 10 list

**Implications**

- “Pick for me” one-tap mode flagged as future UI idea
- Too many ranked options may conflict with overwhelm-reduction goal

---

## Habit and routine

**Description**  
Fixed reading times, formats (audiobook vs print), or commute length constrain viable picks.

**Supporting observations**

- Mentioned indirectly via “need something short tonight”
- Not deeply explored in current research log

**Implications**

- Format/length fields not in app CSV
- **Insufficient evidence** for dedicated features yet

---

## Pattern summary for product

| Pattern | Modeled in ShelfTxt today? |
|---------|----------------------------|
| Author loyalty | Partially yes |
| Own rating history | Yes (finished books) |
| Mood / energy | No |
| Genre | No (live CSV) |
| Challenges | No |
| Availability | No |
| Why added / intent | No |
| Random / pick-one | Partially (styles + top pick UX) |

Use [assumptions-validation.md](./assumptions-validation.md) to track when evidence changes.
