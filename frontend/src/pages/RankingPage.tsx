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
        title="Top recommendations"
        subtitle="Your top 10 to-read picks with scores, explanations, and similar books."
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

      {!loading && !error && items.length === 0 ? (
        <EmptyState
          title="No strong recommendations yet"
          description="No unread book currently passes the metadata match threshold. Enrich your library and rate completed books to unlock better matches."
        />
      ) : null}

      {!loading && items.length > 0 ? <RecommendationsList items={items} limit={10} /> : null}
    </div>
  );
}
