import { useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";

import { PageHeader } from "@/components/layout/PageHeader";
import { Badge } from "@/components/ui/Badge";
import { Card } from "@/components/ui/Card";
import { EmptyState } from "@/components/ui/EmptyState";
import { fetchJson } from "@/lib/api";
import { bookAuthor, bookId, bookTitle, type BookRecord } from "@/lib/books";
import { formatScore } from "@/lib/scoring";

export function RankingPage() {
  const [rows, setRows] = useState<BookRecord[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  useEffect(() => {
    let cancelled = false;

    async function load() {
      setLoading(true);
      setError("");
      try {
        const ranked = await fetchJson<BookRecord[]>("/recommend");
        if (!cancelled) {
          setRows(Array.isArray(ranked) ? ranked : []);
        }
      } catch (err) {
        if (!cancelled) {
          setRows([]);
          setError(err instanceof Error ? err.message : "Failed to load ranking");
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

  const topSlice = useMemo(() => rows.slice(0, 25), [rows]);

  return (
    <div className="grid gap-6">
      <PageHeader
        title="TBR Ranking"
        subtitle="Your To-Be-Read books ranked by recommendation score."
      />

      {error ? (
        <div
          className="rounded-lg border border-danger/30 bg-danger-muted px-4 py-3 text-sm text-danger"
          role="alert"
        >
          {error}
        </div>
      ) : null}

      {loading ? <p className="text-sm text-text-muted">Loading ranked candidates…</p> : null}

      {!loading && !error && topSlice.length === 0 ? (
        <EmptyState
          title="No ranked books yet"
          description="Add books with status “to-read”, then refresh the dashboard to generate recommendation candidates."
        />
      ) : null}

      {!loading && topSlice.length > 0 ? (
        <Card className="overflow-hidden" padding="sm">
          <div className="overflow-x-auto">
            <table className="min-w-full text-sm">
              <thead className="text-left text-xs uppercase tracking-wide text-text-dim">
                <tr>
                  <th className="px-3 py-2">Rank</th>
                  <th className="px-3 py-2">Title</th>
                  <th className="px-3 py-2">Author</th>
                  <th className="px-3 py-2">Score</th>
                  <th className="px-3 py-2">Details</th>
                </tr>
              </thead>
              <tbody>
                {topSlice.map((book, index) => {
                  const id = bookId(book);
                  const score = typeof book.score === "number" ? formatScore(book.score) : "—";
                  return (
                    <tr key={id} className="border-t border-border-subtle">
                      <td className="px-3 py-2 font-mono text-text-muted">{index + 1}</td>
                      <td className="px-3 py-2 text-text">{bookTitle(book)}</td>
                      <td className="px-3 py-2 text-text-muted">{bookAuthor(book)}</td>
                      <td className="px-3 py-2">
                        <Badge tone={index < 3 ? "success" : "neutral"}>{score}</Badge>
                      </td>
                      <td className="px-3 py-2">
                        <Link
                          to={`/book/${encodeURIComponent(id)}`}
                          className="text-accent hover:underline"
                        >
                          Open
                        </Link>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        </Card>
      ) : null}
    </div>
  );
}
