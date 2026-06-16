import { useCallback, useEffect, useMemo, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";

import { BookDeleteButton } from "@/components/books/BookDeleteButton";
import { BookEditModal } from "@/components/books/BookEditModal";
import { BookProgressEditor } from "@/components/books/BookProgressEditor";
import { PageHeader } from "@/components/layout/PageHeader";
import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { Card } from "@/components/ui/Card";
import { EmptyState } from "@/components/ui/EmptyState";
import { useUserSettings } from "@/contexts/UserSettingsContext";
import { fetchJson } from "@/lib/api";
import { recommendQuery } from "@/lib/userSettings";
import { statusLabel } from "@/lib/bookProgress";
import { fetchAllLibraryBooks, recordToApiBook, type BookRecord } from "@/lib/books";
import { isReadOnlyDemo } from "@/lib/demoMode";
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
          <Card className="grid gap-4 md:grid-cols-2 lg:grid-cols-4">
            <div>
              <p className="text-xs uppercase tracking-wide text-text-dim">Status</p>
              <p className="mt-1 text-text">
                <Badge tone="accent">{statusLabel(book.status)}</Badge>
              </p>
            </div>
            <div>
              <p className="text-xs uppercase tracking-wide text-text-dim">Progress</p>
              <p className="mt-1 font-mono text-text">{book.progress_pct.toFixed(0)}%</p>
            </div>
            <div>
              <p className="text-xs uppercase tracking-wide text-text-dim">Rating</p>
              <p className="mt-1 font-mono text-text">{ratingLabel}</p>
            </div>
            <div>
              <p className="text-xs uppercase tracking-wide text-text-dim">Pages</p>
              <p className="mt-1 font-mono text-text">
                {book.pages_read} / {book.total_pages ?? "—"}
              </p>
            </div>
          </Card>

          {!isReadOnlyDemo ? (
            <div>
              <Button variant="secondary" onClick={() => setEditing(true)}>
                Edit book
              </Button>
            </div>
          ) : null}

          <BookProgressEditor
            book={book}
            onUpdated={(updated) => {
              setBook(updated);
              void load();
            }}
          />

          {recommendation && settings.showRecommendationExplanations ? (
            <Card className="grid gap-3">
              <h3 className="text-sm font-medium text-text">Recommendation insight</h3>
              <p className="text-sm leading-relaxed text-text-muted">{recommendation.explanation}</p>
              {recommendation.similar_books.length > 0 ? (
                <div>
                  <p className="text-xs font-medium uppercase tracking-wide text-text-dim">Similar to</p>
                  <ul className="mt-2 text-sm text-text-muted">
                    {recommendation.similar_books.map((similar) => (
                      <li key={similar.id || similar.title}>
                        {similar.title} — {similar.author}
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
