import { useCallback, useEffect, useRef, useState, type FormEvent, type KeyboardEvent } from "react";

import { PageHeader } from "@/components/layout/PageHeader";
import { BookCover } from "@/components/ui/BookCover";
import { Button } from "@/components/ui/Button";
import { Card } from "@/components/ui/Card";
import { EmptyState } from "@/components/ui/EmptyState";
import { useUserSettings } from "@/contexts/UserSettingsContext";
import { fetchJson } from "@/lib/api";
import { submitSectionRecommendationFeedback } from "@/lib/recommendationFeedback";
import { recommendationMatchLabel } from "@/lib/recommendationDisplay";
import {
  getRecommendationDisplayExplanation,
  getRecommendationMatchLabel,
  normalizeRecommendationItem,
  publicRecommendationProvider,
  splitRecommendationSections
} from "@/lib/recommendationNormalization";
import { recommendationSectionsQuery, type RecommendationFilters } from "@/lib/userSettings";
import type {
  RecommendationFacet,
  RecommendationFacetResponse,
  ExternalSectionReplaceResponse,
  NewlyFoundSectionRefreshResponse,
  PopularSectionRefreshResponse,
  RecommendationItem,
  RecommendationSection,
  RecommendationSectionItem,
  RecommendationSectionsResponse
} from "@/lib/types";

type RecommendationTab = "for-you" | "genres" | "authors";
type DiscoverSectionType = "shelf_recommendations" | "popular_this_week" | "newly_found";
type ExternalSectionType = "popular_this_week" | "newly_found";
type LoadingExternalState = { section: ExternalSectionType; id: string } | null;

export const POPULAR_CATEGORY_OPTIONS = [
  ["any", "Any"],
  ["fiction", "Fiction"],
  ["young_adult", "Young Adult"],
  ["romance", "Romance"],
  ["fantasy_scifi", "Fantasy / Sci-Fi"],
  ["mystery_thriller", "Mystery / Thriller"],
  ["manga_graphic", "Manga / Graphic"],
  ["nonfiction", "Nonfiction"]
] as const;

export const NEWLY_FOUND_CATEGORY_OPTIONS = [
  ["any", "Any"],
  ["fiction", "Fiction"],
  ["young_adult", "Young Adult"],
  ["romance", "Romance"],
  ["fantasy_scifi", "Fantasy / Sci-Fi"],
  ["mystery_thriller", "Mystery / Thriller"],
  ["manga_graphic", "Manga / Graphic"],
  ["literary_fiction", "Literary Fiction"],
  ["historical_fiction", "Historical Fiction"]
] as const;

const POPULAR_REFRESH_OPTIONS = [
  ["mixed", "Refresh all"],
  ["mixed", "Mixed"],
  ["fiction_heavy", "Fiction-heavy"],
  ["young_adult", "Young Adult"],
  ["romance", "Romance"],
  ["fantasy_scifi", "Fantasy / Sci-Fi"],
  ["mystery_thriller", "Mystery / Thriller"],
  ["manga_graphic", "Manga / Graphic"]
] as const;

const NEWLY_REFRESH_OPTIONS = [
  ["mixed", "Refresh all"],
  ["mixed", "Mixed"],
  ["fiction", "Fiction"],
  ["young_adult", "Young Adult"],
  ["romance", "Romance"],
  ["fantasy_scifi", "Fantasy / Sci-Fi"],
  ["mystery_thriller", "Mystery / Thriller"],
  ["literary_fiction", "Literary Fiction"],
  ["historical_fiction", "Historical Fiction"]
] as const;

const DISCOVER_SECTION_COPY: Record<DiscoverSectionType, { title: string; description: string; empty: string }> = {
  shelf_recommendations: {
    title: "From Your Shelf",
    description: "Books you already own that fit your reading history.",
    empty: "No unread shelf books are ready to recommend yet."
  },
  popular_this_week: {
    title: "Popular This Week",
    description: "Books appearing on current bestseller lists.",
    empty: "Popular books are unavailable right now."
  },
  newly_found: {
    title: "Newly Found",
    description: "Recent books discovered outside your library.",
    empty: "No recent discoveries are available right now."
  }
};

