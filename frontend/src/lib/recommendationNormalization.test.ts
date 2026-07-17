import { describe, expect, it } from "vitest";

import {
  getClusterDisplayTitle,
  getRecommendationDisplayExplanation,
  getRecommendationMatchLabel,
  normalizeRecommendationItem,
  normalizeRecommendationCluster,
  publicRecommendationProvider,
  splitRecommendationSections,
  visibleRecommendationTags
} from "@/lib/recommendationNormalization";
import type { RecommendationCluster, RecommendationSectionItem, RecommendationSectionsResponse } from "@/lib/types";

const mockedCluster = {
  cluster_id: "dystopian",
  title: "Survival competitions and dystopian rebellion",
  reading_identity: "Survival competitions and dystopian rebellion",
  why: "Because you enjoy survival-focused dystopian stories.",
  anchors: [],
  dominant_genres: ["fiction", "dystopian"],
  dominant_themes: ["general", "resistance"],
  cluster_size: 2,
  recommendations: [
    {
      title: "Example Book",
      qualitative_match_label: "Strong match",
      match_label: "Strong match",
      match_percentage: 86,
      final_score: 0.86,
      explanation: {
        primary_reason:
          "Because you enjoyed The Hunger Games and The Maze Runner, this shares survival competitions, state control, and resistance."
      },
      genres: ["fiction", "dystopian"],
      traits: ["general", "resistance"]
    }
  ]
} as unknown as RecommendationCluster;

function splitItem(
  title: string,
  source: "library" | "nyt" | "hardcover" = "library",
  status: RecommendationSectionItem["library_state"]["status"] = source === "library" ? "not_started" : null
): RecommendationSectionItem {
  const external = source !== "library";
  return {
    recommendation_id: title.toLowerCase().replaceAll(" ", "-"),
    work_id: title.toLowerCase().replaceAll(" ", "-"),
    canonical_identity: title.toLowerCase().replaceAll(" ", "-"),
    canonical_title: title,
    canonical_author: "Test Author",
    book_id: external ? null : `book-${title}`,
    cover_url: null,
    score: 0.9,
    final_score: 0.9,
    match_label: external ? "New discovery" : "Strong match",
    qualitative_match_label: external ? "New discovery" : "Strong match",
    genres: [],
    traits: [],
    explanation: {
      primary_reason: external ? "External metadata." : "Specific shelf reason.",
      related_books: [],
      shared_genres: [],
      shared_traits: [],
      style: "balanced"
    },
    reader_explanation: external ? "External metadata." : "Specific shelf reason.",
    library_state: {
      in_library: !external,
      status,
      selected_edition_id: external ? null : `book-${title}`
    },
    in_library: !external,
    is_in_library: !external,
    source,
    external_discovery: external,
    provider: external ? source : null
  };
}

function splitResponse(
  overrides: Partial<RecommendationSectionsResponse> = {}
): RecommendationSectionsResponse {
  return {
    schema_version: 3,
    sections: [],
    shelf_recommendations: [],
    popular_this_week: [],
    newly_found: [],
    provider_status: {},
    generated_at: "2026-07-16T00:00:00Z",
    style: "balanced",
    ...overrides
  };
}

