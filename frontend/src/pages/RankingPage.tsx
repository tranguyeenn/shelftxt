import { useCallback, useEffect, useState, type FormEvent } from "react";
import { Link } from "react-router-dom";

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
  getClusterDisplayTitle,
  getRecommendationDisplayExplanation,
  getRecommendationMatchLabel,
  normalizeRecommendationItem,
  visibleRecommendationTags
} from "@/lib/recommendationNormalization";
import { recommendationSectionsQuery, type RecommendationFilters } from "@/lib/userSettings";
import type {
  RecommendationFacet,
  RecommendationFacetResponse,
  RecommendationClustersResponse,
  RecommendationCluster,
  RecommendationItem,
  RecommendationSection,
  RecommendationSectionItem,
  RecommendationSectionsResponse
} from "@/lib/types";

type RecommendationTab = "for-you" | "genres" | "authors";

const RECOMMENDATION_UI_RESPONSE_VERSION = "identity-v2";

export function RankingPage() {
  const {
    settings,
    recommendationFilters: appliedFilters,
    setRecommendationFilters: setAppliedFilters
  } = useUserSettings();
  const [sections, setSections] = useState<RecommendationSection[]>([]);
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
  const visibleSections = visibleRecommendationSections(sections);

  const loadFallbackSections = useCallback(async (
    refresh = false,
    excludeIds: string[] = [],
    filters: RecommendationFilters = {}
  ) => {
    const endpoint = recommendationSectionsQuery(settings, refresh, excludeIds, filters);
    try {
      const ranked = await fetchJson<RecommendationSectionsResponse>(
        endpoint,
        { skipClientCache: refresh }
      );
      const responseSections = Array.isArray(ranked.sections) ? ranked.sections : [];
      return {
        sections: normalizeRecommendationSections(responseSections)
      };
    } catch (err) {
      throw err instanceof Error ? err : new Error("Failed to load recommendations");
    }
  }, [settings.recommendationStyle]);

  const load = useCallback(async (
    refresh = false,
    excludeIds: string[] = [],
    filters: RecommendationFilters = {}
  ) => {
    setLoading(true);
    setError("");
    try {
      const clusterEndpoint = recommendationClustersQuery(settings);
      const clustered = await fetchJson<RecommendationClustersResponse>(
        clusterEndpoint,
        { skipClientCache: refresh }
      );
      const clusterSections = normalizeRecommendationClusterSections(clustered);
      if (clusterSections.length > 0) {
        setSections(clusterSections);
        return;
      }
      const fallback = await loadFallbackSections(refresh, excludeIds, filters);
      setSections(fallback.sections);
    } catch (clusterErr) {
      try {
        const fallback = await loadFallbackSections(refresh, excludeIds, filters);
        setSections(fallback.sections);
      } catch (fallbackErr) {
        setSections([]);
        setError(
          fallbackErr instanceof Error
            ? fallbackErr.message
            : clusterErr instanceof Error
              ? clusterErr.message
              : "Failed to load recommendations"
        );
      }
    } finally {
      setLoading(false);
    }
  }, [loadFallbackSections, settings.recommendationStyle]);

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

      {!loading && !error && sections.every((section) => section.items.length === 0) && visibleSections.every((section) => section.items.length === 0) ? (
        <EmptyState
          title="No clear recommendation yet."
          description="Add more books from your TBR or rate a few finished reads so ShelfTxt can explain the next pick."
        />
      ) : null}

      {!loading && visibleSections.some((section) => section.items.length > 0) ? (
        <div className="grid gap-6">
          {visibleSections.map((section) => (
            <RecommendationSectionBlock
              key={section.id}
              section={section}
              onNotInterested={handleNotInterested}
            />
          ))}
        </div>
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
    canonical_title: book.title,
    canonical_author: book.author,
    book_id: inLibrary ? String(item.book_id ?? book.book_id ?? book.id ?? "") || null : null,
    canonical_identity: canonicalIdentity,
    cover_url: book.cover_url,
    score,
    final_score: item.final_score ?? score,
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
    provider: item.provider ?? item.discovery_source ?? null
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

function normalizeRecommendationClusterSections(clusters: RecommendationClustersResponse): RecommendationSection[] {
  if (!Array.isArray(clusters)) return [];
  return clusters
    .filter((cluster) => Array.isArray(cluster.recommendations) && cluster.recommendations.length > 0)
    .map(clusterSectionFromCluster);
}

function clusterSectionFromCluster(cluster: RecommendationCluster): RecommendationSection {
  const title = cluster.title || "Recommended for you";
  return {
    ...cluster,
    id: `cluster-${cluster.cluster_id}`,
    type: "cluster",
    title: cluster.title,
    reading_identity: cluster.reading_identity || title,
    source_book: null,
    why: cluster.why || undefined,
    anchors: Array.isArray(cluster.anchors) ? cluster.anchors : [],
    dominant_genres: Array.isArray(cluster.dominant_genres) ? cluster.dominant_genres : [],
    dominant_themes: Array.isArray(cluster.dominant_themes) ? cluster.dominant_themes : [],
    items: cluster.recommendations.map((item) => ({
      ...normalizeRecommendationItem(item),
      cluster_id: cluster.cluster_id
    }))
  };
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

function visibleRecommendationKey(item: RecommendationSectionItem): string {
  return String(
    item.canonical_identity
    ?? item.recommendation_id
    ?? item.work_id
    ?? recommendationTitleAuthorIdentity(item.canonical_title, item.canonical_author)
  );
}

function sectionItemSource(item: RecommendationSectionItem): "library" | "external" {
  return item.source === "external" || item.library_state.in_library === false ? "external" : "library";
}

function recommendationSource(item: RecommendationItem): "library" | "external" {
  if (item.source === "external" || item.source_type === "external_discovery" || item.external_discovery === true || item.is_in_library === false || item.in_library === false) {
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

function recommendationActionLabel(item: RecommendationSectionItem): string {
  return item.library_state.in_library ? "Start reading" : "Add to library";
}

function recommendationBadgeLabel(item: RecommendationSectionItem): string {
  const fallback = item.library_state.in_library ? "On your shelf" : "Outside your library";
  return sectionItemSource(item) === "external" ? "Outside your library" : fallback;
}

function recommendationTitleAuthorIdentity(title: string, author: string): string {
  const normalize = (value: string) =>
    value.toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-+|-+$/g, "");
  return `title_author:${normalize(title)}:${normalize(author.split(",", 1)[0] ?? "")}`;
}

function recommendationClustersQuery(settings: { recommendationStyle: string }): string {
  const params = new URLSearchParams({
    style: settings.recommendationStyle,
    limit: "3",
    max_per_cluster: "3",
    ui_response_version: RECOMMENDATION_UI_RESPONSE_VERSION
  });
  return `/recommendations/clusters?${params.toString()}`;
}

function RecommendationSectionBlock({
  section,
  onNotInterested
}: {
  section: RecommendationSection;
  onNotInterested: (item: RecommendationSectionItem) => Promise<void>;
}) {
  if (section.items.length === 0) return null;
  const anchors = section.anchors ?? [];
  const readingIdentity = getClusterDisplayTitle(section);
  const themes = [...(section.dominant_themes ?? []), ...(section.dominant_genres ?? [])]
    .filter((theme) => visibleRecommendationTags([theme]).length > 0)
    .filter((theme, index, all) => theme && all.findIndex((candidate) => candidate.toLowerCase() === theme.toLowerCase()) === index)
    .slice(0, 6);
  return (
    <section className="grid gap-3">
      <div className="grid gap-2">
        <h2 className="text-sm font-semibold uppercase text-text-dim">{readingIdentity}</h2>
        {anchors.length > 0 ? (
          <p className="text-sm text-text-muted">
            Anchors: {anchors.slice(0, 3).map((anchor) => anchor.title).join(", ")}
          </p>
        ) : null}
        {section.why ? <p className="text-sm text-text-muted">{section.why}</p> : null}
        {themes.length > 0 ? (
          <div className="flex flex-wrap gap-2" aria-label={`${section.title} themes`}>
            {themes.map((theme) => (
              <span key={theme} className="rounded-full border border-border px-2 py-1 text-xs text-text-muted">
                {theme}
              </span>
            ))}
          </div>
        ) : null}
      </div>
      <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
        {section.items.map((item) => (
          <StructuredRecommendationCard key={visibleRecommendationKey(item)}
            item={item}
            onNotInterested={onNotInterested}
          />
        ))}
      </div>
    </section>
  );
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

function StructuredRecommendationCard({
  item,
  onNotInterested
}: {
  item: RecommendationSectionItem;
  onNotInterested: (item: RecommendationSectionItem) => Promise<void>;
}) {
  const [submittingFeedback, setSubmittingFeedback] = useState(false);
  const [feedbackError, setFeedbackError] = useState("");
  const actionLabel = recommendationActionLabel(item);
  const badgeLabel = recommendationBadgeLabel(item);
  const detailsPath = item.library_state.in_library
    ? `/app/book/${encodeURIComponent(item.book_id ?? item.work_id)}`
    : "/app/add";
  const visibleTags = visibleRecommendationTags([...item.genres, ...item.traits]).slice(0, 5);
  const matchLabel = getRecommendationMatchLabel(item);
  const readerExplanation = getRecommendationDisplayExplanation(item);

  return (
    <Card className="grid gap-4">
      <div className="grid grid-cols-[84px_minmax(0,1fr)] gap-3">
        <BookCover title={item.canonical_title} coverUrl={item.cover_url} className="w-[84px] rounded-lg" />
        <div className="min-w-0">
          <div className="flex flex-wrap gap-2">
            <span className="rounded-full border border-accent/30 bg-accent-muted px-2 py-0.5 text-xs text-accent-readable">
              {matchLabel}
            </span>
            <span className="rounded-full border border-border px-2 py-0.5 text-xs text-text-muted">
              {badgeLabel}
            </span>
          </div>
          <h3 className="mt-3 line-clamp-2 font-semibold text-text">{item.canonical_title}</h3>
          <p className="mt-1 truncate text-sm text-text-muted">{item.canonical_author}</p>
        </div>
      </div>
      <p className="line-clamp-3 text-sm leading-6 text-text-muted">{readerExplanation}</p>
      {visibleTags.length > 0 ? (
        <div className="flex flex-wrap gap-2">
          {visibleTags.map((tag) => (
            <span key={tag} className="rounded-full border border-border px-2 py-1 text-xs text-text-muted">
              {tag}
            </span>
          ))}
        </div>
      ) : null}
      <div className="flex flex-wrap gap-2">
        <Button variant="secondary" className="px-3 py-1.5 text-xs">
          {actionLabel}
        </Button>
        <Link
          to={detailsPath}
          className="rounded-lg border border-border px-3 py-1.5 text-xs text-text-muted hover:text-text"
        >
          View Details
        </Link>
        <button
          type="button"
          disabled={submittingFeedback}
          aria-label={`Not interested in ${item.canonical_title}`}
          title="This recommendation may not match what you want right now."
          onClick={async () => {
            setSubmittingFeedback(true);
            setFeedbackError("");
            try {
              await onNotInterested(item);
            } catch (err) {
              setFeedbackError(err instanceof Error ? err.message : "Could not update recommendations.");
              setSubmittingFeedback(false);
            }
          }}
          className="rounded-lg px-3 py-1.5 text-xs text-text-dim hover:bg-bg-elevated hover:text-text disabled:cursor-not-allowed disabled:opacity-50"
        >
          {submittingFeedback ? "Adjusting..." : "Not interested"}
        </button>
      </div>
      {feedbackError ? (
        <p className="text-sm text-danger" role="alert">{feedbackError}</p>
      ) : null}
    </Card>
  );
}