export function RankingPage() {
  const {
    settings,
    recommendationFilters: appliedFilters,
    setRecommendationFilters: setAppliedFilters
  } = useUserSettings();
  const [sections, setSections] = useState<RecommendationSection[]>([]);
  const [providerStatus, setProviderStatus] = useState<RecommendationSectionsResponse["provider_status"]>();
  const [skippedExternalIds, setSkippedExternalIds] = useState<Record<ExternalSectionType, string[]>>({
    popular_this_week: [],
    newly_found: []
  });
  const [loadingExternal, setLoadingExternal] = useState<LoadingExternalState>(null);
  const [noMatchMessages, setNoMatchMessages] = useState<Record<string, string>>({});
  const [sectionPreferences, setSectionPreferences] = useState<Record<ExternalSectionType, string>>({
    popular_this_week: "mixed",
    newly_found: "mixed"
  });
  const [genreFacets, setGenreFacets] = useState<RecommendationFacet[]>([]);
  const [authorFacets, setAuthorFacets] = useState<RecommendationFacet[]>([]);
  const [activeTab, setActiveTab] = useState<RecommendationTab>(() => {
    const saved = window.sessionStorage.getItem("shelftxt.recommendationTab");
    return saved === "genres" || saved === "authors" ? saved : "for-you";
  });
  const [loading, setLoading] = useState(true);
  const [facetsLoading, setFacetsLoading] = useState(false);
  const [error, setError] = useState("");
  const [filterError, setFilterError] = useState("");
  const [feedbackMessage, setFeedbackMessage] = useState("");
  const [genre, setGenre] = useState(appliedFilters.genre ?? "");
  const [minPages, setMinPages] = useState(
    appliedFilters.min_pages === undefined ? "" : String(appliedFilters.min_pages)
  );
  const [maxPages, setMaxPages] = useState(
    appliedFilters.max_pages === undefined ? "" : String(appliedFilters.max_pages)
  );
  const loadRequestId = useRef(0);

  const loadSections = useCallback(async (
    refresh = false,
    excludeIds: string[] = [],
    filters: RecommendationFilters = {}
  ) => {
    const endpoint = recommendationSectionsQuery(settings, refresh, excludeIds, filters);
    const ranked = await fetchJson<RecommendationSectionsResponse>(
      endpoint,
      { skipClientCache: true }
    );
    const responseSections = explicitRecommendationSections(ranked);
    return {
      sections: normalizeRecommendationSections(responseSections),
      providerStatus: ranked.provider_status
    };
  }, [settings.recommendationStyle]);

  const load = useCallback(async (
    refresh = false,
    excludeIds: string[] = [],
    filters: RecommendationFilters = {}
  ) => {
    const requestId = loadRequestId.current + 1;
    loadRequestId.current = requestId;
    setLoading(true);
    setError("");
    try {
      const response = await loadSections(refresh, excludeIds, filters);
      if (requestId !== loadRequestId.current) return;
      setProviderStatus(response.providerStatus);
      setSections((current) => mergeLoadedDiscoverSections(current, response.sections));
    } catch (err) {
      if (requestId !== loadRequestId.current) return;
      setSections((current) => current);
      setError(err instanceof Error ? err.message : "Failed to load recommendations");
    } finally {
      if (requestId === loadRequestId.current) {
        setLoading(false);
      }
    }
  }, [loadSections, settings.recommendationStyle]);

  useEffect(() => {
    void load(false, [], appliedFilters);
  }, [load]);

  useEffect(() => {
    window.sessionStorage.setItem("shelftxt.recommendationTab", activeTab);
    if (activeTab === "genres" && genreFacets.length === 0) {
      setFacetsLoading(true);
      fetchJson<RecommendationFacetResponse>("/recommendations/genres")
        .then((response) => setGenreFacets(Array.isArray(response.items) ? response.items : []))
        .catch((err) => setError(err instanceof Error ? err.message : "Failed to load genre filters"))
        .finally(() => setFacetsLoading(false));
    }
    if (activeTab === "authors" && authorFacets.length === 0) {
      setFacetsLoading(true);
      fetchJson<RecommendationFacetResponse>("/recommendations/authors")
        .then((response) => setAuthorFacets(Array.isArray(response.items) ? response.items : []))
        .catch((err) => setError(err instanceof Error ? err.message : "Failed to load author filters"))
        .finally(() => setFacetsLoading(false));
    }
  }, [activeTab, authorFacets.length, genreFacets.length]);

  function refreshRecommendations() {
    const excludeIds = sections.flatMap((section) => section.items.map((item) => item.work_id)).filter(Boolean);
    void load(true, excludeIds, appliedFilters);
  }

  function externalSectionItems(type: ExternalSectionType): RecommendationSectionItem[] {
    return sections.find((section) => section.type === type)?.items ?? [];
  }

  function externalIds(type: ExternalSectionType): string[] {
    return externalSectionItems(type)
      .map((item) => item.recommendation_id ?? item.canonical_identity ?? item.work_id)
      .filter((value): value is string => Boolean(value));
  }

  async function postExternalJson<T>(path: string, body: Record<string, unknown>): Promise<T> {
    return fetchJson<T>(path, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
      skipClientCache: true
    });
  }

  async function replaceExternalCard(type: ExternalSectionType, item: RecommendationSectionItem, category: string) {
    const itemId = item.recommendation_id ?? item.canonical_identity ?? item.work_id;
    if (!itemId) return;
    setLoadingExternal({ section: type, id: itemId });
    setNoMatchMessages((current) => ({ ...current, [itemId]: "" }));
    const skipped = skippedExternalIds[type];
    const endpoint = type === "popular_this_week"
      ? "/recommendations/popular/replace"
      : "/recommendations/newly-found/replace";
    try {
      const response = await postExternalJson<ExternalSectionReplaceResponse>(endpoint, {
        current_recommendation_ids: externalIds(type),
        excluded_recommendation_ids: skipped,
        replace_recommendation_id: itemId,
        category
      });
      if (!response.replacement) {
        setNoMatchMessages((current) => ({
          ...current,
          [itemId]: type === "popular_this_week"
            ? "No more books match that category right now."
            : "No more recent books match that category right now."
        }));
        setSkippedExternalIds((current) => ({
          ...current,
          [type]: Array.from(new Set([...current[type], itemId]))
        }));
        return;
      }
      const replacement = normalizeRecommendationItem(response.replacement);
      setSections((current) =>
        current.map((section) => section.type !== type ? section : {
          ...section,
          items: section.items.map((candidate) => {
            const candidateId = candidate.recommendation_id ?? candidate.canonical_identity ?? candidate.work_id;
            return candidateId === itemId ? replacement : candidate;
          })
        })
      );
      setSkippedExternalIds((current) => ({
        ...current,
        [type]: Array.from(new Set([...current[type], itemId]))
      }));
    } catch (err) {
      setNoMatchMessages((current) => ({
        ...current,
        [itemId]: err instanceof Error ? err.message : "Could not replace this book."
      }));
    } finally {
      setLoadingExternal(null);
    }
  }

  async function refreshExternalSection(type: ExternalSectionType, preference: string) {
    setSectionPreferences((current) => ({ ...current, [type]: preference }));
    setLoadingExternal({ section: type, id: "__section__" });
    const endpoint = type === "popular_this_week"
      ? "/recommendations/popular/refresh"
      : "/recommendations/newly-found/refresh";
    try {
      const response = type === "popular_this_week"
        ? await postExternalJson<PopularSectionRefreshResponse>(endpoint, {
            current_recommendation_ids: externalIds(type),
            excluded_recommendation_ids: skippedExternalIds[type],
            preference,
            limit: 5
          })
        : await postExternalJson<NewlyFoundSectionRefreshResponse>(endpoint, {
            current_recommendation_ids: externalIds(type),
            excluded_recommendation_ids: skippedExternalIds[type],
            preference,
            limit: 5
          });
      const nextItems = (type === "popular_this_week"
        ? (response as PopularSectionRefreshResponse).popular_this_week
        : (response as NewlyFoundSectionRefreshResponse).newly_found
      ).map(normalizeRecommendationItem);
      setSkippedExternalIds((current) => ({
        ...current,
        [type]: Array.from(new Set([...current[type], ...externalIds(type)]))
      }));
      setNoMatchMessages((current) => ({
        ...current,
        [`${type}:section`]: nextItems.length > 0 ? "" : type === "popular_this_week"
          ? "No more books match that category right now."
          : "No more recent books match that category right now."
      }));
      setSections((current) => applyExternalRefreshResult(current, type, nextItems));
    } catch (err) {
      setNoMatchMessages((current) => ({
        ...current,
        [`${type}:section`]: err instanceof Error ? err.message : "Could not refresh this section."
      }));
    } finally {
      setLoadingExternal(null);
    }
  }

  async function handleNotInterested(item: RecommendationSectionItem) {
    const previousSections = sections;
    const currentIds = previousSections.flatMap((section) =>
      section.items.map((candidate) => candidate.recommendation_id ?? candidate.work_id)
    );
    setSections((current) =>
      current.map((section) => ({
        ...section,
        items: section.items.filter((candidate) => candidate.work_id !== item.work_id)
      }))
    );
    setFeedbackMessage("Got it. We'll adjust your recommendations.");
    setError("");
    try {
      await submitSectionRecommendationFeedback(
        item,
        "not_interested",
        currentIds,
        settings.recommendationStyle
      );
      setFeedbackMessage("Got it. We replaced that recommendation.");
      await load(true, currentIds, appliedFilters);
    } catch (err) {
      setSections(previousSections);
      setFeedbackMessage("");
      setError(err instanceof Error ? err.message : "Failed to update recommendations");
      throw err;
    }
  }

  function applyFilters(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();

    const parsedMin = minPages === "" ? undefined : Number(minPages);
    const parsedMax = maxPages === "" ? undefined : Number(maxPages);
    if (
      (parsedMin !== undefined && (!Number.isFinite(parsedMin) || parsedMin < 0)) ||
      (parsedMax !== undefined && (!Number.isFinite(parsedMax) || parsedMax < 0))
    ) {
      setFilterError("Page values must be nonnegative numbers.");
      return;
    }
    if (parsedMin !== undefined && parsedMax !== undefined && parsedMin > parsedMax) {
      setFilterError("Minimum pages cannot be greater than maximum pages.");
      return;
    }

    const filters: RecommendationFilters = {
      ...(genre.trim() ? { genre: genre.trim() } : {}),
      ...(parsedMin !== undefined ? { min_pages: parsedMin } : {}),
      ...(parsedMax !== undefined ? { max_pages: parsedMax } : {})
    };
    setFilterError("");
    setAppliedFilters(filters);
    void load(false, [], filters);
  }

  function selectFacet(tab: RecommendationTab, label: string) {
    const filters: RecommendationFilters = {
      ...(tab === "genres" ? { genre: label } : {}),
      ...(tab === "authors" ? { author: label } : {})
    };
    setGenre(tab === "genres" ? label : "");
    setMinPages("");
    setMaxPages("");
    setAppliedFilters(filters);
    void load(false, [], filters);
  }

  return (
    <div className="grid gap-6">
      <PageHeader
        eyebrow="Discover"
        title="Discover recommendations"
        subtitle="Recommendation sections backed by your ShelfTXT ranking service."
        actions={
          <Button variant="secondary" onClick={refreshRecommendations} disabled={loading}>
            {loading ? "Refreshing…" : "Refresh"}
          </Button>
        }
      />

      <form
        className="grid gap-3 rounded-[20px] border border-border bg-surface p-4 shadow-card sm:grid-cols-3 lg:grid-cols-[minmax(180px,1fr)_160px_160px_auto]"
        onSubmit={applyFilters}
        noValidate
      >
        <label className="grid gap-1.5 text-sm">
          <span className="text-text-muted">Genre</span>
          <input
            type="text"
            value={genre}
            onChange={(event) => setGenre(event.target.value)}
            placeholder="e.g. romance"
            className="rounded-lg border border-border bg-bg-elevated px-3 py-2 text-text outline-none placeholder:text-text-dim focus:border-accent/70"
          />
        </label>
        <label className="grid gap-1.5 text-sm">
          <span className="text-text-muted">Min pages</span>
          <input
            type="number"
            min="0"
            value={minPages}
            onChange={(event) => setMinPages(event.target.value)}
            placeholder="0"
            className="rounded-lg border border-border bg-bg-elevated px-3 py-2 text-text outline-none placeholder:text-text-dim focus:border-accent/70"
          />
        </label>
        <label className="grid gap-1.5 text-sm">
          <span className="text-text-muted">Max pages</span>
          <input
            type="number"
            min="0"
            value={maxPages}
            onChange={(event) => setMaxPages(event.target.value)}
            placeholder="Any"
            className="rounded-lg border border-border bg-bg-elevated px-3 py-2 text-text outline-none placeholder:text-text-dim focus:border-accent/70"
          />
        </label>
        <Button variant="primary" type="submit" disabled={loading} className="self-end">
          {loading ? "Applying…" : "Apply filters"}
        </Button>
        {filterError ? (
          <p className="text-xs text-danger sm:col-span-3 lg:col-span-4" role="alert">
            {filterError}
          </p>
        ) : null}
      </form>

      {error ? (
        <div
          className="rounded-lg border border-danger/30 bg-danger-muted px-4 py-3 text-sm text-danger"
          role="alert"
        >
          {error}
        </div>
      ) : null}

      {feedbackMessage ? (
        <p className="text-sm text-text-muted" role="status">{feedbackMessage}</p>
      ) : null}

      {loading ? <p className="text-sm text-text-muted">Loading recommendations…</p> : null}

      <div className="flex gap-2 overflow-x-auto border-b border-border-subtle pb-2" aria-label="Discover filters">
        {(["for-you", "genres", "authors"] as RecommendationTab[]).map((tab) => (
          <button
            key={tab}
            type="button"
            onClick={() => setActiveTab(tab)}
            className={`inline-flex rounded-lg px-3 py-1.5 text-sm ${
              activeTab === tab
                ? "bg-accent-muted text-accent-readable"
                : "border border-border text-text-muted hover:text-text"
            }`}
          >
            {tab === "for-you" ? "For You" : tab === "genres" ? "Genres" : "Authors"}
          </button>
        ))}
      </div>

      {activeTab === "genres" || activeTab === "authors" ? (
        <FacetSelector
          loading={facetsLoading}
          items={activeTab === "genres" ? genreFacets : authorFacets}
          selected={activeTab === "genres" ? appliedFilters.genre : appliedFilters.author}
          emptyLabel={activeTab === "genres" ? "No genre filters yet." : "No author filters yet."}
          onSelect={(label) => selectFacet(activeTab, label)}
        />
      ) : null}

      {!loading && providerStatus ? (
        <p className="text-xs text-text-dim">
          Popular provider {providerStatus.nyt?.available ? "available" : "unavailable"} · Discovery provider {providerStatus.hardcover?.available ? "available" : "unavailable"}.
        </p>
      ) : null}

      {activeTab === "for-you" ? (
        <DiscoverSections
          sections={sections}
          loading={loading}
          loadingExternal={loadingExternal}
          noMatchMessages={noMatchMessages}
          sectionPreferences={sectionPreferences}
          onNotInterested={handleNotInterested}
          onReplaceExternal={replaceExternalCard}
          onRefreshExternal={refreshExternalSection}
        />
      ) : null}
    </div>
  );
}