describe("recommendation normalization", () => {
  it("keeps reading_identity as the cluster display title", () => {
    const section = normalizeRecommendationCluster({
      ...mockedCluster,
      title: "Because you enjoyed Fiction",
      reading_identity: "Survival competitions and dystopian rebellion"
    });

    expect(section.title).toBe("Because you enjoyed Fiction");
    expect(section.reading_identity).toBe("Survival competitions and dystopian rebellion");
    expect(getClusterDisplayTitle(section)).toBe("Survival competitions and dystopian rebellion");
  });

  it("normalizes explanation.primary_reason into reader_explanation", () => {
    const section = normalizeRecommendationCluster(mockedCluster);
    const recommendation = section.items[0];

    expect(recommendation.reader_explanation).toBe(
      "Because you enjoyed The Hunger Games and The Maze Runner, this shares survival competitions, state control, and resistance."
    );
    expect(recommendation.explanation.primary_reason).toBe(recommendation.reader_explanation);
    expect(getRecommendationDisplayExplanation(recommendation)).toBe(recommendation.reader_explanation);
  });

  it("uses qualitative_match_label before numeric match percentage", () => {
    const section = normalizeRecommendationCluster(mockedCluster);
    const recommendation = section.items[0];

    expect(getRecommendationMatchLabel(recommendation)).toBe("Strong match");
    expect(getRecommendationMatchLabel(recommendation)).not.toContain("% match");
  });

  it("removes generic tags from visible chips", () => {
    expect(visibleRecommendationTags(["fiction", "general", "dystopian", "resistance"])).toEqual([
      "dystopian",
      "resistance"
    ]);
  });

  it("does not produce legacy percentage or Shares text in display output", () => {
    const section = normalizeRecommendationCluster(mockedCluster);
    const recommendation = section.items[0];
    const renderedText = [
      getClusterDisplayTitle(section),
      section.why,
      getRecommendationMatchLabel(recommendation),
      getRecommendationDisplayExplanation(recommendation),
      ...visibleRecommendationTags([...recommendation.genres, ...recommendation.traits])
    ].join(" ");

    expect(renderedText).not.toContain("% match");
    expect(renderedText).not.toContain("Shares ");
  });

  it("accepts public Hardcover metadata on external recommendations without personalized match labels", () => {
    const recommendation = normalizeRecommendationItem({
      recommendation_id: "work:hardcover:book:42",
      work_id: "hardcover:book:42",
      canonical_title: "Enriched Hardcover Pick",
      canonical_author: "A. Writer",
      source: "external",
      external_discovery: true,
      discovery_source: "hardcover",
      provider: "hardcover",
      cover_url: "https://img.example/book.jpg",
      publication_year: 2024,
      page_count: 321,
      publisher: "Test Publisher",
      source_url: "https://hardcover.app/books/enriched",
      ratings_count: 1200,
      reader_likelihood_score: 0.74,
      series_name: "Example Series",
      series_position: 2,
      score: 0.82,
      match_label: "Strong match",
      explanation: { primary_reason: "A strong external match." },
      genres: ["mystery"],
      traits: []
    });

    expect(recommendation.library_state.in_library).toBe(false);
    expect(recommendation.book_id).toBeNull();
    expect(recommendation.provider).toBe("hardcover");
    expect(recommendation.cover_url).toBe("https://img.example/book.jpg");
    expect(recommendation.publication_year).toBe(2024);
    expect(recommendation.page_count).toBe(321);
    expect(recommendation.series_name).toBe("Example Series");
    expect(recommendation.ratings_count).toBe(1200);
    expect(recommendation.reader_likelihood_score).toBe(0.74);
    expect(getRecommendationMatchLabel(recommendation)).toBe("New discovery");
  });

  it("normalizes internal fixture provenance to a public provider", () => {
    const recommendation = normalizeRecommendationItem({
      canonical_title: "Seeded External Pick",
      canonical_author: "A. Writer",
      source: "external",
      external_discovery: true,
      discovery_source: "seeded_fixture",
      provider: "seeded_fixture",
      score: 0.7,
      match_label: "Strong match",
      explanation: { primary_reason: "A strong external match." },
      genres: [],
      traits: []
    });

    expect(recommendation.discovery_source).toBe("seeded_fixture");
    expect(recommendation.provider).toBe("open_library");
    expect(publicRecommendationProvider("seeded_fixture")).toBe("open_library");
  });

  it("does not display vague related-themes explanations as finished copy", () => {
    const recommendation = normalizeRecommendationItem({
      canonical_title: "Weak Explanation",
      canonical_author: "A. Writer",
      score: 0.5,
      match_label: "Possible match",
      explanation: { primary_reason: "This recommendation follows similar themes of related themes." },
      genres: [],
      traits: []
    });

    expect(recommendation.reader_explanation).toBe(
      "Selected from your unread shelf based on your reading history."
    );
    expect(getRecommendationDisplayExplanation(recommendation)).not.toContain("related themes");
  });

  it("keeps backend match labels for continuity recommendations", () => {
    const recommendation = normalizeRecommendationItem({
      canonical_title: "Series Sequel",
      canonical_author: "A. Writer",
      score: 0.36,
      reader_likelihood_score: 0.61,
      match_label: "Strong match",
      qualitative_match_label: "Strong match",
      explanation: { primary_reason: "Because you continued Example Series." },
      genres: ["fantasy"],
      traits: []
    });

    expect(getRecommendationMatchLabel(recommendation)).toBe("Strong match");
  });

  it("requires split discovery schema v3", () => {
    expect(() =>
      splitRecommendationSections({
        ...splitResponse(),
        schema_version: 2
      } as unknown as RecommendationSectionsResponse)
    ).toThrow("Recommendation response is stale");
  });

  it("splits only the explicit v3 arrays and ignores legacy sections", () => {
    const sections = splitRecommendationSections(splitResponse({
      sections: [
        {
          id: "legacy",
          type: "for_you",
          title: "Legacy",
          source_book: null,
          items: [splitItem("Legacy Shelf Book")]
        }
      ],
      shelf_recommendations: [splitItem("Shelf Book")],
      popular_this_week: [splitItem("Popular Book", "nyt")],
      newly_found: [splitItem("New Discovery", "hardcover")]
    }));

    expect(sections.map((section) => section.items.map((item) => item.canonical_title))).toEqual([
      ["Shelf Book"],
      ["Popular Book"],
      ["New Discovery"]
    ]);
    expect(sections.flatMap((section) => section.items)).not.toContainEqual(
      expect.objectContaining({ canonical_title: "Legacy Shelf Book" })
    );
  });

  it("filters active or finished shelf books from From Your Shelf", () => {
    const sections = splitRecommendationSections(splitResponse({
      shelf_recommendations: [
        splitItem("Unread Shelf Book", "library", "not_started"),
        splitItem("Currently Reading Shelf Book", "library", "reading"),
        splitItem("Completed Shelf Book", "library", "completed"),
        splitItem("DNF Shelf Book", "library", "dnf")
      ]
    }));

    expect(sections[0]?.items.map((item) => item.canonical_title)).toEqual(["Unread Shelf Book"]);
  });
});
