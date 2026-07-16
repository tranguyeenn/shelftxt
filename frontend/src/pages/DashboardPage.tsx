import { useCallback, useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";

import { BookProgressEditor } from "@/components/books/BookProgressEditor";
import { PageHeader } from "@/components/layout/PageHeader";
import { BookCover } from "@/components/ui/BookCover";
import { Button } from "@/components/ui/Button";
import { Card } from "@/components/ui/Card";
import { EmptyState } from "@/components/ui/EmptyState";
import { ProgressBar } from "@/components/ui/ProgressBar";
import { StatCard } from "@/components/ui/StatCard";
import { useAuth } from "@/contexts/AuthContext";
import { useUserSettings } from "@/contexts/UserSettingsContext";
import { fetchJson } from "@/lib/api";
import {
  finishDateValue,
  formatDisplayDate,
  parseDate,
  recordToApiBook,
  type BookRecord
} from "@/lib/books";
import { displayProgressPercent, progressPercentValue, readingProgressSummary } from "@/lib/bookProgress";
import { dashboardAnnualGoalStat, dashboardSummaryLibrary, type DashboardSummary } from "@/lib/dashboardSummary";
import { loadCachedProfile, profileDisplayName } from "@/lib/profile";
import { stableRecommendationId, submitRecommendationFeedback } from "@/lib/recommendationFeedback";
import { recommendationMatchLabel } from "@/lib/recommendationDisplay";
import { recommendQuery } from "@/lib/userSettings";
import type { ApiBook, RecommendationItem } from "@/lib/types";

function timeBasedGreeting() {
  const hour = new Date().getHours();
  if (hour < 12) return "good morning";
  if (hour < 18) return "good afternoon";
  return "good evening";
}

export function primaryCurrentReadForDashboard(books: ApiBook[]) {
  return [...books]
    .filter((book) => book.status === "reading")
    .sort((a, b) => {
      const aDate = parseDate(a.start_date)?.getTime() ?? 0;
      const bDate = parseDate(b.start_date)?.getTime() ?? 0;
      return bDate - aDate || b.progress_pct - a.progress_pct || a.title.localeCompare(b.title);
    })[0] ?? null;
}

function recommendationBook(item: RecommendationItem) {
  return item.recommended_book ?? item.book;
}

export function DashboardPage() {
  const { user } = useAuth();
  const { settings } = useUserSettings();
  const [library, setLibrary] = useState<BookRecord[]>([]);
  const [recommendations, setRecommendations] = useState<RecommendationItem[]>([]);
  const [readingInsights, setReadingInsights] = useState<DashboardSummary | null>(null);
  const [summaryLoading, setSummaryLoading] = useState(true);
  const [recommendationsLoading, setRecommendationsLoading] = useState(true);
  const [error, setError] = useState("");
  const [feedbackMessage, setFeedbackMessage] = useState("");
  const [progressBook, setProgressBook] = useState<ApiBook | null>(null);

  const load = useCallback(async (refresh = false, excludeIds: string[] = []) => {
    setError("");
    setSummaryLoading(true);
    setRecommendationsLoading(true);

    void fetchJson<DashboardSummary>("/dashboard/summary", { skipClientCache: true })
      .then((summary) => {
        setReadingInsights(summary);
        setLibrary(dashboardSummaryLibrary(summary));
      })
      .catch((err) => {
        setError(err instanceof Error ? err.message : "Failed to load dashboard");
        setLibrary([]);
        setReadingInsights(null);
      })
      .finally(() => setSummaryLoading(false));

    void fetchJson<RecommendationItem[]>(recommendQuery(settings, refresh, excludeIds), {
      skipClientCache: refresh
    })
      .then((recs) => setRecommendations(Array.isArray(recs) ? recs : []))
      .catch(() => setRecommendations([]))
      .finally(() => setRecommendationsLoading(false));
  }, [settings.recommendationStyle]);

  useEffect(() => {
    void load();
  }, [load]);

  const books = useMemo(() => library.map(recordToApiBook), [library]);
  const current = primaryCurrentReadForDashboard(books);
  const keepGoing = books.filter((book) => book.status === "reading" && book.id !== current?.id);
  const profile = loadCachedProfile();
  const profileName = profileDisplayName(profile);
  const fallbackName = user?.email?.split("@")[0] || "reader";
  const greetingName = profileName === "Reader" ? fallbackName : profileName;
  const annualGoal = profile.readingGoal && profile.readingGoal > 0 ? profile.readingGoal : null;
  const annualGoalStat = dashboardAnnualGoalStat(readingInsights, annualGoal);
  const completedYearCount = readingInsights?.completed_this_year ?? 0;
  const recentCompleted = books
    .filter((book) => book.status === "completed" && parseDate(finishDateValue({
      Title: book.title,
      Authors: book.author,
      "ISBN/UID": book.id,
      "Read Status": book.read_status,
      "End Date": book.end_date
    })) !== null)
    .sort((a, b) => (parseDate(b.end_date)?.getTime() ?? 0) - (parseDate(a.end_date)?.getTime() ?? 0))
    .slice(0, 4);

  function refreshRecommendations() {
    const excludeIds = recommendations
      .map((item) => recommendationBook(item).id)
      .filter((id): id is string => Boolean(id));
    void load(true, excludeIds);
  }

  async function handleNotInterested(item: RecommendationItem) {
    const previous = recommendations;
    const key = recommendationKey(item);
    const index = previous.findIndex((candidate) => recommendationKey(candidate) === key);
    const currentIds = recommendations.slice(0, 10).map(stableRecommendationId);
    setRecommendations((current) => current.filter((candidate) => recommendationKey(candidate) !== key));
    setError("");
    try {
      const response = await submitRecommendationFeedback(
        item,
        "not_interested",
        currentIds,
        settings.recommendationStyle
      );
      setFeedbackMessage("Got it. We replaced that recommendation.");
      if (response.replacement) {
        setRecommendations((current) => {
          const next = [...current];
          next.splice(Math.max(0, index), 0, response.replacement as RecommendationItem);
          return dedupeRecommendations(next).slice(0, 10);
        });
      }
    } catch (err) {
      setRecommendations(previous);
      setFeedbackMessage("");
      setError(err instanceof Error ? err.message : "Failed to update recommendations");
      throw err;
    }
  }

  function handleProgressUpdated(updated: ApiBook) {
    setProgressBook(updated);
    setLibrary((prev) =>
      prev.map((record) => (recordToApiBook(record).id === updated.id ? apiBookToRecord(updated, record) : record))
    );
    void load(true);
  }

  return (
    <div className="grid gap-7">
      <PageHeader
        eyebrow="ShelfTXT"
        title={`${timeBasedGreeting()}, ${greetingName}.`}
        subtitle={current ? `Continue ${current.title}.` : "Pick up a current read or choose the next book for your shelf."}
        actions={
          <Button variant="secondary" onClick={refreshRecommendations} disabled={recommendationsLoading}>
            {recommendationsLoading ? "Refreshing..." : "Refresh"}
          </Button>
        }
      />

      {error ? (
        <div className="rounded-lg border border-danger/30 bg-danger-muted px-4 py-3 text-sm text-danger" role="alert">
          {error}
        </div>
      ) : null}

      {summaryLoading && books.length === 0 ? <p className="text-sm text-text-muted">Loading reading activity...</p> : null}
      {feedbackMessage ? <p className="text-sm text-text-muted" role="status">{feedbackMessage}</p> : null}

      <section className="grid gap-4 xl:grid-cols-[minmax(0,1fr)_340px]">
        {current ? (
          <CurrentReadingCard book={current} onUpdate={() => setProgressBook(current)} />
        ) : (
          <Card padding="lg" className="grid min-h-72 place-items-center">
            <EmptyState
              title="No current read yet."
              description="Mark a book as currently reading to make this your reading dashboard."
              action={
                <Link className="inline-flex rounded-lg bg-accent px-4 py-2 text-sm font-semibold text-on-accent hover:bg-accent-dim" to="/app/library">
                  Open library
                </Link>
              }
            />
          </Card>
        )}

        <div className="grid content-start gap-3 sm:grid-cols-2 xl:grid-cols-1">
          <StatCard
            label="current streak"
            value={`${readingInsights?.current_streak_days ?? 0} day${(readingInsights?.current_streak_days ?? 0) === 1 ? "" : "s"}`}
            hint={
              readingInsights?.has_reading_activity
                ? `Longest: ${readingInsights.longest_streak_days} days`
                : "Log reading progress to begin a streak."
            }
          />
          <StatCard
            label="pages today"
            value={`${readingInsights?.pages_read_today ?? 0}`}
            hint={readingInsights?.read_today ? "Recorded today" : "No reading logged today"}
          />
          <StatCard
            label="annual goal"
            value={annualGoalStat.value}
            hint={annualGoalStat.hint}
          />
          <StatCard
            label="books read this year"
            value={String(completedYearCount)}
            hint={`${(readingInsights?.pages_read_this_year ?? 0).toLocaleString()} pages from completed books`}
          />
        </div>
      </section>

      <section className="grid gap-4 lg:grid-cols-[minmax(0,1fr)_360px]">
        <Card className="grid gap-4">
          <div className="flex items-center justify-between gap-3">
            <h2 className="text-sm font-semibold uppercase text-text-dim">Keep going</h2>
            <Link to="/app/library" className="text-sm font-medium text-accent hover:text-accent-dim">
              Library
            </Link>
          </div>
          {keepGoing.length > 0 ? (
            <div className="grid gap-3">
              {keepGoing.slice(0, 4).map((book) => (
                <CompactReadingRow key={book.id} book={book} onUpdate={() => setProgressBook(book)} />
              ))}
            </div>
          ) : (
            <p className="text-sm text-text-muted">Other current reads will appear here.</p>
          )}
        </Card>

        <Card className="grid gap-4">
          <h2 className="text-sm font-semibold uppercase text-text-dim">Recent activity</h2>
          {recentCompleted.length > 0 ? (
            <div className="grid gap-3">
              {recentCompleted.map((book) => (
                <div key={book.id} className="text-sm">
                  <p className="font-medium text-text">Completed {book.title}</p>
                  <p className="text-text-muted">{formatDisplayDate(book.end_date)}</p>
                </div>
              ))}
            </div>
          ) : (
            <p className="text-sm text-text-muted">No completion activity found. Progress-update history is deferred until an activity model exists.</p>
          )}
        </Card>
      </section>

      <section className="grid gap-4">
        <div className="flex items-center justify-between gap-3">
          <h2 className="text-sm font-semibold uppercase text-text-dim">Recommendations</h2>
          <Link to="/app/discover" className="text-sm font-medium text-accent hover:text-accent-dim">
            Discover
          </Link>
        </div>
        {!recommendationsLoading && recommendations.length === 0 ? (
          <EmptyState
            title="No recommendation yet."
            description="Recommendations improve after you add books and rate completed reads."
          />
        ) : (
          <div className="grid gap-4 md:grid-cols-3">
            {recommendations.slice(0, 3).map((item) => (
              <RecommendationPreview
                key={recommendationKey(item)}
                item={item}
                onNotInterested={handleNotInterested}
              />
            ))}
          </div>
        )}
      </section>

      {progressBook ? (
        <div className="fixed inset-0 z-50 grid place-items-center bg-black/75 p-4">
          <div
            className="w-full max-w-2xl rounded-lg border border-border bg-bg-elevated p-5 shadow-card"
            role="dialog"
            aria-modal="true"
            aria-label={`Update progress for ${progressBook.title}`}
          >
            <div className="mb-4 flex items-start justify-between gap-4">
              <div>
                <p className="text-xs font-semibold uppercase text-accent-readable">Update progress</p>
                <h2 className="mt-1 text-xl font-semibold text-text">{progressBook.title}</h2>
              </div>
              <Button variant="ghost" onClick={() => setProgressBook(null)}>
                Close
              </Button>
            </div>
            <BookProgressEditor book={progressBook} onUpdated={handleProgressUpdated} />
          </div>
        </div>
      ) : null}
    </div>
  );
}

function CurrentReadingCard({ book, onUpdate }: { book: ApiBook; onUpdate: () => void }) {
  const progressPercent = progressPercentValue(book);
  return (
    <Card padding="lg" className="grid gap-5 overflow-hidden border-accent/20 bg-surface shadow-glow md:grid-cols-[160px_minmax(0,1fr)]">
      <BookCover title={book.title} coverUrl={book.cover_url} className="w-36 rounded-lg md:w-40" />
      <div className="grid min-w-0 content-between gap-5">
        <div className="min-w-0">
          <p className="text-xs font-semibold uppercase text-accent-readable">Currently reading</p>
          <h2 className="mt-2 line-clamp-2 text-3xl font-semibold leading-tight text-text md:text-4xl">{book.title}</h2>
          <p className="mt-2 text-text-muted">{book.author}</p>
        </div>
        <div className="grid gap-3">
          <div className="grid gap-2">
            <p className="text-sm text-text-muted">{readingProgressSummary(book)}</p>
            <div className="grid grid-cols-[minmax(0,1fr)_4.5rem] items-center gap-3">
              <ProgressBar value={progressPercent} />
              <p className="text-right font-mono text-2xl font-semibold text-text">
                {displayProgressPercent(book)}
              </p>
            </div>
          </div>
          <div className="flex flex-wrap gap-2">
            <Link className="inline-flex rounded-lg bg-accent px-4 py-2 text-sm font-semibold text-on-accent hover:bg-accent-dim" to={`/app/book/${encodeURIComponent(book.id)}`}>
              Continue
            </Link>
            <Button variant="secondary" onClick={onUpdate}>
              Update progress
            </Button>
          </div>
        </div>
      </div>
    </Card>
  );
}

function CompactReadingRow({ book, onUpdate }: { book: ApiBook; onUpdate: () => void }) {
  const progressPercent = progressPercentValue(book);
  return (
    <div className="grid grid-cols-[48px_minmax(0,1fr)_auto] items-center gap-3 rounded-lg border border-border-subtle bg-bg-elevated p-3">
      <BookCover title={book.title} coverUrl={book.cover_url} className="w-12 rounded-md" />
      <div className="min-w-0">
        <Link className="line-clamp-1 font-medium text-text hover:text-accent" to={`/app/book/${encodeURIComponent(book.id)}`}>
          {book.title}
        </Link>
        <p className="truncate text-xs text-text-muted">{book.author}</p>
        <div className="mt-2 grid grid-cols-[minmax(0,1fr)_3rem] items-center gap-2">
          <ProgressBar value={progressPercent} />
          <span className="text-right font-mono text-sm font-semibold text-text">
            {displayProgressPercent(book)}
          </span>
        </div>
      </div>
      <Button variant="ghost" className="px-3 py-1.5 text-xs" onClick={onUpdate}>
        Update
      </Button>
    </div>
  );
}

function RecommendationPreview({
  item,
  onNotInterested
}: {
  item: RecommendationItem;
  onNotInterested: (item: RecommendationItem) => Promise<void>;
}) {
  const [submittingFeedback, setSubmittingFeedback] = useState(false);
  const [feedbackError, setFeedbackError] = useState("");
  const book = recommendationBook(item);
  return (
    <Card className="grid gap-3">
      <div className="grid grid-cols-[72px_minmax(0,1fr)] gap-3">
        <BookCover title={book.title} coverUrl={book.cover_url} className="w-[72px] rounded-lg" />
        <div className="min-w-0">
          <p className="text-xs font-semibold text-accent-readable">{recommendationMatchLabel(item.score)}</p>
          <p className="mt-1 text-xs text-text-muted">{item.in_library ? "On your shelf" : "New discovery"}</p>
          <h3 className="mt-1 line-clamp-2 font-semibold text-text">{book.title}</h3>
          <p className="mt-1 truncate text-sm text-text-muted">{book.author}</p>
        </div>
      </div>
      <p className="line-clamp-3 text-sm text-text-muted">{item.reason || item.explanation}</p>
      <div className="flex flex-wrap gap-2">
        <Link className="text-sm font-medium text-accent hover:text-accent-dim" to="/app/discover">
          View recommendation
        </Link>
        <button
          type="button"
          disabled={submittingFeedback}
          aria-label={`Not interested in ${book.title}`}
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
          className="text-sm text-text-dim hover:text-text disabled:cursor-not-allowed disabled:opacity-50"
        >
          {submittingFeedback ? "Adjusting..." : "Not interested"}
        </button>
      </div>
      {feedbackError ? <p className="text-sm text-danger" role="alert">{feedbackError}</p> : null}
    </Card>
  );
}

function recommendationKey(item: RecommendationItem): string {
  return stableRecommendationId(item);
}

function dedupeRecommendations(items: RecommendationItem[]): RecommendationItem[] {
  const seen = new Set<string>();
  return items.filter((item) => {
    const key = recommendationKey(item);
    if (seen.has(key)) return false;
    seen.add(key);
    return true;
  });
}

function apiBookToRecord(book: ApiBook, previous: BookRecord): BookRecord {
  return {
    ...previous,
    Title: book.title,
    Authors: book.author,
    "ISBN/UID": book.id,
    "Read Status": book.status === "completed" ? "Read" : book.status === "not_started" ? "To-Read" : book.status,
    "Progress (%)": book.progress_pct,
    "Pages Read": book.pages_read,
    "Total Pages": book.total_pages,
    "Tracking Mode": book.tracking_mode,
    tracking_mode: book.tracking_mode,
    "Start Date": book.start_date,
    "End Date": book.end_date,
    cover_url: book.cover_url,
    "Cover URL": book.cover_url
  };
}