export function sectionItemFromRecommendation(item: RecommendationItem): RecommendationSectionItem {
  const book = item.recommended_book ?? item.book;
  const score = item.score ?? null;
  const inLibrary = recommendationInLibrary(item);
  const source = recommendationSource(item);
  const relatedBooks = item.related_books ?? item.matched_liked_books ?? [];
  const canonicalIdentity = item.recommendation_id ?? item.work_id ?? book.work_id ?? null;
  return {
    recommendation_id: item.recommendation_id,
    work_id: canonicalIdentity ?? book.id ?? recommendationTitleAuthorIdentity(book.title, book.author),
    external_id: item.external_id ?? book.external_id ?? null,
    edition_id: item.edition_id ?? book.edition_id ?? null,
    isbn: item.isbn ?? book.isbn ?? null,
    isbn_10: book.isbn_10 ?? null,
    isbn_13: book.isbn_13 ?? null,
    canonical_title: book.title,
    canonical_author: book.author,
    book_id: inLibrary ? String(item.book_id ?? book.book_id ?? book.id ?? "") || null : null,
    canonical_identity: canonicalIdentity,
    cover_url: book.cover_url,
    publication_year: item.publication_year ?? book.publication_year ?? book.first_publish_year ?? null,
    first_publish_year: item.first_publish_year ?? book.first_publish_year ?? book.publication_year ?? null,
    page_count: item.page_count ?? book.page_count ?? book.total_pages ?? null,
    total_pages: item.total_pages ?? book.total_pages ?? book.page_count ?? null,
    publisher: item.publisher ?? book.publisher ?? null,
    source_url: item.source_url ?? book.source_url ?? null,
    source_urls: item.source_urls ?? book.source_urls ?? [],
    provider_source_id: item.provider_source_id ?? book.provider_source_id ?? null,
    provider_rating: item.provider_rating ?? book.provider_rating ?? book.rating ?? null,
    rating: item.rating ?? book.rating ?? book.provider_rating ?? null,
    ratings_count: item.ratings_count ?? book.ratings_count ?? null,
    users_count: item.users_count ?? book.users_count ?? null,
    activities_count: item.activities_count ?? book.activities_count ?? null,
    language: item.language ?? book.language ?? null,
    discovery_reason: item.discovery_reason ?? book.discovery_reason ?? null,
    score,
    final_score: item.final_score ?? score,
    reader_likelihood_score: item.reader_likelihood_score ?? null,
    match_label: item.qualitative_match_label ?? recommendationMatchLabel(score ?? 0),
    qualitative_match_label: item.qualitative_match_label ?? recommendationMatchLabel(score ?? 0),
    display_title: book.display_title ?? book.title,
    original_title: book.original_title ?? null,
    genres: item.matched_genres ?? book.genres ?? [],
    traits: item.matched_subjects ?? book.subjects ?? [],
    explanation: {
      primary_reason: item.reason ?? item.explanation ?? "Recommended based on your reading profile.",
      related_books: relatedBooks,
      shared_genres: item.matched_genres ?? [],
      shared_traits: item.matched_subjects ?? [],
      style: "balanced"
    },
    reader_explanation: item.reason ?? item.explanation ?? "Recommended based on your reading profile.",
    library_state: {
      in_library: inLibrary,
      status: null,
      selected_edition_id: inLibrary ? book.id ?? null : null
    },
    in_library: inLibrary,
    is_in_library: inLibrary,
    source,
    external_discovery: source === "external" ? true : item.external_discovery,
    discovery_source: item.discovery_source,
    discovery_query: item.discovery_query,
    discovery_cluster_id: item.discovery_cluster_id,
    exploration_mode: item.exploration_mode,
    exploration_source: item.exploration_source,
    novelty_score: item.novelty_score,
    provider_rank: item.provider_rank,
    score_breakdown: item.score_breakdown,
    diagnostics: item.diagnostics,
    provider: publicRecommendationProvider(item.provider ?? item.discovery_source)
  };
}

