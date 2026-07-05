import { useCallback, useEffect, useState, type FormEvent } from "react";

import { PageHeader } from "@/components/layout/PageHeader";
import { Button } from "@/components/ui/Button";
import { EmptyState } from "@/components/ui/EmptyState";
import { RecommendationsList } from "@/features/recommendations/RecommendationsList";
import { useUserSettings } from "@/contexts/UserSettingsContext";
import { fetchJson } from "@/lib/api";
import { recommendQuery, type RecommendationFilters } from "@/lib/userSettings";
import type { RecommendationItem } from "@/lib/types";

export function RankingPage() {
  const {
    settings,
    recommendationFilters: appliedFilters,
    setRecommendationFilters: setAppliedFilters
  } = useUserSettings();
  const [items, setItems] = useState<RecommendationItem[]>([]);
  const [loading, setLoading] = useState(true);
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
      const ranked = await fetchJson<RecommendationItem[]>(
        recommendQuery(settings, refresh, excludeIds, filters),
        { skipClientCache: refresh }
      );
      setItems(Array.isArray(ranked) ? ranked : []);
    } catch (err) {
      setItems([]);
      setError(err instanceof Error ? err.message : "Failed to load recommendations");
    } finally {
      setLoading(false);
    }
  }, [settings.recommendationStyle]);

  useEffect(() => {
    void load(false, [], appliedFilters);
  }, [load]);

  function refreshRecommendations() {
    const excludeIds = items.map((item) => (item.recommended_book ?? item.book).id).filter(Boolean);
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

  return (
    <div className="grid gap-6">
      <PageHeader
        title="Recommendations"
        subtitle="Ranked books from your own shelf patterns."
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

      <div className="border-b border-border-subtle pb-2">
        <span className="inline-flex rounded-lg bg-accent-muted px-3 py-1.5 text-sm text-accent">
          for you
        </span>
      </div>

      {!loading && !error && items.length === 0 ? (
        <EmptyState
          title="No clear recommendation yet."
          description="Add more books from your TBR or rate a few finished reads so ShelfTxt can explain the next pick."
        />
      ) : null}

      {!loading && items.length > 0 ? (
        <div className="grid gap-4">
          <RecommendationsList items={items} limit={10} />
        </div>
      ) : null}
    </div>
  );
}
