import { useCallback, useEffect, useState } from "react";

import { PageHeader } from "@/components/layout/PageHeader";
import { Button } from "@/components/ui/Button";
import { EmptyState } from "@/components/ui/EmptyState";
import { RecommendationsList } from "@/features/recommendations/RecommendationsList";
import { useUserSettings } from "@/contexts/UserSettingsContext";
import { fetchJson } from "@/lib/api";
import { recommendQuery } from "@/lib/userSettings";
import type { RecommendationItem } from "@/lib/types";

export function RankingPage() {
  const { settings } = useUserSettings();
  const [items, setItems] = useState<RecommendationItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  const load = useCallback(async (refresh = false, excludeIds: string[] = []) => {
    setLoading(true);
    setError("");
    try {
      const ranked = await fetchJson<RecommendationItem[]>(recommendQuery(settings, refresh, excludeIds), {
        skipClientCache: refresh,
      });
      setItems(Array.isArray(ranked) ? ranked : []);
    } catch (err) {
      setItems([]);
      setError(err instanceof Error ? err.message : "Failed to load recommendations");
    } finally {
      setLoading(false);
    }
  }, [settings.recommendationStyle]);

  useEffect(() => {
    void load();
  }, [load]);

  function refreshRecommendations() {
    const excludeIds = items.map((item) => (item.recommended_book ?? item.book).id).filter(Boolean);
    void load(true, excludeIds);
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
