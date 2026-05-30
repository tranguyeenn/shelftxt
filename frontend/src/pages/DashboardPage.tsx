import { useCallback, useEffect, useState } from "react";
import { Link } from "react-router-dom";

import { PageHeader } from "@/components/layout/PageHeader";
import { Button } from "@/components/ui/Button";
import { EmptyState } from "@/components/ui/EmptyState";
import { QuickActions } from "@/features/dashboard/QuickActions";
import { ReadingStats } from "@/features/dashboard/ReadingStats";
import { RecommendedNextCard } from "@/features/dashboard/RecommendedNextCard";
import { RecommendationsList } from "@/features/recommendations/RecommendationsList";
import { useUserSettings } from "@/contexts/UserSettingsContext";
import { fetchJson } from "@/lib/api";
import { fetchAllLibraryBooks, type BookRecord } from "@/lib/books";
import { recommendQuery } from "@/lib/userSettings";
import type { RecommendationItem } from "@/lib/types";

export function DashboardPage() {
  const { settings } = useUserSettings();
  const [library, setLibrary] = useState<BookRecord[]>([]);
  const [recommendations, setRecommendations] = useState<RecommendationItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  const load = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      const [books, recs] = await Promise.all([
        fetchAllLibraryBooks(),
        fetchJson<RecommendationItem[]>(recommendQuery(settings))
      ]);
      setLibrary(books);
      setRecommendations(Array.isArray(recs) ? recs : []);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load dashboard");
      setLibrary([]);
      setRecommendations([]);
    } finally {
      setLoading(false);
    }
  }, [settings.recommendationStyle]);

  useEffect(() => {
    void load();
  }, [load]);

  const topPick = recommendations[0] ?? null;

  return (
    <div className="grid gap-8">
      <PageHeader
        title="Recommended Next"
        subtitle="Our system thinks you should read next."
        actions={
          <Button variant="secondary" onClick={() => void load()} disabled={loading}>
            {loading ? "Refreshing…" : "Refresh signals"}
          </Button>
        }
      />

      {error ? (
        <div
          className="rounded-lg border border-danger/30 bg-danger-muted px-4 py-3 text-sm text-danger"
          role="alert"
        >
          {error}
        </div>
      ) : null}

      {loading && !topPick ? (
        <p className="text-sm text-text-muted">Loading recommendation signals…</p>
      ) : null}

      {!loading && !topPick && !error ? (
        <EmptyState
          title="No TBR recommendation yet"
          description="Add books with status “to-read” to your library, or import a CSV, then the ranker can pick your next read."
          action={
            <Link
              to="/add"
              className="inline-flex rounded-lg bg-accent px-4 py-2 text-sm font-medium text-bg hover:bg-accent-dim"
            >
              Add your first book
            </Link>
          }
        />
      ) : null}

      {topPick ? <RecommendedNextCard item={topPick} /> : null}

      {recommendations.length > 0 ? (
        <section className="grid gap-4">
          <div className="flex items-center justify-between gap-3">
            <h2 className="text-lg font-semibold text-text">Top 10 recommendations</h2>
            <Link to="/ranking" className="text-sm text-accent hover:underline">
              View all
            </Link>
          </div>
          <RecommendationsList
            items={topPick ? recommendations.slice(1) : recommendations}
            limit={topPick ? 9 : 10}
          />
        </section>
      ) : null}

      <ReadingStats library={library} />
      <QuickActions />
    </div>
  );
}
