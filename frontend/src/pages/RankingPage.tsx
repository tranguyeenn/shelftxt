import { useCallback, useEffect, useState, type FormEvent } from "react";
import { Link } from "react-router-dom";

import { PageHeader } from "@/components/layout/PageHeader";
import { BookCover } from "@/components/ui/BookCover";
import { Button } from "@/components/ui/Button";
import { Card } from "@/components/ui/Card";
import { EmptyState } from "@/components/ui/EmptyState";
import { useUserSettings } from "@/contexts/UserSettingsContext";
import { fetchJson } from "@/lib/api";
import { recommendationSectionsQuery, type RecommendationFilters } from "@/lib/userSettings";
import type {
  RecommendationFacet,
  RecommendationFacetResponse,
  RecommendationSection,
  RecommendationSectionItem,
  RecommendationSectionsResponse
} from "@/lib/types";

type RecommendationTab = "for-you" | "genres" | "authors";

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
  const [genre, setGenre] = useState(appliedFilters.genre ?? "");
  const [minPages, setMinPages] = useState(
    appliedFilters.min_pages === undefined ? "" : String(appliedFilters.min_pages)
  );
  const [maxPages, setMaxPages] = useState(
    appliedFilters.max_pages === undefined ? "" : String(appliedFilters.max_pages)
  );

  const load = useCallback(async (
    refresh = false,
    excludeIds: string[] = [],
    filters: RecommendationFilters = {}
  ) => {
    setLoading(true);
    setError("");
    try {
      const ranked = await fetchJson<RecommendationSectionsResponse>(
        recommendationSectionsQuery(settings, refresh, excludeIds, filters),
        { skipClientCache: refresh }
      );
      setSections(Array.isArray(ranked.sections) ? ranked.sections : []);
    } catch (err) {
      setSections([]);
      setError(err instanceof Error ? err.message : "Failed to load recommendations");
    } finally {
      setLoading(false);
    }
  }, [settings.recommendationStyle]);

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
        title="For You"
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

      {!loading && !error && sections.every((section) => section.items.length === 0) ? (
        <EmptyState
          title="No clear recommendation yet."
          description="Add more books from your TBR or rate a few finished reads so ShelfTxt can explain the next pick."
        />
      ) : null}

      {!loading && sections.some((section) => section.items.length > 0) ? (
        <div className="grid gap-6">
          {sections.map((section) => (
            <RecommendationSectionBlock key={section.id} section={section} />
          ))}
        </div>
      ) : null}
    </div>
  );
}

function RecommendationSectionBlock({ section }: { section: RecommendationSection }) {
  if (section.items.length === 0) return null;
  return (
    <section className="grid gap-3">
      <h2 className="text-sm font-semibold uppercase text-text-dim">{section.title}</h2>
      <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
        {section.items.map((item) => (
          <StructuredRecommendationCard key={item.work_id} item={item} />
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

function StructuredRecommendationCard({ item }: { item: RecommendationSectionItem }) {
  return (
    <Card className="grid gap-4">
      <div className="grid grid-cols-[84px_minmax(0,1fr)] gap-3">
        <BookCover title={item.canonical_title} coverUrl={item.cover_url} className="w-[84px] rounded-lg" />
        <div className="min-w-0">
          <div className="flex flex-wrap gap-2">
            <span className="rounded-full border border-accent/30 bg-accent-muted px-2 py-0.5 text-xs text-accent-readable">
              {item.match_label}
            </span>
            <span className="rounded-full border border-border px-2 py-0.5 text-xs text-text-muted">
              {item.library_state.in_library ? "On your shelf" : "New discovery"}
            </span>
            {item.match_percentage != null ? (
              <span className="rounded-full border border-border px-2 py-0.5 text-xs text-text-muted">
                {item.match_percentage}% match
              </span>
            ) : null}
          </div>
          <h3 className="mt-3 line-clamp-2 font-semibold text-text">{item.canonical_title}</h3>
          <p className="mt-1 truncate text-sm text-text-muted">{item.canonical_author}</p>
        </div>
      </div>
      <p className="line-clamp-3 text-sm leading-6 text-text-muted">{item.explanation.primary_reason}</p>
      {[...item.genres, ...item.traits].length > 0 ? (
        <div className="flex flex-wrap gap-2">
          {[...item.genres, ...item.traits].slice(0, 5).map((tag) => (
            <span key={tag} className="rounded-full border border-border px-2 py-1 text-xs text-text-muted">
              {tag}
            </span>
          ))}
        </div>
      ) : null}
      <div className="flex flex-wrap gap-2">
        <Button variant="secondary" className="px-3 py-1.5 text-xs">
          {item.library_state.in_library ? "Start Reading" : "Add to Library"}
        </Button>
        <Link
          to={item.library_state.in_library ? `/app/book/${encodeURIComponent(item.work_id)}` : "/app/add"}
          className="rounded-lg border border-border px-3 py-1.5 text-xs text-text-muted hover:text-text"
        >
          View Details
        </Link>
      </div>
    </Card>
  );
}
