import { useCallback, useEffect, useMemo, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";

import { BookDeleteButton } from "@/components/books/BookDeleteButton";
import { BookEditModal } from "@/components/books/BookEditModal";
import { BookProgressEditor } from "@/components/books/BookProgressEditor";
import { PageHeader } from "@/components/layout/PageHeader";
import { Badge } from "@/components/ui/Badge";
import { BookCoverPlaceholder } from "@/components/ui/BookCoverPlaceholder";
import { Button } from "@/components/ui/Button";
import { Card } from "@/components/ui/Card";
import { EmptyState } from "@/components/ui/EmptyState";
import { ProgressBar } from "@/components/ui/ProgressBar";
import { useUserSettings } from "@/contexts/UserSettingsContext";
import { fetchJson } from "@/lib/api";
import { recommendQuery } from "@/lib/userSettings";
import { statusLabel } from "@/lib/bookProgress";
import { fetchAllLibraryBooks, formatDisplayDate, recordToApiBook, type BookRecord } from "@/lib/books";
import { isReadOnlyDemo } from "@/lib/demoMode";
import { readerFacingExplanation } from "@/lib/recommendationDisplay";
import type { ApiBook, RecommendationItem } from "@/lib/types";

export function BookDetailPage() {
  const navigate = useNavigate();
  const { settings } = useUserSettings();
  const { id } = useParams();
  const [, setLibrary] = useState<BookRecord[]>([]);
  const [recommendation, setRecommendation] = useState<RecommendationItem | null>(null);
  const [book, setBook] = useState<ApiBook | null>(null);
  const [editing, setEditing] = useState(false);
  const [activeTab, setActiveTab] = useState<"overview" | "details" | "reviews" | "quotes">("overview");
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
      const list = books;
      setLibrary(list);
      const decoded = decodeURIComponent(id ?? "");
      const match = list.map(recordToApiBook).find((item) => item.id === decoded) ?? null;
      setBook(match);
      const recList = Array.isArray(recs) ? recs : [];
      setRecommendation(recList.find((r) => r.book.id === decoded) ?? null);
    } catch (err) {
      setLibrary([]);
      setBook(null);
      setRecommendation(null);
      setError(err instanceof Error ? err.message : "Failed to load book detail");
    } finally {
      setLoading(false);
    }
  }, [id, settings.recommendationStyle]);

  useEffect(() => {
    void load();
  }, [load]);

  const ratingLabel = useMemo(() => {
    if (book?.rating == null) return "—";
    return Number(book.rating).toFixed(1);
  }, [book?.rating]);

  return (
    <div className="grid gap-6">
      <Link to="/library" className="text-sm text-accent hover:underline">
        ← Back to library
      </Link>
      <PageHeader
        title={book ? book.title : "Book detail"}
        subtitle={book ? book.author : `ID: ${decodeURIComponent(id ?? "")}`}
      />

      {error ? (
        <div
          className="rounded-lg border border-danger/30 bg-danger-muted px-4 py-3 text-sm text-danger"
          role="alert"
        >
          {error}
        </div>
      ) : null}

      {loading ? <p className="text-sm text-text-muted">Loading book details…</p> : null}

      {!loading && !error && !book ? (
        <EmptyState
          title="Book not found"
          description="This item may have been removed or re-imported with a different ID."
        />
      ) : null}

      {book ? (
        <>
          <Card padding="lg" className="grid gap-6 md:grid-cols-[156px_1fr]">
            <BookCoverPlaceholder title={book.title} className="w-full max-w-[156px]" />
            <div className="grid gap-5">
              <div>
                <h2 className="text-2xl font-semibold tracking-tight text-text">{book.title}</h2>
                <p className="mt-1 text-sm text-text-muted">{book.author}</p>
              </div>
              <div className="flex flex-wrap gap-2">
                <Badge tone="accent">{statusLabel(book.status)}</Badge>
                <Badge tone="warning">{ratingLabel === "—" ? "unrated" : `${ratingLabel} rating`}</Badge>
                <Badge tone="neutral">literary fiction</Badge>
                <Badge tone="neutral">contemporary</Badge>
              </div>
              <div className="grid gap-2">
                <ProgressBar
                  value={book.progress_pct}
                  label={`${book.pages_read} / ${book.total_pages ?? "—"} pages`}
                />
                <p className="text-sm text-text-muted">{book.progress_pct.toFixed(0)}% complete</p>
              </div>
              <div className="grid gap-3 sm:grid-cols-4">
                {(["overview", "details", "reviews", "quotes"] as const).map((tab) => (
                  <button
                    key={tab}
                    type="button"
                    onClick={() => setActiveTab(tab)}
                    className={[
                      "cursor-pointer rounded-lg px-3 py-2 text-sm transition-colors",
                      activeTab === tab
                        ? "bg-accent-muted text-accent"
                        : "text-text-muted hover:bg-surface-hover hover:text-text"
                    ].join(" ")}
                  >
                    {tab}
                  </button>
                ))}
              </div>
            </div>
          </Card>

          {!isReadOnlyDemo ? (
            <div>
              <Button variant="secondary" onClick={() => setEditing(true)}>
                Edit book
              </Button>
            </div>
          ) : null}

          <section className="grid gap-4 lg:grid-cols-[1fr_320px]">
            <Card className="grid gap-4">
              <h3 className="text-sm font-medium text-text">reading progress</h3>
              <BookProgressEditor
                book={book}
                onUpdated={(updated) => {
                  setBook(updated);
                  void load();
                }}
              />
              <dl className="grid grid-cols-2 gap-3 text-sm sm:grid-cols-4">
                <div>
                  <dt className="text-xs lowercase tracking-wide text-text-dim">started</dt>
                  <dd className="mt-1 text-text">{formatDisplayDate(book.start_date)}</dd>
                </div>
                <div>
                  <dt className="text-xs lowercase tracking-wide text-text-dim">finished</dt>
                  <dd className="mt-1 text-text">{formatDisplayDate(book.end_date)}</dd>
                </div>
                <div>
                  <dt className="text-xs lowercase tracking-wide text-text-dim">pages</dt>
                  <dd className="mt-1 text-text">{book.total_pages ?? "—"}</dd>
                </div>
                <div>
                  <dt className="text-xs lowercase tracking-wide text-text-dim">rating</dt>
                  <dd className="mt-1 text-score-rating">{ratingLabel}</dd>
                </div>
              </dl>
            </Card>

          <Card className="grid gap-3">
            {activeTab === "overview" ? (
              <>
                <h3 className="text-sm font-medium text-text">overview</h3>
                <p className="text-sm text-text-muted">
                  Track status, pages, dates, and recommendation context for this book.
                </p>
              </>
            ) : null}
            {activeTab === "details" ? (
              <>
                <h3 className="text-sm font-medium text-text">details</h3>
                <dl className="grid gap-3 text-sm sm:grid-cols-3">
                  <div>
                    <dt className="text-text-dim">status</dt>
                    <dd className="mt-1 text-text">{statusLabel(book.status)}</dd>
                  </div>
                  <div>
                    <dt className="text-text-dim">total pages</dt>
                    <dd className="mt-1 text-text">{book.total_pages ?? "—"}</dd>
                  </div>
                  <div>
                    <dt className="text-text-dim">rating</dt>
                    <dd className="mt-1 text-text">{ratingLabel}</dd>
                  </div>
                </dl>
              </>
            ) : null}
            {activeTab === "reviews" ? (
              <EmptyState title="No reviews saved yet." description="Reviews will appear here when review support is available." />
            ) : null}
            {activeTab === "quotes" ? (
              <EmptyState title="No quotes saved yet." description="Quotes will appear here when quote support is available." />
            ) : null}
          </Card>
            <div className="grid gap-4 content-start">
              <Card className="grid gap-3">
                <h3 className="text-sm font-medium text-text">mood</h3>
                <EmptyState
                  title="No mood tags yet."
                  description="Mood tags will appear when this book has mood metadata."
                />
              </Card>
              <Card className="grid gap-3">
                <h3 className="text-sm font-medium text-text">readers often listen to</h3>
                <EmptyState
                  title="No listening suggestions available."
                  description="Vibe suggestions will appear here when recommendation metadata includes music links."
                />
              </Card>
            </div>
          </section>

          {recommendation && settings.showRecommendationExplanations ? (
            <Card className="grid gap-3">
              <h3 className="text-sm font-medium text-text">Recommendation insight</h3>
              <p className="text-sm leading-relaxed text-text-muted">
                {readerFacingExplanation(recommendation)}
              </p>
              {(recommendation.related_books ?? recommendation.recommendation_breakdown?.inspired_by ?? recommendation.matched_liked_books ?? []).length > 0 ? (
                <div>
                  <p className="text-xs font-medium uppercase tracking-wide text-text-dim">Related books</p>
                  <ul className="mt-2 text-sm text-text-muted">
                    {(recommendation.related_books ?? recommendation.recommendation_breakdown?.inspired_by ?? recommendation.matched_liked_books ?? []).slice(0, 3).map((similar) => (
                      <li key={similar.id || `${similar.title}-${similar.author}`}>
                        {similar.title}
                      </li>
                    ))}
                  </ul>
                </div>
              ) : null}
            </Card>
          ) : null}

          <Card>
            <BookDeleteButton
              bookId={book.id}
              bookTitle={book.title}
              onDeleted={() => navigate("/library")}
            />
          </Card>
          {editing ? (
            <BookEditModal
              book={book}
              onClose={() => setEditing(false)}
              onUpdated={(updated) => {
                setBook(updated);
                void load();
              }}
            />
          ) : null}
        </>
      ) : null}
    </div>
  );
}