export function dedupeSectionItems(items: RecommendationSectionItem[]): RecommendationSectionItem[] {
  const seen = new Set<string>();
  return items.filter((item) => {
    const key = visibleRecommendationKey(item);
    if (seen.has(key)) return false;
    seen.add(key);
    return true;
  });
}

function normalizeRecommendationSections(sections: RecommendationSection[]): RecommendationSection[] {
  return sections.map((section) => ({
    ...section,
    items: section.items.map(normalizeRecommendationItem)
  }));
}

export function explicitRecommendationSections(response: RecommendationSectionsResponse): RecommendationSection[] {
  return splitRecommendationSections(response);
}

export function visibleRecommendationSections(sections: RecommendationSection[]): RecommendationSection[] {
  const seen = new Set<string>();
  return sections
    .map((section) => ({
      ...section,
      items: section.items.filter((item) => {
        const key = visibleRecommendationKey(item);
        if (seen.has(key)) return false;
        seen.add(key);
        return true;
      })
    }))
    .filter((section) => section.items.length > 0);
}

export function mergeLoadedDiscoverSections(
  currentSections: RecommendationSection[],
  nextSections: RecommendationSection[]
): RecommendationSection[] {
  return nextSections.map((nextSection) => {
    if (nextSection.type !== "popular_this_week" && nextSection.type !== "newly_found") {
      return nextSection;
    }
    if (nextSection.items.length > 0) {
      return nextSection;
    }
    const currentSection = currentSections.find((section) => section.type === nextSection.type);
    if (!currentSection || currentSection.items.length === 0) {
      return nextSection;
    }
    return {
      ...nextSection,
      items: currentSection.items
    };
  });
}

