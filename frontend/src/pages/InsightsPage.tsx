import { useCallback, useEffect, useMemo, useState, type ReactNode } from "react";
import { Link } from "react-router-dom";

import { PageHeader } from "@/components/layout/PageHeader";
import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { Card } from "@/components/ui/Card";
import { EmptyState } from "@/components/ui/EmptyState";
import { MonthlyBooksChart } from "@/components/ui/MonthlyBooksChart";
import { StatCard } from "@/components/ui/StatCard";
import { useUserSettings } from "@/contexts/UserSettingsContext";
import { fetchJson } from "@/lib/api";
import { recommendQuery } from "@/lib/userSettings";
import { pagesLabel, progressLabel, statusLabel } from "@/lib/bookProgress";
import { fetchAllLibraryBooks, type BookRecord } from "@/lib/books";
import {
  RECOMMENDATION_SIGNALS,
  completionYears,
  computeMonthlyCompletions,
  computeReadingPatterns,
  computeReadingSummary,
  currentlyReadingBooks,
  libraryHasGenre,
  topRecommendationThemes
} from "@/lib/insights";
import {
  fetchMetadataStatus,
  metadataStatusLabel,
  startMetadataGeneration,
  type MetadataStatus
} from "@/lib/metadata";
import type { RecommendationItem } from "@/lib/types";

function PatternCard({
  label,
  children
}: {
  label: string;
  children: ReactNode;
}) {
  return (
    <Card className="grid gap-2">
      <h3 className="text-xs font-semibold uppercase text-text-dim">{label}</h3>
      {children}
    </Card>
  );
}

