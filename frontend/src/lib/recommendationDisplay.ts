import type { RecommendationItem } from "@/lib/types";

export type RecommendationReason = {
  label: string;
  detail: string;
};

function sentenceJoin(parts: string[]): string {
  const filtered = parts.map((part) => part.trim()).filter(Boolean);
  if (filtered.length === 0) return "";
  if (filtered.length === 1) return filtered[0];
  if (filtered.length === 2) return `${filtered[0]} and ${filtered[1]}`;
  return `${filtered.slice(0, -1).join(", ")}, and ${filtered[filtered.length - 1]}`;
}

function readingCategory(genres: string[]): string {
  const normalized = genres.map((genre) => genre.toLowerCase());
  if (normalized.some((genre) => genre.includes("romance"))) return "romance";
  if (normalized.some((genre) => genre.includes("fantasy"))) return "fantasy";
  if (normalized.some((genre) => genre.includes("historical"))) return "historical fiction";
  if (normalized.some((genre) => genre.includes("classic") || genre.includes("literary"))) {
    return "literary classics";
  }
  if (genres.length > 0) return genres.slice(0, 2).join(" and ");
  return "books";
}

export function recommendationMatchPercent(score: number): number {
  return Math.round(Math.min(1, Math.max(0, score)) * 100);
}

export function signalLabel(value: number | null | undefined): string | null {
  if (value == null || !Number.isFinite(value)) return null;
  if (value < 25) return "Low";
  if (value < 50) return "Medium";
  if (value < 75) return "High";
  return "Very High";
}

export function recommendationSignals(item: RecommendationItem): Array<{ label: string; value: number; display: string }> {
  const source = item.signals ?? item.recommendation_breakdown ?? {};
  return [
    ["Genre Match", source.genre_fit],
    ["Theme Match", source.mood_match],
    ["Reader Similarity", source.reader_similarity],
    ["Author Affinity", source.author_affinity]
  ].flatMap(([label, value]) => {
    const numeric = typeof value === "number" ? value : null;
    const display = signalLabel(numeric);
    return display && numeric !== null ? [{ label: String(label), value: numeric, display }] : [];
  });
}

export function buildRecommendationReasons(item: RecommendationItem): RecommendationReason[] {
  if (item.recommendation_reasons?.length) {
    return item.recommendation_reasons
      .filter((reason) => reason.label.trim() && reason.detail.trim())
      .slice(0, 4);
  }

  const reasons: RecommendationReason[] = [];
  const genres = [...(item.matched_genres ?? []), ...(item.matched_subjects ?? [])].slice(0, 4);

  if (genres.length > 0) {
    reasons.push({
      label: "Genre fit",
      detail: genres.join(", ")
    });
  }

  if ((item.matched_liked_books ?? []).length > 0) {
    reasons.push({
      label: "Rating similarity",
      detail: `Similar to ${item.matched_liked_books?.slice(0, 2).map((book) => book.title).join(", ")}`
    });
  }

  if (item.similar_books.length > 0) {
    reasons.push({
      label: "Recent reading pattern",
      detail: `Related to ${item.similar_books.slice(0, 2).map((book) => book.title).join(", ")}`
    });
  }

  if (genres.length > 0) {
    reasons.push({
      label: "Mood match",
      detail: genres.slice(0, 2).join(", ")
    });
  }

  return reasons;
}

export function recommendationFallbackExplanation(item: RecommendationItem): string {
  const text = item.reason || item.explanation;
  const genericBackendFallback = ["Recommended based", "on your reading history."].join(" ");
  if (text?.trim() && text.trim() !== genericBackendFallback) {
    return text.trim();
  }
  return "This is the strongest available match from your current library, but detailed genre and theme signals are not available yet.";
}

export function readerFacingExplanation(item: RecommendationItem): string {
  const book = item.recommended_book ?? item.book;
  const genres = (item.matched_genres ?? []).slice(0, 3);
  const themes = (item.matched_subjects ?? []).slice(0, 3);
  const inspiredBy = (
    item.related_books ??
    item.recommendation_breakdown?.inspired_by ??
    item.matched_liked_books ??
    []
  ).slice(0, 3);
  const authors = (item.matched_authors ?? []).slice(0, 2);
  const signals = recommendationSignals(item);
  const sentences: string[] = [];

  if (inspiredBy.length > 0) {
    const titles = sentenceJoin(inspiredBy.slice(0, 2).map((liked) => liked.title));
    const descriptor =
      themes.length > 0
        ? `for its similar themes of ${sentenceJoin(themes.slice(0, 2))}`
        : genres.length > 0
          ? `as another ${readingCategory(genres)} read`
          : "for a similar reading experience";
    sentences.push(
      `Because you enjoyed ${titles}, you may enjoy ${book.title} ${descriptor}.`
    );
  }

  if (genres.length > 0 && themes.length > 0) {
    sentences.push(
      `You've enjoyed ${readingCategory(genres)}, and ${book.title} shares themes of ${sentenceJoin(themes)}.`
    );
  } else if (genres.length > 0) {
    sentences.push(
      `Because you rated ${readingCategory(genres)} highly, ${book.title} is a strong match for your reading preferences.`
    );
  }

  if (sentences.length < 2 && themes.length > 0) {
    sentences.push(
      `${book.title} matches themes that show up in your completed books, including ${sentenceJoin(themes)}.`
    );
  }

  if (sentences.length < 2 && authors.length > 0) {
    sentences.push(
      `It is also connected to authors you've enjoyed, including ${sentenceJoin(authors)}.`
    );
  }

  if (sentences.length === 0 && signals.length > 0) {
    sentences.push(
      `${book.title} appears to be the strongest match from your current library, though related books are not available yet.`
    );
  }

  if (sentences.length === 0) {
    return recommendationFallbackExplanation(item);
  }

  return sentences.slice(0, 3).join(" ");
}
