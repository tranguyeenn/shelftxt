import { recommendationMatchLabel } from "@/lib/recommendationDisplay";
import type {
  RecommendationCluster,
  RecommendationSection,
  RecommendationSectionItem
} from "@/lib/types";

const GENERIC_RECOMMENDATION_TAGS = new Set([
  "fiction",
  "drama",
  "novel",
  "literature",
  "young adult",
  "children's fiction",
  "childrens fiction",
  "juvenile fiction",
  "new york times bestseller",
  "bestseller",
  "schools",
  "school",
  "general",
  "contemporary",
  "romance",
  "fantasy"
]);

const GENERIC_EXPLANATION_FALLBACK =
  "This is the strongest available match from your current library. Add ratings or related books for a clearer explanation.";

type RecommendationExplanation =
  | string
  | {
      primary_reason?: string | null;
      related_books?: RecommendationSectionItem["explanation"]["related_books"];
      shared_genres?: string[];
      shared_traits?: string[];
      style?: string;
    }
  | null
  | undefined;

type RecommendationInput = Partial<Omit<RecommendationSectionItem, "explanation">> & {
  title?: string;
  author?: string;
  explanation?: RecommendationExplanation;
  reason?: string | null;
  reader_explanation?: string | null;
  match_percentage?: number | null;
};

export function getClusterDisplayTitle(section: Pick<RecommendationSection, "reading_identity" | "title">): string {
  return cleanText(section.reading_identity) || cleanText(section.title) || "Recommended for you";
}

export function getRecommendationDisplayExplanation(
  recommendation: Pick<RecommendationSectionItem, "reader_explanation" | "explanation">
): string {
  return (
    cleanText(recommendation.reader_explanation) ||
    cleanText(recommendation.explanation?.primary_reason) ||
    GENERIC_EXPLANATION_FALLBACK
  );
}

export function getRecommendationMatchLabel(
  recommendation: Pick<RecommendationSectionItem, "qualitative_match_label" | "match_label" | "final_score" | "score">
): string {
  return (
    cleanText(recommendation.qualitative_match_label) ||
    cleanText(recommendation.match_label) ||
    recommendationMatchLabel(Number(recommendation.final_score ?? recommendation.score ?? 0))
  );
}

export function visibleRecommendationTags(tags: string[]): string[] {
  const seen = new Set<string>();
  return tags.filter((tag) => {
    const key = tag.trim().toLowerCase();
    if (!key || seen.has(key) || GENERIC_RECOMMENDATION_TAGS.has(key)) return false;
    seen.add(key);
    return true;
  });
}

export function normalizeRecommendationCluster(cluster: RecommendationCluster): RecommendationSection {
  const title = cleanText(cluster.title) || "Recommended for you";
  return {
    ...cluster,
    id: `cluster-${cluster.cluster_id}`,
    type: "cluster",
    title,
    reading_identity: cleanText(cluster.reading_identity) || title,
    source_book: null,
    why: cleanText(cluster.why) || undefined,
    anchors: Array.isArray(cluster.anchors) ? cluster.anchors : [],
    dominant_genres: Array.isArray(cluster.dominant_genres) ? cluster.dominant_genres : [],
    dominant_themes: Array.isArray(cluster.dominant_themes) ? cluster.dominant_themes : [],
    items: Array.isArray(cluster.recommendations)
      ? cluster.recommendations.map((recommendation) => ({
          ...normalizeRecommendationItem(recommendation),
          cluster_id: cluster.cluster_id
        }))
      : []
  };
}

