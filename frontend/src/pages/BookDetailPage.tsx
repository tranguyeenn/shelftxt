import { useEffect, useMemo, useState } from "react";
import { Link, useParams } from "react-router-dom";

import { PageHeader } from "@/components/layout/PageHeader";
import { Badge } from "@/components/ui/Badge";
import { Card } from "@/components/ui/Card";
import { EmptyState } from "@/components/ui/EmptyState";
import { ScoreBar } from "@/components/ui/ScoreBar";
import { fetchJson } from "@/lib/api";
import { bookAuthor, bookId, bookTitle, progressPct, type BookRecord } from "@/lib/books";
import { buildScoreBreakdown, formatScore } from "@/lib/scoring";

export function BookDetailPage() {
  const { id } = useParams();
  const [library, setLibrary] = useState<BookRecord[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  useEffect(() => {
    let cancelled = false;

    async function load() {
      setLoading(true);
      setError("");
      try {
        const books = await fetchJson<BookRecord[]>("/books");
        if (!cancelled) setLibrary(Array.isArray(books) ? books : []);
      } catch (err) {
        if (!cancelled) {
          setLibrary([]);
          setError(err instanceof Error ? err.message : "Failed to load book detail");
        }
      } finally {
        if (!cancelled) setLoading(false);
      }
    }

    void load();
    return () => {
      cancelled = true;
    };
  }, []);

  const book = useMemo(() => {
    const decoded = decodeURIComponent(id ?? "");
    return library.find((item) => bookId(item) === decoded) ?? null;
  }, [id, library]);

  const breakdown = useMemo(() => {
    if (!book) return null;
    return buildScoreBreakdown(book, library);
  }, [book, library]);

  const readStatus = String(book?.["Read Status"] ?? "unknown").trim() || "unknown";
  const rating =
    typeof book?.["Star Rating"] === "number" ? Number(book["Star Rating"]).toFixed(1) : "—";
  const pagesRead =
    typeof book?.["Pages Read"] === "number" ? String(Math.round(book["Pages Read"])) : "—";
  const totalPages =
    typeof book?.["Total Pages"] === "number" ? String(Math.round(book["Total Pages"])) : "—";

  return (
    <div className="grid gap-6">
      <Link to="/ranking" className="text-sm text-accent hover:underline">
        ← Back to TBR
      </Link>
      <PageHeader
        title={book ? bookTitle(book) : "Book detail"}
        subtitle={book ? bookAuthor(book) : `ID: ${decodeURIComponent(id ?? "")}`}
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

      {book && breakdown ? (
        <>
          <Card className="grid gap-4 md:grid-cols-2 lg:grid-cols-4">
            <div>
              <p className="text-xs uppercase tracking-wide text-text-dim">Status</p>
              <p className="mt-1 text-text">
                <Badge tone="accent">{readStatus}</Badge>
              </p>
            </div>
            <div>
              <p className="text-xs uppercase tracking-wide text-text-dim">Progress</p>
              <p className="mt-1 font-mono text-text">{progressPct(book).toFixed(0)}%</p>
            </div>
            <div>
              <p className="text-xs uppercase tracking-wide text-text-dim">Rating</p>
              <p className="mt-1 font-mono text-text">{rating}</p>
            </div>
            <div>
              <p className="text-xs uppercase tracking-wide text-text-dim">Pages</p>
              <p className="mt-1 font-mono text-text">
                {pagesRead} / {totalPages}
              </p>
            </div>
          </Card>

          <Card className="grid gap-4">
            <div className="flex items-center justify-between gap-3">
              <h3 className="text-sm font-medium text-text">Why this is recommended</h3>
              <Badge tone="success">{breakdown.matchLabel}</Badge>
            </div>
            <p className="text-sm text-text-muted">
              Composite score: <span className="font-mono text-text">{formatScore(breakdown.composite)}</span>
            </p>
            <div className="grid gap-3">
              {breakdown.factors.map((factor) => (
                <ScoreBar
                  key={factor.key}
                  label={factor.label}
                  value={factor.value}
                  weight={factor.weight}
                  color={factor.color}
                  explanation={factor.explanation}
                />
              ))}
            </div>
          </Card>
        </>
      ) : null}
    </div>
  );
}