export function applyExternalRefreshResult(
  currentSections: RecommendationSection[],
  type: ExternalSectionType,
  nextItems: RecommendationSectionItem[]
): RecommendationSection[] {
  if (nextItems.length === 0) {
    return currentSections;
  }
  return currentSections.map((section) =>
    section.type === type ? { ...section, items: nextItems } : section
  );
}

function visibleRecommendationKey(item: RecommendationSectionItem): string {
  return String(
    item.canonical_identity
    ?? item.recommendation_id
    ?? item.work_id
    ?? recommendationTitleAuthorIdentity(item.canonical_title, item.canonical_author)
  );
}

function recommendationSource(item: RecommendationItem): "library" | "external" {
  if (
    item.source === "external" ||
    item.source === "nyt" ||
    item.source === "hardcover" ||
    item.source_type === "external_discovery" ||
    item.external_discovery === true ||
    item.is_in_library === false ||
    item.in_library === false
  ) {
    return "external";
  }
  if (item.source === "library" || item.is_in_library === true || item.in_library === true) {
    return "library";
  }
  return "external";
}

function recommendationInLibrary(item: RecommendationItem): boolean {
  return recommendationSource(item) === "library";
}

function providerBadgeLabel(item: RecommendationSectionItem): string {
  const provider = publicRecommendationProvider(item.provider ?? item.discovery_source);
  if (provider === "hardcover") return "Hardcover";
  if (provider === "open_library") return "Open Library";
  if (provider === "librarything") return "LibraryThing";
  if (provider === "series_metadata") return "Series metadata";
  if (provider === "nyt") return "Bestseller list";
  return provider ? provider.replace(/_/g, " ") : "External source";
}