export function normalizeRecommendationItem(recommendation: RecommendationInput): RecommendationSectionItem {
  const canonicalTitle = cleanText(recommendation.canonical_title) || cleanText(recommendation.title) || "Untitled";
  const canonicalAuthor = cleanText(recommendation.canonical_author) || cleanText(recommendation.author) || "Unknown author";
  const workId =
    cleanText(recommendation.work_id) ||
    cleanText(recommendation.recommendation_id) ||
    recommendationTitleAuthorIdentity(canonicalTitle, canonicalAuthor);
  const source = sectionItemSource(recommendation);
  const inLibrary = source === "library";
  const readerExplanation = readerExplanationFrom(recommendation);
  const normalized: RecommendationSectionItem = {
    ...recommendation,
    work_id: workId,
    canonical_title: canonicalTitle,
    canonical_author: canonicalAuthor,
    book_id: inLibrary ? recommendation.book_id ?? null : null,
    canonical_identity: recommendation.canonical_identity ?? recommendation.recommendation_id ?? workId,
    match_label:
      cleanText(recommendation.qualitative_match_label) ||
      cleanText(recommendation.match_label) ||
      recommendationMatchLabel(Number(recommendation.final_score ?? recommendation.score ?? 0)),
    qualitative_match_label:
      cleanText(recommendation.qualitative_match_label) ||
      cleanText(recommendation.match_label) ||
      recommendationMatchLabel(Number(recommendation.final_score ?? recommendation.score ?? 0)),
    display_title: recommendation.display_title ?? canonicalTitle,
    original_title: recommendation.original_title ?? null,
    genres: Array.isArray(recommendation.genres) ? recommendation.genres : [],
    traits: Array.isArray(recommendation.traits) ? recommendation.traits : [],
    explanation: normalizeExplanation(recommendation.explanation, readerExplanation),
    reader_explanation: readerExplanation,
    library_state: {
      ...recommendation.library_state,
      in_library: inLibrary,
      status: recommendation.library_state?.status ?? null,
      selected_edition_id: inLibrary ? recommendation.library_state?.selected_edition_id ?? null : null
    },
    in_library: inLibrary,
    is_in_library: inLibrary,
    source,
    external_discovery: source === "external" ? true : recommendation.external_discovery,
    discovery_query: recommendation.discovery_query ?? null,
    discovery_cluster_id: recommendation.discovery_cluster_id ?? recommendation.cluster_id ?? null,
    exploration_mode: recommendation.exploration_mode ?? null,
    exploration_source: recommendation.exploration_source ?? null,
    novelty_score: recommendation.novelty_score ?? null,
    provider_rank: recommendation.provider_rank ?? null,
    score_breakdown: recommendation.score_breakdown ?? {},
    diagnostics: recommendation.diagnostics ?? {}
  };
  normalized.match_label = getRecommendationMatchLabel(normalized);
  normalized.qualitative_match_label = normalized.match_label;
  return normalized;
}

function readerExplanationFrom(recommendation: RecommendationInput): string {
  return (
    cleanText(recommendation.reader_explanation) ||
    cleanText(
      typeof recommendation.explanation === "string"
        ? recommendation.explanation
        : recommendation.explanation?.primary_reason
    ) ||
    cleanText(recommendation.reason) ||
    GENERIC_EXPLANATION_FALLBACK
  );
}

function normalizeExplanation(
  explanation: RecommendationExplanation,
  readerExplanation: string
): RecommendationSectionItem["explanation"] {
  if (typeof explanation === "object" && explanation !== null) {
    return {
      primary_reason: cleanText(explanation.primary_reason) || readerExplanation,
      related_books: Array.isArray(explanation.related_books) ? explanation.related_books : [],
      shared_genres: Array.isArray(explanation.shared_genres) ? explanation.shared_genres : [],
      shared_traits: Array.isArray(explanation.shared_traits) ? explanation.shared_traits : [],
      style: cleanText(explanation.style) || "balanced"
    };
  }
  return {
    primary_reason: readerExplanation,
    related_books: [],
    shared_genres: [],
    shared_traits: [],
    style: "balanced"
  };
}

function sectionItemSource(item: RecommendationInput): "library" | "external" {
  if (item.source === "external" || item.external_discovery === true || item.library_state?.in_library === false) {
    return "external";
  }
  if (item.source === "library" || item.library_state?.in_library === true || item.is_in_library === true || item.in_library === true) {
    return "library";
  }
  return "external";
}

function recommendationTitleAuthorIdentity(title: string, author: string): string {
  const normalize = (value: string) =>
    value.toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-+|-+$/g, "");
  return `title_author:${normalize(title)}:${normalize(author.split(",", 1)[0] ?? "")}`;
}

function cleanText(value: unknown): string {
  return typeof value === "string" ? value.trim() : "";
}
