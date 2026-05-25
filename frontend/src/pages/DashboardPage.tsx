import { useCallback, useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";

import { PageHeader } from "@/components/layout/PageHeader";
import { Button } from "@/components/ui/Button";
import { EmptyState } from "@/components/ui/EmptyState";
import { QuickActions } from "@/features/dashboard/QuickActions";
import { ReadingStats } from "@/features/dashboard/ReadingStats";
import { RecommendedNextCard } from "@/features/dashboard/RecommendedNextCard";
import { ScoreBreakdownPanel } from "@/features/dashboard/ScoreBreakdown";
import { fetchJson } from "@/lib/api";
import type { BookRecord } from "@/lib/books";
import { buildScoreBreakdown } from "@/lib/scoring";

export function DashboardPage() {
  const [library, setLibrary] = useState<BookRecord[]>([]);
  const [recommendation, setRecommendation] = useState<BookRecord | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  const load = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      const [books, recs] = await Promise.all([
        fetchJson<BookRecord[]>("/books"),
        fetchJson<BookRecord[]>("/recommend")
      ]);
      setLibrary(Array.isArray(books) ? books : []);
      setRecommendation(Array.isArray(recs) && recs.length > 0 ? recs[0] : null);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load dashboard");
      setLibrary([]);
      setRecommendation(null);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  const breakdown = useMemo(() => {
    if (!recommendation) return null;
    return buildScoreBreakdown(recommendation, library);
  }, [recommendation, library]);

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

      {loading && !recommendation ? (
        <p className="text-sm text-text-muted">Loading recommendation signals…</p>
      ) : null}

      {!loading && !recommendation && !error ? (
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

      {recommendation && breakdown ? (
        <>
          <RecommendedNextCard book={recommendation} breakdown={breakdown} />
          <ScoreBreakdownPanel breakdown={breakdown} />
        </>
      ) : null}

      <ReadingStats library={library} />
      <QuickActions />
    </div>
  );
}