function recommendationTitleAuthorIdentity(title: string, author: string): string {
  const normalize = (value: string) =>
    value.toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-+|-+$/g, "");
  return `title_author:${normalize(title)}:${normalize(author.split(",", 1)[0] ?? "")}`;
}

export function DiscoverSections({
  sections,
  loading,
  loadingExternal = null,
  noMatchMessages = {},
  sectionPreferences = { popular_this_week: "mixed", newly_found: "mixed" },
  onNotInterested,
  onReplaceExternal = async () => undefined,
  onRefreshExternal = async () => undefined
}: {
  sections: RecommendationSection[];
  loading: boolean;
  loadingExternal?: LoadingExternalState;
  noMatchMessages?: Record<string, string>;
  sectionPreferences?: Record<ExternalSectionType, string>;
  onNotInterested: (item: RecommendationSectionItem) => Promise<void>;
  onReplaceExternal?: (type: ExternalSectionType, item: RecommendationSectionItem, category: string) => Promise<void>;
  onRefreshExternal?: (type: ExternalSectionType, preference: string) => Promise<void>;
}) {
  const byType = new Map(sections.map((section) => [section.type, section]));
  const orderedTypes: DiscoverSectionType[] = ["shelf_recommendations", "popular_this_week", "newly_found"];
  return (
    <div className="grid gap-6" data-testid="discover-sections">
      {orderedTypes.map((type) => {
        const section = byType.get(type);
        return (
          <DiscoverSectionBlock
            key={type}
            type={type}
            items={section?.items ?? []}
            loading={loading}
            loadingExternal={loadingExternal}
            noMatchMessages={noMatchMessages}
            sectionPreference={type === "shelf_recommendations" ? undefined : sectionPreferences[type]}
            onNotInterested={onNotInterested}
            onReplaceExternal={onReplaceExternal}
            onRefreshExternal={onRefreshExternal}
          />
        );
      })}
    </div>
  );
}

function DiscoverSectionBlock({
  type,
  items,
  loading,
  loadingExternal,
  noMatchMessages,
  sectionPreference,
  onNotInterested,
  onReplaceExternal,
  onRefreshExternal
}: {
  type: DiscoverSectionType;
  items: RecommendationSectionItem[];
  loading: boolean;
  loadingExternal: LoadingExternalState;
  noMatchMessages: Record<string, string>;
  sectionPreference?: string;
  onNotInterested: (item: RecommendationSectionItem) => Promise<void>;
  onReplaceExternal: (type: ExternalSectionType, item: RecommendationSectionItem, category: string) => Promise<void>;
  onRefreshExternal: (type: ExternalSectionType, preference: string) => Promise<void>;
}) {
  const copy = DISCOVER_SECTION_COPY[type];
  const externalType = type === "shelf_recommendations" ? null : type;
  const sectionMessage = externalType ? noMatchMessages[`${externalType}:section`] : "";
  return (
    <section className="grid gap-3" aria-labelledby={`${type}-heading`} data-testid={type} data-preference={sectionPreference}>
      <div className="flex items-start justify-between gap-3">
        <div className="grid gap-1">
          <h2 id={`${type}-heading`} className="text-sm font-semibold uppercase text-text-dim">
            {copy.title}
          </h2>
          <p className="text-sm text-text-muted">{copy.description}</p>
        </div>
        {externalType ? (
          <PreferenceMenu
            label={`Refresh ${copy.title}`}
            options={externalType === "popular_this_week" ? POPULAR_REFRESH_OPTIONS : NEWLY_REFRESH_OPTIONS}
            disabled={loadingExternal?.section === externalType}
            onSelect={(preference) => onRefreshExternal(externalType, preference)}
          />
        ) : null}
      </div>
      {sectionMessage ? <p className="text-sm text-text-muted" role="status">{sectionMessage}</p> : null}
      {loading ? (
        <SectionSkeleton />
      ) : items.length === 0 ? (
        <EmptyState title={copy.empty} description={copy.description} />
      ) : (
        <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-5">
          {items.slice(0, 5).map((item) => {
            if (type === "shelf_recommendations") {
              return (
                <ShelfRecommendationCard
                  key={visibleRecommendationKey(item)}
                  item={item}
                  onNotInterested={onNotInterested}
                />
              );
            }
            if (type === "popular_this_week") {
              return (
                <PopularityCard
                  key={visibleRecommendationKey(item)}
                  item={item}
                  loading={loadingExternal?.section === "popular_this_week" && loadingExternal.id === (item.recommendation_id ?? item.canonical_identity ?? item.work_id)}
                  message={noMatchMessages[item.recommendation_id ?? item.canonical_identity ?? item.work_id] ?? ""}
                  onReplace={(category) => onReplaceExternal("popular_this_week", item, category)}
                />
              );
            }
            return (
              <DiscoveryCard
                key={visibleRecommendationKey(item)}
                item={item}
                loading={loadingExternal?.section === "newly_found" && loadingExternal.id === (item.recommendation_id ?? item.canonical_identity ?? item.work_id)}
                message={noMatchMessages[item.recommendation_id ?? item.canonical_identity ?? item.work_id] ?? ""}
                onReplace={(category) => onReplaceExternal("newly_found", item, category)}
              />
            );
          })}
        </div>
      )}
    </section>
  );
}

