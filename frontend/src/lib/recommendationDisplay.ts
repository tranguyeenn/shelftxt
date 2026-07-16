import type { RecommendationItem } from "@/lib/types";

export type RecommendationReason = {
  label: string;
  detail: string;
};

export function recommendationMatchLabel(score: number): string {
  const normalized = Math.min(1, Math.max(0, Number.isFinite(score) ? score : 0));
  if (normalized >= 0.85) return "Strong match";
  if (normalized >= 0.65) return "Good match";
  if (normalized >= 0.4) return "Possible match";
  return "Exploratory match";
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
  return "This is the strongest available match from your current library. Add ratings or related books for a clearer explanation.";
}

export function readerFacingExplanation(item: RecommendationItem): string {
  return recommendationFallbackExplanation(item);
}
