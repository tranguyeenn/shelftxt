import { describe, expect, it } from "vitest";
import { renderToStaticMarkup } from "react-dom/server";
import { readFileSync } from "node:fs";

import {
  DiscoverSections,
  NEWLY_FOUND_CATEGORY_OPTIONS,
  applyExternalRefreshResult,
  explicitRecommendationSections,
  mergeLoadedDiscoverSections
} from "@/pages/RankingPage";
import type {
  RecommendationSection,
  RecommendationSectionItem,
  RecommendationSectionsResponse
} from "@/lib/types";

function item(title: string, source: "library" | "nyt" | "hardcover" = "library"): RecommendationSectionItem {
  const external = source !== "library";
  return {
    recommendation_id: title.toLowerCase().replaceAll(" ", "-"),
    work_id: title.toLowerCase().replaceAll(" ", "-"),
    canonical_identity: title.toLowerCase().replaceAll(" ", "-"),
    canonical_title: title,
    canonical_author: "Test Author",
    book_id: external ? null : `book-${title}`,
    cover_url: null,
    publication_year: 2026,
    first_publish_year: 2026,
    page_count: 320,
    total_pages: 320,
    score: 0.9,
    final_score: 0.9,
    match_label: external ? "New discovery" : "Strong match",
    qualitative_match_label: external ? "New discovery" : "Strong match",
    genres: external ? ["Fiction"] : ["Romance"],
    traits: [],
    explanation: {
      primary_reason: external ? "Popular this week." : "Specific shelf reason.",
      related_books: [],
      shared_genres: [],
      shared_traits: [],
      style: "balanced"
    },
    reader_explanation: external ? "Popular this week." : "Specific shelf reason.",
    library_state: {
      in_library: !external,
      status: external ? null : "to-read",
      selected_edition_id: external ? null : `book-${title}`
    },
    in_library: !external,
    is_in_library: !external,
    source,
    external_discovery: external,
    provider: external ? source : null,
    discovery_label: external ? "Popular This Week" : null,
    broad_genre: source === "nyt" ? "Hardcover fiction" : null,
    nyt_rank: source === "nyt" ? 3 : null,
    nyt_weeks_on_list: source === "nyt" ? 4 : null,
    description: source === "hardcover" ? "A concise external book description." : null
  } as RecommendationSectionItem;
}

function legacySection(title: string): RecommendationSection {
  return {
    id: "for_you",
    type: "for_you",
    title: "For You",
    source_book: null,
    items: [item(title)]
  };
}

