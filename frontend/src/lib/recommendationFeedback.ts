import { fetchJson } from "@/lib/api";
import type { RecommendationItem, RecommendationSectionItem } from "@/lib/types";

export type RecommendationFeedbackResponse = {
  feedback: {
    id: number;
    recommendation_id: string;
    recommendation_identity: string;
    feedback_type: string;
    expires_at: string | null;
  };
  status: string;
  removed_recommendation_id: string;
  should_hide: boolean;
  replacement: RecommendationItem | null;
  recommendations: RecommendationItem[];
  recommendation_count: number;
};

export function stableRecommendationId(item: RecommendationItem): string {
  const book = item.recommended_book ?? item.book;
  return String(
    item.recommendation_id
    ?? item.work_id
    ?? book.work_id
    ?? item.isbn
    ?? book.isbn
    ?? book.id
    ?? recommendationTitleAuthorIdentity(book.title, book.author)
  );
}

function recommendationTitleAuthorIdentity(title: string, author: string): string {
  return `title_author:${normalizeIdentityPart(title)}:${normalizeIdentityPart(author.split(",", 1)[0] ?? "")}`;
}

function normalizeIdentityPart(value: string): string {
  return value.toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-+|-+$/g, "");
}

export async function submitRecommendationFeedback(
  item: RecommendationItem,
  feedbackType = "not_interested",
  currentRecommendationIds: string[] = [],
  style = "balanced"
) {
  const book = item.recommended_book ?? item.book;
  return fetchJson<RecommendationFeedbackResponse>("/recommendations/feedback", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      canonical_identity: item.recommendation_id ?? item.work_id ?? book.work_id ?? item.isbn ?? book.isbn ?? null,
      recommendation_id: stableRecommendationId(item),
      action: feedbackType,
      feedback_type: feedbackType,
      current_recommendation_ids: currentRecommendationIds,
      style,
      book_id: item.book_id ?? book.book_id ?? null,
      work_id: item.work_id ?? book.work_id ?? null,
      isbn: item.isbn ?? book.isbn ?? null,
      title: book.title,
      author: book.author,
      source: item.source ?? (item.in_library === false || item.is_in_library === false ? "external" : "library"),
      genres: item.matched_genres ?? book.genres ?? [],
      authors: item.matched_authors ?? [],
      related_books: item.related_books ?? item.matched_liked_books ?? [],
      recommendation_score: item.score,
      explanation: item.reason ?? item.explanation,
      inferred_trends: item.score_breakdown ?? {}
    })
  });
}

export async function submitSectionRecommendationFeedback(
  item: RecommendationSectionItem,
  feedbackType = "not_interested",
  currentRecommendationIds: string[] = [],
  style = "balanced"
) {
  return fetchJson<RecommendationFeedbackResponse>("/recommendations/feedback", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      canonical_identity: item.canonical_identity ?? item.recommendation_id ?? item.work_id,
      recommendation_id: item.recommendation_id ?? item.work_id,
      action: feedbackType,
      feedback_type: feedbackType,
      current_recommendation_ids: currentRecommendationIds,
      style,
      work_id: item.work_id,
      title: item.canonical_title,
      author: item.canonical_author,
      source: item.source ?? (item.library_state.in_library ? "library" : "external"),
      cluster_id: item.cluster_id,
      genres: item.genres,
      authors: [item.canonical_author],
      related_books: item.explanation.related_books,
      recommendation_score: item.score,
      explanation: item.explanation.primary_reason,
      inferred_trends: {
        shared_genres: item.explanation.shared_genres,
        shared_traits: item.explanation.shared_traits,
        style: item.explanation.style
      }
    })
  });
}
