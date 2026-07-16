import { describe, expect, it } from "vitest";

import {
  getClusterDisplayTitle,
  getRecommendationDisplayExplanation,
  getRecommendationMatchLabel,
  normalizeRecommendationCluster,
  visibleRecommendationTags
} from "@/lib/recommendationNormalization";
import type { RecommendationCluster } from "@/lib/types";

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
          "Because you enjoyed The Hunger Games and The Maze Runner, this explores similar themes of survival, control, and resistance."
      },
      genres: ["fiction", "dystopian"],
      traits: ["general", "resistance"]
    }
  ]
} as unknown as RecommendationCluster;

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
      "Because you enjoyed The Hunger Games and The Maze Runner, this explores similar themes of survival, control, and resistance."
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
});