function PreferenceMenu({
  label,
  options,
  disabled,
  onSelect
}: {
  label: string;
  options: readonly (readonly [string, string])[];
  disabled?: boolean;
  onSelect: (value: string) => void | Promise<void>;
}) {
  const [open, setOpen] = useState(false);
  const [activeIndex, setActiveIndex] = useState(0);
  const buttonRef = useRef<HTMLButtonElement | null>(null);
  const itemRefs = useRef<Array<HTMLButtonElement | null>>([]);

  function closeMenu() {
    setOpen(false);
    window.setTimeout(() => buttonRef.current?.focus(), 0);
  }

  function handleKeyDown(event: KeyboardEvent<HTMLDivElement>) {
    if (event.key === "Escape") {
      event.preventDefault();
      closeMenu();
      return;
    }
    if (event.key === "ArrowDown" || event.key === "ArrowUp") {
      event.preventDefault();
      const delta = event.key === "ArrowDown" ? 1 : -1;
      const next = (activeIndex + delta + options.length) % options.length;
      setActiveIndex(next);
      itemRefs.current[next]?.focus();
    }
  }

  return (
    <div className="relative justify-self-start" onKeyDown={handleKeyDown}>
      <button
        ref={buttonRef}
        type="button"
        aria-haspopup="menu"
        aria-expanded={open}
        aria-label={label}
        disabled={disabled}
        onClick={() => setOpen((current) => !current)}
        className="inline-flex h-8 min-w-8 items-center justify-center rounded-full border border-border bg-bg-elevated px-2 text-xs text-text-muted transition hover:text-text focus:outline-none focus:ring-2 focus:ring-accent/60 disabled:cursor-not-allowed disabled:opacity-50"
      >
        ↻
      </button>
      {open ? (
        <div
          role="menu"
          className="absolute right-0 z-20 mt-2 grid min-w-44 gap-1 rounded-lg border border-border bg-surface p-1 shadow-card"
        >
          {options.map(([value, optionLabel], index) => (
            <button
              key={`${value}-${optionLabel}`}
              ref={(node) => {
                itemRefs.current[index] = node;
              }}
              type="button"
              role="menuitem"
              tabIndex={index === activeIndex ? 0 : -1}
              onFocus={() => setActiveIndex(index)}
              onClick={() => {
                void onSelect(value);
                closeMenu();
              }}
              className="rounded-md px-3 py-1.5 text-left text-sm text-text-muted hover:bg-bg-elevated hover:text-text focus:bg-bg-elevated focus:text-text focus:outline-none"
            >
              {optionLabel}
            </button>
          ))}
        </div>
      ) : null}
    </div>
  );
}

function SectionSkeleton() {
  return (
    <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-5" aria-label="Loading section">
      {Array.from({ length: 5 }).map((_, index) => (
        <Card key={index} className="grid gap-3">
          <div className="h-44 animate-pulse rounded-lg bg-bg-elevated" />
          <div className="h-4 animate-pulse rounded bg-bg-elevated" />
          <div className="h-3 w-2/3 animate-pulse rounded bg-bg-elevated" />
          <div className="h-8 animate-pulse rounded bg-bg-elevated" />
        </Card>
      ))}
    </div>
  );
}

function ShelfRecommendationCard({
  item,
  onNotInterested
}: {
  item: RecommendationSectionItem;
  onNotInterested: (item: RecommendationSectionItem) => Promise<void>;
}) {
  return (
    <Card className="grid content-start gap-3">
      <BookCover title={item.canonical_title} coverUrl={item.cover_url} className="w-full" />
      <div className="grid gap-1">
        <div className="flex flex-wrap gap-2">
          <span className="rounded-full border border-accent/30 bg-accent-muted px-2 py-0.5 text-xs text-accent-readable">
            Shelf
          </span>
          <span className="rounded-full border border-border px-2 py-0.5 text-xs text-text-muted">
            {getRecommendationMatchLabel(item)}
          </span>
        </div>
        <h3 className="line-clamp-2 font-semibold text-text">{item.canonical_title}</h3>
        <p className="truncate text-sm text-text-muted">{item.canonical_author}</p>
      </div>
      <p className="line-clamp-3 text-sm leading-6 text-text-muted">
        {getRecommendationDisplayExplanation(item)}
      </p>
      <button
        type="button"
        aria-label={`Not interested in ${item.canonical_title}`}
        onClick={() => void onNotInterested(item)}
        className="justify-self-start rounded-lg px-3 py-1.5 text-xs text-text-dim hover:bg-bg-elevated hover:text-text"
      >
        Not interested
      </button>
    </Card>
  );
}