function response(
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

describe("explicit Discover sections", () => {
  it("renders shelf titles from the split shelf_recommendations array before legacy sections", () => {
    const sections = explicitRecommendationSections(response({
      shelf_recommendations: [item("Bride")],
      sections: [legacySection("The Handmaid's Tale")]
    }));

    expect(sections[0]?.items.map((entry) => entry.canonical_title)).toEqual(["Bride"]);
    expect(
      sections.flatMap((section) => section.items.map((entry) => entry.canonical_title))
    ).not.toContain("The Handmaid's Tale");
  });

  it("treats an empty split shelf_recommendations array as authoritative", () => {
    const sections = explicitRecommendationSections(response({
      shelf_recommendations: [],
      sections: [legacySection("The Handmaid's Tale")]
    }));

    expect(sections[0]?.items).toEqual([]);
  });

  it("renders external discovery arrays in their own sections", () => {
    const sections = explicitRecommendationSections(response({
      popular_this_week: [item("Popular NYT Book", "nyt")],
      newly_found: [item("New Hardcover Book", "hardcover")]
    }));

    expect(sections.map((section) => section.title)).toEqual([
      "From Your Shelf",
      "Popular This Week",
      "Newly Found"
    ]);
    expect(sections[1]?.items[0]?.canonical_title).toBe("Popular NYT Book");
    expect(sections[2]?.items[0]?.canonical_title).toBe("New Hardcover Book");
  });

  it("renders five Newly Found cards from an initial split response", () => {
    const sections = explicitRecommendationSections(response({
      newly_found: [
        item("Discovery One", "hardcover"),
        item("Discovery Two", "hardcover"),
        item("Discovery Three", "hardcover"),
        item("Discovery Four", "hardcover"),
        item("Discovery Five", "hardcover")
      ]
    }));

    expect(sections[2]?.items.map((entry) => entry.canonical_title)).toEqual([
      "Discovery One",
      "Discovery Two",
      "Discovery Three",
      "Discovery Four",
      "Discovery Five"
    ]);
  });

  it("rejects non-v3 split discovery responses", () => {
    expect(() =>
      explicitRecommendationSections({
        ...response(),
        schema_version: 2
      } as unknown as RecommendationSectionsResponse)
    ).toThrow("Recommendation response is stale");
  });
});

describe("Discover section rendering", () => {
  function renderSections(sections: RecommendationSection[]) {
    return renderToStaticMarkup(
      <DiscoverSections sections={sections} loading={false} onNotInterested={async () => undefined} />
    );
  }

  it("renders the three split arrays into separate visible sections", () => {
    const html = renderSections(explicitRecommendationSections(response({
      shelf_recommendations: [item("Shelf Only")],
      popular_this_week: [item("Popular Only", "nyt")],
      newly_found: [item("Discovery Only", "hardcover")],
      sections: [legacySection("Legacy Only")]
    })));

    expect(html).toContain("From Your Shelf");
    expect(html).toContain("Books you already own that fit your reading history.");
    expect(html).toContain("Shelf Only");
    expect(html).toContain("Shelf");
    expect(html).toContain("Popular This Week");
    expect(html).toContain("Books appearing on current bestseller lists.");
    expect(html).toContain("Popular Only");
    expect(html).toContain("Bestseller list");
    expect(html).toContain("#3");
    expect(html).toContain("4 weeks on list");
    expect(html).toContain("Newly Found");
    expect(html).toContain("Recent books discovered outside your library.");
    expect(html).toContain("Discovery Only");
    expect(html).toContain("Hardcover");
    expect(html).toContain("Published in 2026");
    expect(html).toContain("A concise external book description.");
    expect(html).not.toContain("New on Hardcover");
    expect(html).not.toContain("Legacy Only");
  });

  it("does not render personalized match copy on popularity cards", () => {
    const sections = explicitRecommendationSections(response({
      popular_this_week: [
        {
          ...item("Popular No Match", "nyt"),
          match_label: "87% match",
          qualitative_match_label: "Strong match",
          reader_explanation: "Because you liked a similar book.",
          explanation: {
            primary_reason: "Because you liked a similar book.",
            related_books: [],
            shared_genres: [],
            shared_traits: [],
            style: "balanced"
          }
        }
      ]
    }));

    const html = renderSections(sections);

    expect(html).toContain("Popular No Match");
    expect(html).toContain("Bestseller list");
    expect(html).not.toContain("87% match");
    expect(html).not.toContain("Strong match");
    expect(html).not.toContain("Because you liked a similar book.");
  });

  it("keeps other sections visible when one provider section is empty", () => {
    const html = renderSections(explicitRecommendationSections(response({
      shelf_recommendations: [item("Available Shelf")],
      popular_this_week: [],
      newly_found: [item("Available Discovery", "hardcover")],
      provider_status: {
        nyt: { available: false, error: "provider unavailable" },
        hardcover: { available: true }
      }
    })));

    expect(html).toContain("Available Shelf");
    expect(html).toContain("Popular books are unavailable right now.");
    expect(html).toContain("Available Discovery");
  });

  it("renders section-specific empty states", () => {
    const html = renderSections(explicitRecommendationSections(response()));

    expect(html).toContain("No unread shelf books are ready to recommend yet.");
    expect(html).toContain("Popular books are unavailable right now.");
    expect(html).toContain("No recent discoveries are available right now.");
  });

  it("does not render currently reading books from From Your Shelf", () => {
    const html = renderSections(explicitRecommendationSections(response({
      shelf_recommendations: [
        item("Unread Shelf"),
        {
          ...item("Reading Shelf"),
          library_state: {
            in_library: true,
            status: "reading",
            selected_edition_id: "book-reading"
          }
        }
      ]
    })));

    expect(html).toContain("Unread Shelf");
    expect(html).not.toContain("Reading Shelf");
  });

  it("renders replace and section refresh controls for external cards", () => {
    const html = renderSections(explicitRecommendationSections(response({
      popular_this_week: [item("Popular Replace", "nyt")],
      newly_found: [item("Discovery Replace", "hardcover")]
    })));

    expect(html).toContain('aria-label="Refresh Popular This Week"');
    expect(html).toContain('aria-label="Refresh Newly Found"');
    expect(html).toContain('aria-label="Replace Popular Replace"');
    expect(html).toContain('aria-label="Replace Discovery Replace"');
    expect(html).toContain('aria-haspopup="menu"');
  });

  it("uses romance as the Newly Found Romance category value", () => {
    expect(NEWLY_FOUND_CATEGORY_OPTIONS).toContainEqual(["romance", "Romance"]);
  });

  it("posts Newly Found replacement requests with the selected category", () => {
    const source = readFileSync(new URL("./RankingPage.tsx", import.meta.url), "utf8");

    expect(source).toContain('"/recommendations/newly-found/replace"');
    expect(source).toContain("category");
    expect(source).toContain("onReplace={(category) => onReplaceExternal(\"newly_found\", item, category)}");
  });

  it("shows loading and no-match state only for the selected external card", () => {
    const sections = explicitRecommendationSections(response({
      popular_this_week: [item("Popular Loading", "nyt"), item("Popular Stable", "nyt")],
      newly_found: [item("Discovery Stable", "hardcover")]
    }));
    const html = renderToStaticMarkup(
      <DiscoverSections
        sections={sections}
        loading={false}
        loadingExternal={{ section: "popular_this_week", id: "popular-loading" }}
        noMatchMessages={{ "popular-loading": "No more books match that category right now." }}
        onNotInterested={async () => undefined}
      />
    );

    expect(html).toContain("Popular Loading");
    expect(html).toContain("Popular Stable");
    expect(html).toContain("Replacing...");
    expect(html).toContain("No more books match that category right now.");
  });

  it("renders exactly one section refresh control for an empty Newly Found section", () => {
    const html = renderSections(explicitRecommendationSections(response()));

    expect(html).not.toContain("Try another category");
    expect(html.match(/aria-label="Refresh Newly Found"/g)).toHaveLength(1);
    expect(html).toContain("No recent discoveries are available right now.");
    expect(html).toContain("No unread shelf books are ready to recommend yet.");
  });

  it("does not show the Newly Found empty state when a populated response is rendered", () => {
    const html = renderSections(explicitRecommendationSections(response({
      newly_found: [
        item("Discovery One", "hardcover"),
        item("Discovery Two", "hardcover"),
        item("Discovery Three", "hardcover"),
        item("Discovery Four", "hardcover"),
        item("Discovery Five", "hardcover")
      ]
    })));

    expect(html).toContain("Discovery Five");
    expect(html).not.toContain("No recent discoveries are available right now.");
  });

  it("preserves populated Newly Found items when a later stale load is empty", () => {
    const populated = explicitRecommendationSections(response({
      newly_found: [
        item("Discovery One", "hardcover"),
        item("Discovery Two", "hardcover"),
        item("Discovery Three", "hardcover"),
        item("Discovery Four", "hardcover"),
        item("Discovery Five", "hardcover")
      ]
    }));
    const staleEmpty = explicitRecommendationSections(response());

    const merged = mergeLoadedDiscoverSections(populated, staleEmpty);

    expect(merged.find((section) => section.type === "newly_found")?.items).toHaveLength(5);
    expect(merged.find((section) => section.type === "newly_found")?.items[0]?.canonical_title).toBe("Discovery One");
  });

  it("allows the initial empty Newly Found state when no cards have loaded yet", () => {
    const merged = mergeLoadedDiscoverSections([], explicitRecommendationSections(response()));

    expect(merged.find((section) => section.type === "newly_found")?.items).toHaveLength(0);
  });

  it("keeps current Newly Found cards when refresh returns no replacement items", () => {
    const populated = explicitRecommendationSections(response({
      newly_found: [item("Discovery Stable", "hardcover")]
    }));

    const next = applyExternalRefreshResult(populated, "newly_found", []);

    expect(next.find((section) => section.type === "newly_found")?.items[0]?.canonical_title).toBe("Discovery Stable");
  });

  it("keeps personalized match scores absent from external cards with controls", () => {
    const sections = explicitRecommendationSections(response({
      popular_this_week: [
        {
          ...item("Popular Controlled", "nyt"),
          match_label: "99% match",
          qualitative_match_label: "Strong match",
          reader_explanation: "Because you liked a similar book.",
          explanation: {
            primary_reason: "Because you liked a similar book.",
            related_books: [],
            shared_genres: [],
            shared_traits: [],
            style: "balanced"
          }
        }
      ],
      newly_found: [
        {
          ...item("Discovery Controlled", "hardcover"),
          match_label: "88% match",
          qualitative_match_label: "Good match"
        }
      ]
    }));

    const html = renderSections(sections);

    expect(html).toContain("Popular Controlled");
    expect(html).toContain("Discovery Controlled");
    expect(html).not.toContain("99% match");
    expect(html).not.toContain("88% match");
    expect(html).not.toContain("Because you liked a similar book.");
  });
});
