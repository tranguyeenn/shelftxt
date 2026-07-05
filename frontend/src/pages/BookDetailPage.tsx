import { useCallback, useEffect, useMemo, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";

import { BookDeleteButton } from "@/components/books/BookDeleteButton";
import { BookEditModal } from "@/components/books/BookEditModal";
import { BookProgressEditor } from "@/components/books/BookProgressEditor";
import { BookCover } from "@/components/ui/BookCover";
import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { Card } from "@/components/ui/Card";
import { EmptyState } from "@/components/ui/EmptyState";
import { ProgressBar } from "@/components/ui/ProgressBar";
import { StarRatingDisplay } from "@/components/ui/StarRatingDisplay";
import { useUserSettings } from "@/contexts/UserSettingsContext";
import { fetchJson } from "@/lib/api";
import { recommendQuery } from "@/lib/userSettings";
import { readingProgressLabel, statusLabel } from "@/lib/bookProgress";
import { fetchAllLibraryBooks, formatDisplayDate, recordToApiBook, type BookRecord } from "@/lib/books";
import { isReadOnlyDemo } from "@/lib/demoMode";
import { readerFacingExplanation } from "@/lib/recommendationDisplay";
import { cleanDisplaySubjects } from "@/lib/metadataDisplay";
import type { ApiBook, RecommendationItem } from "@/lib/types";

export function BookDetailPage() {
  const navigate = useNavigate();
  const { settings } = useUserSettings();
  const { id } = useParams();
  const [, setLibrary] = useState<BookRecord[]>([]);
  const [recommendation, setRecommendation] = useState<RecommendationItem | null>(null);
  const [book, setBook] = useState<ApiBook | null>(null);
  const [editing, setEditing] = useState(false);
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
    return Number(book.rating).toFixed(2).replace(/0+$/, "").replace(/\.$/, "");
  }, [book?.rating]);
  const description = book?.description?.trim() ?? "";

  const relatedBooks = useMemo(
    () =>
      recommendation
        ? (recommendation.related_books ??
            recommendation.recommendation_breakdown?.inspired_by ??
            recommendation.matched_liked_books ??
            [])
        : [],
    [recommendation]
  );
  const displaySubjects = useMemo(
    () => cleanDisplaySubjects(book?.subjects, book?.genres),
    [book?.subjects, book?.genres]
  );

  return (
    <div className="grid gap-6">
      <Link to="/app/library" className="text-sm text-accent hover:underline">
        ← Back to library
      </Link>
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
          <Card padding="lg" className="grid gap-6 md:grid-cols-[180px_1fr]">
            <BookCover
              title={book.title}
              coverUrl={book.cover_url}
              className="mx-auto w-full max-w-[180px] shadow-card md:mx-0"
            />
            <div className="flex min-w-0 flex-col justify-between gap-6">
              <div className="flex flex-wrap items-start justify-between gap-4">
                <div className="min-w-0">
                  <div className="flex flex-wrap gap-2">
                    <Badge tone={book.status === "completed" ? "success" : "accent"}>
                      {statusLabel(book.status)}
                    </Badge>
                    <Badge tone={book.rating == null ? "neutral" : "warning"}>
                      {book.rating == null ? "Unrated" : `${ratingLabel} stars`}
                    </Badge>
                  </div>
                  <h2 className="mt-4 font-serif text-3xl font-semibold leading-tight text-text sm:text-4xl">
                    {book.title}
                  </h2>
                  <p className="mt-2 text-base text-text-muted">by {book.author}</p>
                </div>
                {!isReadOnlyDemo ? (
                  <Button variant="secondary" onClick={() => setEditing(true)}>
                    Edit book
                  </Button>
                ) : null}
              </div>
              <div className="grid gap-2">
                <ProgressBar value={book.progress_pct} label={readingProgressLabel(book)} />
                <div className="flex flex-wrap justify-between gap-2 text-sm text-text-muted">
                  <span>{statusLabel(book.status)}</span>
                  <span>{readingProgressLabel(book)}</span>
                </div>
              </div>
            </div>
          </Card>

          <section className="grid gap-4 lg:grid-cols-[minmax(0,1fr)_360px]">
            <div className="grid content-start gap-4">
              {description ? (
                <Card className="grid gap-4">
                  <div>
                    <p className="text-xs font-semibold uppercase tracking-wide text-accent">
                      About the book
                    </p>
                    <h3 className="mt-1 font-serif text-2xl font-semibold text-text">Description</h3>
                  </div>
                  <p className="text-sm leading-7 text-text-muted">{description}</p>
                </Card>
              ) : null}

              <Card className="grid gap-5">
                <div>
                  <p className="text-xs font-semibold uppercase tracking-wide text-text-dim">
                    Edition data
                  </p>
                  <h3 className="mt-1 text-lg font-semibold text-text">Book details</h3>
                </div>
                {(book.genres?.length ?? 0) > 0 ? (
                  <div className="flex flex-wrap gap-2">
                    {book.genres?.map((genre) => (
                      <Badge key={genre} tone="neutral">
                        {genre}
                      </Badge>
                    ))}
                  </div>
                ) : null}
                <dl className="grid gap-x-6 gap-y-4 text-sm sm:grid-cols-2">
                  <MetadataItem label="ISBN / UID" value={book.id} />
                  <MetadataItem label="Pages" value={book.total_pages?.toLocaleString() ?? "—"} />
                  <MetadataItem
                    label="First published"
                    value={book.first_publish_year?.toString() ?? "—"}
                  />
                  <MetadataItem label="Started" value={formatDisplayDate(book.start_date)} />
                  <MetadataItem label="Finished" value={formatDisplayDate(book.end_date)} />
                </dl>
                {displaySubjects.length > 0 ? (
                  <div className="border-t border-border-subtle pt-4">
                    <p className="text-xs font-medium uppercase tracking-wide text-text-dim">
                      Subjects
                    </p>
                    <p className="mt-2 text-sm leading-6 text-text-muted">
                      {displaySubjects.join(" · ")}
                    </p>
                  </div>
                ) : null}
              </Card>
            </div>

            <aside className="grid content-start gap-4">
              <Card className="grid gap-4">
                <div>
                  <p className="text-xs font-semibold uppercase tracking-wide text-text-dim">
                    Reading log
                  </p>
                  <h3 className="mt-1 text-lg font-semibold text-text">Status and progress</h3>
                </div>
                <BookProgressEditor
                  book={book}
                  onUpdated={(updated) => {
                    setBook(updated);
                    void load();
                  }}
                />
              </Card>
              <Card>
                <dl className="grid grid-cols-2 gap-4 text-sm">
                  <MetadataItem label="Status" value={statusLabel(book.status)} />
                  <div className="min-w-0">
                    <dt className="text-xs uppercase tracking-wide text-text-dim">Rating</dt>
                    <dd className="mt-1">
                      <StarRatingDisplay value={book.rating ?? null} size="sm" showValue />
                    </dd>
                  </div>
                  <MetadataItem label="Progress" value={readingProgressLabel(book)} />
                </dl>
              </Card>
            </aside>
          </section>

          {recommendation && settings.showRecommendationExplanations ? (
            <Card className="grid gap-3">
              <h3 className="text-sm font-medium text-text">Recommendation insight</h3>
              <p className="text-sm leading-relaxed text-text-muted">
                {readerFacingExplanation(recommendation)}
              </p>
              {relatedBooks.length > 0 ? (
                <div>
                  <p className="text-xs font-medium uppercase text-text-dim">Related books</p>
                  <ul className="mt-2 text-sm text-text-muted">
                    {relatedBooks.slice(0, 3).map((similar) => (
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
              onDeleted={() => navigate("/app/library")}
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

function MetadataItem({
  label,
  value,
  accent = false
}: {
  label: string;
  value: string;
  accent?: boolean;
}) {
  return (
    <div className="min-w-0">
      <dt className="text-xs uppercase tracking-wide text-text-dim">{label}</dt>
      <dd className={`mt-1 break-words ${accent ? "text-score-rating" : "text-text"}`}>{value}</dd>
    </div>
  );
}
