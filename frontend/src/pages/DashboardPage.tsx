import { useCallback, useEffect, useState } from "react";
import { Link } from "react-router-dom";

import { PageHeader } from "@/components/layout/PageHeader";
import { BookCard } from "@/components/books/BookCard";
import { Button } from "@/components/ui/Button";
import { EmptyState } from "@/components/ui/EmptyState";
import { MiniVibeCard } from "@/components/ui/MiniVibeCard";
import { ReadingStats } from "@/features/dashboard/ReadingStats";
import { RecommendedNextCard } from "@/features/dashboard/RecommendedNextCard";
import { useAuth } from "@/contexts/AuthContext";
import { useUserSettings } from "@/contexts/UserSettingsContext";
import { fetchJson } from "@/lib/api";
import { fetchAllLibraryBooks, recordToApiBook, type BookRecord } from "@/lib/books";
import { loadCachedProfile, profileDisplayName } from "@/lib/profile";
import { recommendQuery } from "@/lib/userSettings";
import type { RecommendationItem } from "@/lib/types";

function timeBasedGreeting() {
  const hour = new Date().getHours();

  if (hour < 12) {
    return "good morning";
  }
  if (hour < 18) {
    return "good afternoon";
  }
  return "good evening";
}

export function DashboardPage() {
  const { user } = useAuth();
  const { settings } = useUserSettings();
  const [library, setLibrary] = useState<BookRecord[]>([]);
  const [recommendations, setRecommendations] = useState<RecommendationItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  const load = useCallback(async (refresh = false, excludeIds: string[] = []) => {
    setLoading(true);
    setError("");
    try {
      const [books, recs] = await Promise.all([
        fetchAllLibraryBooks(),
        fetchJson<RecommendationItem[]>(recommendQuery(settings, refresh, excludeIds), {
          skipClientCache: refresh
        })
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
  const tbrCount = library.filter((book) => recordToApiBook(book).status !== "completed").length;
  const reading = library.map(recordToApiBook).filter((book) => book.status === "reading").slice(0, 4);
  const profileName = profileDisplayName(loadCachedProfile());
  const fallbackName = user?.email?.split("@")[0] || "reader";
  const greetingName = (profileName === "Reader" ? fallbackName : profileName).toLowerCase();
  const greeting = timeBasedGreeting();

  function refreshRecommendations() {
    const excludeIds = recommendations
      .map((item) => (item.recommended_book ?? item.book).id)
      .filter(Boolean);
    void load(true, excludeIds);
  }

  return (
    <div className="grid gap-8">
      <PageHeader
        title={`${greeting}, ${greetingName}.`}
        subtitle={`you have ${tbrCount} books on your TBR.`}
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

      {loading && !topPick ? (
        <p className="text-sm text-text-muted">Loading recommendation signals…</p>
      ) : null}

      {!loading && !topPick && !error ? (
        <EmptyState
          title="Add more books to get recommendations."
          description="Rate completed books and keep your TBR up to date so ShelfTxt can suggest what to read next."
          action={
            <Link
              to="/app/add"
              className="inline-flex rounded-lg bg-accent px-4 py-2 text-sm font-medium text-bg hover:bg-accent-dim"
            >
              Add your first book
            </Link>
          }
        />
      ) : null}

      <div className="grid gap-6 lg:grid-cols-[1fr_260px]">
        <div className="grid gap-6">
          {topPick ? <RecommendedNextCard item={topPick} /> : null}

          <section className="grid gap-4">
            <div className="flex items-center justify-between gap-3">
              <h2 className="text-lg font-semibold text-text">continue reading</h2>
              <Link to="/app/library" className="text-sm text-accent hover:underline">
                library
              </Link>
            </div>
            {reading.length > 0 ? (
              <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
                {reading.map((book) => (
                  <BookCard key={book.id} book={book} />
                ))}
              </div>
            ) : (
              <p className="rounded-lg border border-border bg-surface p-4 text-sm text-text-muted">
                No books are marked currently reading.
              </p>
            )}
          </section>
        </div>
        <div className="grid content-start gap-4">
          <MiniVibeCard
            mood="late night reads"
            genre="indie folk"
            song="august - Taylor Swift"
            spotifyUrl="https://open.spotify.com/search/august%20Taylor%20Swift"
          />
          {recommendations.length > 1 ? (
            <Link
              to="/app/ranking"
              className="rounded-lg border border-border bg-bg-elevated p-4 text-sm text-text-muted transition-colors hover:border-accent hover:text-text"
            >
              View all recommendations
            </Link>
          ) : null}
        </div>
      </div>

      <ReadingStats library={library} />
    </div>
  );
}
