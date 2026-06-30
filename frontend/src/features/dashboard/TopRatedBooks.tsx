import { Link } from "react-router-dom";

import { Badge } from "@/components/ui/Badge";
import { Card } from "@/components/ui/Card";
import { BookCover } from "@/components/ui/BookCover";
import { statusLabel } from "@/lib/bookProgress";
import { formatRating, getTopRatedBooks } from "@/lib/dashboardMetrics";
import type { BookRecord } from "@/lib/books";

type TopRatedBooksProps = {
  library: BookRecord[];
};

export function TopRatedBooks({ library }: TopRatedBooksProps) {
  const books = getTopRatedBooks(library);

  return (
    <Card className="grid content-start gap-4">
      <div>
        <p className="text-xs font-semibold uppercase tracking-wide text-text-dim">Shelf favorites</p>
        <h2 className="mt-1 text-lg font-semibold text-text">Top rated books</h2>
      </div>

      {books.length === 0 ? (
        <div className="rounded-lg border border-dashed border-border p-4">
          <p className="text-sm font-medium text-text">No rated books yet.</p>
          <p className="mt-1 text-xs text-text-muted">Ratings you save will surface your favorites here.</p>
        </div>
      ) : (
        <ol className="divide-y divide-border-subtle">
          {books.map((book, index) => (
            <li key={book.id} className="flex items-center gap-3 py-3 first:pt-0 last:pb-0">
              <span className="w-5 shrink-0 font-mono text-xs text-text-dim">{index + 1}</span>
              <BookCover title={book.title} coverUrl={book.coverUrl} className="w-9 shrink-0" />
              <div className="min-w-0 flex-1">
                <Link
                  to={`/app/book/${encodeURIComponent(book.id)}`}
                  className="block truncate text-sm font-medium text-text hover:text-accent"
                >
                  {book.title}
                </Link>
                <p className="truncate text-xs text-text-muted">{book.author}</p>
              </div>
              <div className="grid shrink-0 justify-items-end gap-1">
                <span className="text-sm font-medium text-score-rating">★ {formatRating(book.rating)}</span>
                <Badge tone={book.status === "completed" ? "success" : "neutral"}>
                  {statusLabel(book.status)}
                </Badge>
              </div>
            </li>
          ))}
        </ol>
      )}
    </Card>
  );
}
