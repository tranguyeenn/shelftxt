import {
  bookAuthor,
  bookTitle,
  daysSince,
  finishDateValue,
  parseDate,
  starRating,
  type BookRecord
} from "./books";

export type ScoreFactorKey = "rating" | "recency" | "author" | "other";

export type ScoreFactor = {
  key: ScoreFactorKey;
  label: string;
  value: number;
  weight: number;
  color: string;
  explanation: string;
};

export type ScoreBreakdown = {
  factors: ScoreFactor[];
  composite: number;
  matchLabel: "High Match" | "Moderate Match" | "Exploratory";
};

const WEIGHTS: Record<ScoreFactorKey, number> = {
  rating: 0.4,
  recency: 0.2,
  author: 0.3,
  other: 0.1
};

const FACTOR_META: Record<
  ScoreFactorKey,
  { label: string; color: string; explanation: (ctx: FactorContext) => string }
> = {
  rating: {
    label: "Rating Score",
    color: "score-rating",
    explanation: (ctx) =>
      ctx.authorReadCount > 0
        ? "You rated similar authors highly."
        : "No read history for this author — using your library average."
  },
  recency: {
    label: "Recency Score",
    color: "score-recency",
    explanation: (ctx) =>
      ctx.daysSinceLastRead === null
        ? "No finish dates yet — neutral recency signal."
        : ctx.daysSinceLastRead > 90
          ? "It's been a while since you finished a book."
          : "You have recent reading activity in your log."
  },
  author: {
    label: "Author Score",
    color: "score-author",
    explanation: (ctx) =>
      ctx.authorReadCount > 0
        ? "You enjoy this author based on past ratings."
        : "Author preference inferred from your overall ratings."
  },
  other: {
    label: "Other Factors",
    color: "score-other",
    explanation: () => "Genre & popularity signals (placeholder until genre weighting ships)."
  }
};

type FactorContext = {
  authorReadCount: number;
  daysSinceLastRead: number | null;
};

function clamp01(n: number): number {
  return Math.min(1, Math.max(0, n));
}

function normalizeRatings(library: BookRecord[]): Map<string, number> {
  const read = library.filter((b) => String(b["Read Status"] ?? "").toLowerCase() === "read");
  const ratings = read
    .map((b) => starRating(b))
    .filter((r): r is number => r !== null);
  if (ratings.length === 0) {
    return new Map();
  }
  const min = Math.min(...ratings);
  const max = Math.max(...ratings);
  const span = max - min || 1;
  const map = new Map<string, number>();
  for (const book of read) {
    const r = starRating(book);
    const norm = r === null ? 0.5 : (r - min) / span;
    map.set(`${bookTitle(book)}::${bookAuthor(book)}`, clamp01(norm));
  }
  return map;
}

function authorPreference(library: BookRecord[], author: string): number {
  const read = library.filter(
    (b) =>
      String(b["Read Status"] ?? "").toLowerCase() === "read" &&
      bookAuthor(b).toLowerCase() === author.toLowerCase()
  );
  const ratings = read.map((b) => starRating(b)).filter((r): r is number => r !== null);
  if (ratings.length === 0) {
    const allRead = library.filter((b) => String(b["Read Status"] ?? "").toLowerCase() === "read");
    const allRatings = allRead.map((b) => starRating(b)).filter((r): r is number => r !== null);
    if (allRatings.length === 0) return 0.5;
    const mean = allRatings.reduce((a, b) => a + b, 0) / allRatings.length;
    return clamp01(mean / 5);
  }
  const mean = ratings.reduce((a, b) => a + b, 0) / ratings.length;
  return clamp01(mean / 5);
}

function recencySignal(library: BookRecord[]): { score: number; daysSinceLastRead: number | null } {
  const read = library.filter((b) => String(b["Read Status"] ?? "").toLowerCase() === "read");
  const dates = read
    .map((b) => parseDate(finishDateValue(b)))
    .filter((d): d is Date => d !== null);
  if (dates.length === 0) {
    return { score: 0.5, daysSinceLastRead: null };
  }
  const mostRecent = dates.reduce((a, b) => (a > b ? a : b));
  const days = daysSince(mostRecent);
  const score = clamp01(days / 365);
  return { score, daysSinceLastRead: days };
}

export function buildScoreBreakdown(
  book: BookRecord,
  library: BookRecord[]
): ScoreBreakdown {
  const author = bookAuthor(book);
  const authorReadCount = library.filter(
    (b) =>
      String(b["Read Status"] ?? "").toLowerCase() === "read" &&
      bookAuthor(b).toLowerCase() === author.toLowerCase()
  ).length;

  const ratingMap = normalizeRatings(library);
  const readSameAuthor = library.filter(
    (b) =>
      String(b["Read Status"] ?? "").toLowerCase() === "read" &&
      bookAuthor(b).toLowerCase() === author.toLowerCase()
  );
  let ratingScore = authorPreference(library, author);
  if (readSameAuthor.length > 0 && ratingMap.size > 0) {
    const norms = readSameAuthor
      .map((b) => ratingMap.get(`${bookTitle(b)}::${bookAuthor(b)}`))
      .filter((n): n is number => n !== undefined);
    if (norms.length > 0) {
      ratingScore = norms.reduce((a, b) => a + b, 0) / norms.length;
    }
  }

  const { score: recencyScore, daysSinceLastRead } = recencySignal(library);

  const authorScore =
    typeof book.author_score === "number"
      ? clamp01(book.author_score)
      : authorPreference(library, author);

  const otherScore = 0.2;

  const ctx: FactorContext = { authorReadCount, daysSinceLastRead };

  const raw: Record<ScoreFactorKey, number> = {
    rating: ratingScore,
    recency: recencyScore,
    author: authorScore,
    other: otherScore
  };

  const factors = (Object.keys(WEIGHTS) as ScoreFactorKey[]).map((key) => ({
    key,
    label: FACTOR_META[key].label,
    value: clamp01(raw[key]),
    weight: WEIGHTS[key],
    color: FACTOR_META[key].color,
    explanation: FACTOR_META[key].explanation(ctx)
  }));

  const composite =
    typeof book.score === "number"
      ? clamp01(book.score)
      : clamp01(
          factors.reduce((sum, f) => sum + f.value * f.weight, 0)
        );

  const matchLabel: ScoreBreakdown["matchLabel"] =
    composite >= 0.65 ? "High Match" : composite >= 0.4 ? "Moderate Match" : "Exploratory";

  return { factors, composite, matchLabel };
}

export function formatScore(value: number): string {
  return value.toFixed(2);
}