export function InsightsPage() {
  const { settings } = useUserSettings();
  const [library, setLibrary] = useState<BookRecord[]>([]);
  const [recommendations, setRecommendations] = useState<RecommendationItem[]>([]);
  const [metadataStatus, setMetadataStatus] = useState<MetadataStatus | null>(null);
  const [metadataStarting, setMetadataStarting] = useState(false);
  const [selectedYear, setSelectedYear] = useState(() => new Date().getFullYear());
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  const load = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      const [books, recs, metadata] = await Promise.all([
        fetchAllLibraryBooks(),
        fetchJson<RecommendationItem[]>(recommendQuery(settings)),
        fetchMetadataStatus()
      ]);
      setLibrary(books);
      setRecommendations(Array.isArray(recs) ? recs : []);
      setMetadataStatus(metadata);
      if (metadata.total_books === 0) {
        setMetadataStarting(false);
      }
    } catch (err) {
      setLibrary([]);
      setRecommendations([]);
      setMetadataStatus(null);
      setError(err instanceof Error ? err.message : "Failed to load insights");
    } finally {
      setLoading(false);
    }
  }, [settings.recommendationStyle]);

  useEffect(() => {
    void load();
  }, [load]);

  const summary = useMemo(() => computeReadingSummary(library), [library]);
  const inProgress = useMemo(() => currentlyReadingBooks(library), [library]);
  const patterns = useMemo(() => computeReadingPatterns(library), [library]);
  const availableYears = useMemo(() => completionYears(library), [library]);
  const monthlyCompletions = useMemo(
    () => computeMonthlyCompletions(library, selectedYear),
    [library, selectedYear]
  );
  const themes = useMemo(() => topRecommendationThemes(recommendations), [recommendations]);
  const hasGenres = useMemo(() => libraryHasGenre(library), [library]);
  const hasNoBooks = (metadataStatus?.total_books ?? 0) === 0;
  const metadataBusy =
    !hasNoBooks &&
    (metadataStarting ||
      metadataStatus?.job.status === "pending" ||
      metadataStatus?.job.status === "processing");

  const avgRatingDisplay =
    summary.averageRating !== null ? `${summary.averageRating.toFixed(1)} / 5` : "—";

  async function handleGenerateMetadata() {
    setMetadataStarting(true);
    setError("");
    try {
      setMetadataStatus(await startMetadataGeneration());
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not start metadata generation");
    } finally {
      setMetadataStarting(false);
    }
  }

  return (
    <div className="grid gap-8">
      <PageHeader
        title="Stats"
        subtitle="Reading analytics for your library and habits."
      />

      {error ? (
        <div
          className="rounded-lg border border-danger/30 bg-danger-muted px-4 py-3 text-sm text-danger"
          role="alert"
        >
          {error}
        </div>
      ) : null}

      {loading ? <p className="text-sm text-text-muted">Loading your reading insights…</p> : null}

      {!loading && !error && library.length === 0 ? (
        <EmptyState
          title="No shelf data yet."
          description="Add a few books to see reading patterns and practical next-read signals."
          action={
            <Link
              to="/app/add"
              className="inline-flex rounded-lg bg-accent px-4 py-2 text-sm font-medium text-text hover:bg-accent-dim"
            >
              Add a book
            </Link>
          }
        />
      ) : null}

      {!loading && library.length > 0 ? (
        <>
          <section className="grid gap-3">
            <h2 className="text-sm font-medium text-text-dim">reading summary</h2>
            <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
              <StatCard label="books read" value={String(summary.completed)} />
              <StatCard
                label="pages read"
                value={summary.totalPagesRead.toLocaleString()}
                hint="Across all books in your library"
              />
              <StatCard
                label="average rating"
                value={avgRatingDisplay}
                hint={
                  summary.ratedCount > 0
                    ? `From ${summary.ratedCount} rated completed book${summary.ratedCount === 1 ? "" : "s"}`
                    : "No ratings on completed books yet"
                }
              />
              <StatCard label="on TBR" value={String(summary.notStarted + summary.reading)} />
            </div>
          </section>

          <section className="grid gap-3 lg:grid-cols-2">
            <Card className="grid gap-4">
              <div className="flex flex-wrap items-center justify-between gap-3">
                <h2 className="text-sm font-medium text-text">books read per month</h2>
                <label className="grid gap-1 text-xs text-text-dim">
                  <span className="sr-only">Chart year</span>
                  <select
                    value={selectedYear}
                    onChange={(event) => setSelectedYear(Number(event.target.value))}
                    className="rounded-lg border border-border bg-bg-elevated px-2 py-1 text-sm text-text"
                  >
                    {availableYears.map((year) => (
                      <option key={year} value={year}>
                        {year}
                      </option>
                    ))}
                  </select>
                </label>
              </div>
              <MonthlyBooksChart data={monthlyCompletions} />
            </Card>
            <Card className="grid gap-4">
              <h2 className="text-sm font-medium text-text">reading moods</h2>
              <EmptyState
                title="No reading mood data yet."
                description="Mood stats will appear when books have mood metadata."
              />
            </Card>
          </section>

          <section className="grid gap-3">
            <h2 className="text-sm font-medium text-text-dim">current progress</h2>
            {inProgress.length === 0 ? (
              <Card>
                <p className="text-sm text-text-muted">
                  You are not reading any books right now. Open your{" "}
                  <Link to="/app/library" className="text-accent hover:underline">
                    library
                  </Link>{" "}
                  to start one.
                </p>
              </Card>
            ) : (
              <div className="grid gap-3">
                {inProgress.map((book) => (
                  <Card key={book.id} className="grid gap-3 sm:grid-cols-[1fr_auto]">
                    <div>
                      <Link
                        to={`/app/book/${encodeURIComponent(book.id)}`}
                        className="text-base font-semibold text-text hover:text-accent hover:underline"
                      >
                        {book.title}
                      </Link>
                      <p className="mt-0.5 text-sm text-text-muted">{book.author}</p>
                      <p className="mt-2 font-mono text-sm text-text">
                        {pagesLabel(book)} · {progressLabel(book)}
                      </p>
                    </div>
                    <div className="flex items-start sm:justify-end">
                      <Badge tone="accent">{statusLabel("reading")}</Badge>
                    </div>
                  </Card>
                ))}
              </div>
            )}
          </section>

          <section className="grid gap-3">
            <h2 className="text-sm font-medium text-text-dim">genre distribution</h2>
            {!hasGenres ? (
              <Card className="grid gap-3 sm:grid-cols-[1fr_auto] sm:items-center">
                <div>
                  <p className="text-sm font-medium text-text">
                    Genre data has not been generated yet.
                  </p>
                  <p className="mt-1 text-sm text-text-muted">
                    {hasNoBooks
                      ? "No books to enrich"
                      : `Metadata Progress: ${metadataStatus?.job.processed_count ?? 0} / ${
                          metadataStatus?.job.total_count ?? 0
                        } books · ${metadataStatusLabel(metadataStatus?.job.status ?? "completed")}`}
                  </p>
                </div>
                <Button
                  variant="primary"
                  onClick={() => void handleGenerateMetadata()}
                  disabled={metadataBusy || hasNoBooks}
                >
                  {hasNoBooks ? "No books to enrich" : metadataBusy ? "Generating" : "Generate Metadata"}
                </Button>
              </Card>
            ) : null}
            <div className="grid gap-3 md:grid-cols-2">
              {patterns.map((pattern) => (
                <PatternCard key={pattern.label} label={pattern.label}>
                  {pattern.kind === "value" ? (
                    <>
                      <p className="text-lg font-semibold text-text">{pattern.value}</p>
                      {pattern.detail ? (
                        <p className="text-sm text-text-muted">{pattern.detail}</p>
                      ) : null}
                    </>
                  ) : (
                    <p className="text-sm text-text-muted">{pattern.message}</p>
                  )}
                </PatternCard>
              ))}
            </div>
          </section>

          <section className="grid gap-3">
            <h2 className="text-sm font-medium text-text-dim">recommendation signals</h2>
            <Card className="grid gap-3">
              <p className="text-sm text-text-muted">
                ShelfTxt learns from your own shelf — not from a generic bestseller list. Here is
                what shapes your picks:
              </p>
              <ul className="grid gap-2 text-sm text-text-muted">
                {RECOMMENDATION_SIGNALS.map((line) => (
                  <li key={line} className="flex gap-2">
                    <span className="text-accent" aria-hidden>
                      ·
                    </span>
                    <span>{line}</span>
                  </li>
                ))}
              </ul>
            </Card>
          </section>

          {themes.length > 0 ? (
            <section className="grid gap-3">
              <h2 className="text-sm font-medium text-text-dim">favorite authors in recommendations</h2>
              <Card className="grid gap-3">
                <p className="text-sm text-text-muted">
                  Common authors showing up in your current top recommendations:
                </p>
                <ul className="grid gap-2">
                  {themes.map((theme) => (
                    <li
                      key={theme.label}
                      className="flex items-center justify-between gap-3 text-sm"
                    >
                      <span className="text-text">{theme.label}</span>
                      <Badge tone="neutral">
                        {theme.count} book{theme.count === 1 ? "" : "s"}
                      </Badge>
                    </li>
                  ))}
                </ul>
              </Card>
            </section>
          ) : null}
        </>
      ) : null}
    </div>
  );
}