function PopularityCard({
  item,
  loading,
  message,
  onReplace
}: {
  item: RecommendationSectionItem;
  loading: boolean;
  message: string;
  onReplace: (category: string) => Promise<void>;
}) {
  const metadata = [
    item.broad_genre ?? item.nyt_list_name ?? item.genres[0] ?? null,
    item.nyt_rank ? `#${item.nyt_rank}` : null,
    item.nyt_weeks_on_list ? `${item.nyt_weeks_on_list} weeks on list` : null
  ].filter(Boolean);
  return (
    <Card className={`relative grid content-start gap-3 transition ${loading ? "opacity-70" : "opacity-100"}`}>
      <div className="absolute right-2 top-2 z-10">
        <PreferenceMenu
          label={`Replace ${item.canonical_title}`}
          options={POPULAR_CATEGORY_OPTIONS}
          disabled={loading}
          onSelect={onReplace}
        />
      </div>
      <BookCover title={item.canonical_title} coverUrl={item.cover_url} className="w-full" />
      <div className="grid gap-1">
        <div className="flex flex-wrap gap-2">
          <span className="rounded-full border border-border px-2 py-0.5 text-xs text-text-muted">
            Bestseller list
          </span>
          <span className="rounded-full border border-border px-2 py-0.5 text-xs text-text-muted">
            Popular this week
          </span>
        </div>
        <h3 className="line-clamp-2 font-semibold text-text">{item.canonical_title}</h3>
        <p className="truncate text-sm text-text-muted">{item.canonical_author}</p>
        {metadata.length > 0 ? (
          <p className="text-xs text-text-dim">{metadata.join(" · ")}</p>
        ) : null}
      </div>
      {loading ? <p className="text-xs text-text-dim" role="status">Replacing...</p> : null}
      {message ? <p className="text-xs text-text-muted" role="status">{message}</p> : null}
    </Card>
  );
}

function DiscoveryCard({
  item,
  loading,
  message,
  onReplace
}: {
  item: RecommendationSectionItem;
  loading: boolean;
  message: string;
  onReplace: (category: string) => Promise<void>;
}) {
  const year = item.publication_year ?? item.first_publish_year;
  const description = externalDiscoveryDescription(item);
  return (
    <Card className={`relative grid content-start gap-3 transition ${loading ? "opacity-70" : "opacity-100"}`}>
      <div className="absolute right-2 top-2 z-10">
        <PreferenceMenu
          label={`Replace ${item.canonical_title}`}
          options={NEWLY_FOUND_CATEGORY_OPTIONS}
          disabled={loading}
          onSelect={onReplace}
        />
      </div>
      <BookCover title={item.canonical_title} coverUrl={item.cover_url} className="w-full" />
      <div className="grid gap-1">
        <div className="flex flex-wrap gap-2">
          <span className="rounded-full border border-border px-2 py-0.5 text-xs text-text-muted">
            {providerBadgeLabel(item)}
          </span>
          {year ? (
            <span className="rounded-full border border-border px-2 py-0.5 text-xs text-text-muted">
              Published in {year}
            </span>
          ) : null}
        </div>
        <h3 className="line-clamp-2 font-semibold text-text">{item.canonical_title}</h3>
        <p className="truncate text-sm text-text-muted">{item.canonical_author}</p>
      </div>
      {description ? <p className="line-clamp-3 text-sm leading-6 text-text-muted">{description}</p> : null}
      {loading ? <p className="text-xs text-text-dim" role="status">Replacing...</p> : null}
      {message ? <p className="text-xs text-text-muted" role="status">{message}</p> : null}
    </Card>
  );
}

function externalDiscoveryDescription(item: RecommendationSectionItem): string {
  const candidates = [
    item.description,
    item.discovery_reason,
    item.explanation.primary_reason,
    item.reader_explanation
  ];
  return candidates.find((candidate) => isSpecificDiscoveryCopy(candidate)) ?? "";
}

function isSpecificDiscoveryCopy(value: unknown): value is string {
  if (typeof value !== "string") return false;
  const text = value.trim();
  if (!text) return false;
  return text !== "Selected from your unread shelf based on your reading history.";
}

function FacetSelector({
  loading,
  items,
  selected,
  emptyLabel,
  onSelect
}: {
  loading: boolean;
  items: RecommendationFacet[];
  selected?: string;
  emptyLabel: string;
  onSelect: (label: string) => void;
}) {
  if (loading) return <p className="text-sm text-text-muted">Loading filters...</p>;
  if (items.length === 0) return <p className="text-sm text-text-muted">{emptyLabel}</p>;
  return (
    <div className="flex flex-wrap gap-2">
      {items.map((item) => {
        const active = selected?.toLowerCase() === item.label.toLowerCase();
        return (
          <button
            key={item.label}
            type="button"
            onClick={() => onSelect(item.label)}
            className={`rounded-full border px-3 py-1.5 text-sm ${
              active
                ? "border-accent/40 bg-accent-muted text-accent-readable"
                : "border-border bg-bg-elevated text-text-muted hover:text-text"
            }`}
          >
            {item.label}
            <span className="ml-2 text-xs text-text-dim">{item.candidate_count}</span>
          </button>
        );
      })}
    </div>
  );
}
