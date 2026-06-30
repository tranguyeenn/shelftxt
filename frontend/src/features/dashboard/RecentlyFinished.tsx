import { Link } from "react-router-dom";

import { Card } from "@/components/ui/Card";
import { BookCover } from "@/components/ui/BookCover";
import { formatDisplayDate, type BookRecord } from "@/lib/books";
import { formatRating, getRecentlyFinishedBooks } from "@/lib/dashboardMetrics";

type RecentlyFinishedProps = {
  library: BookRecord[];
};

export function RecentlyFinished({ library }: RecentlyFinishedProps) {
  const books = getRecentlyFinishedBooks(library);

  return (
    <Card className="grid content-start gap-4">
      <div className="flex items-end justify-between gap-3">
        <div>
          <p className="text-xs font-semibold uppercase tracking-wide text-text-dim">Reading history</p>
          <h2 className="mt-1 text-lg font-semibold text-text">Recently finished</h2>
        </div>
        <Link to="/app/library" className="text-xs text-accent hover:underline">
          View library
        </Link>
      </div>

      {books.length === 0 ? (
        <div className="rounded-lg border border-dashed border-border p-4">
          <p className="text-sm font-medium text-text">No dated finishes yet.</p>
          <p className="mt-1 text-xs text-text-muted">Completed books with a finish date will appear here.</p>
        </div>
      ) : (
        <ul className="divide-y divide-border-subtle">
          {books.map((book) => (
            <li key={book.id} className="flex items-center gap-3 py-3 first:pt-0 last:pb-0">
              <BookCover title={book.title} coverUrl={book.coverUrl} className="w-9 shrink-0" />
              <div className="min-w-0">
                <Link
                  to={`/app/book/${encodeURIComponent(book.id)}`}
                  className="block truncate text-sm font-medium text-text hover:text-accent"
                >
                  {book.title}
                </Link>
                <p className="truncate text-xs text-text-muted">{book.author}</p>
              </div>
              <div className="ml-auto shrink-0 text-right">
                <p className="text-xs text-text">{formatDisplayDate(book.finishDateValue)}</p>
                {book.rating !== null ? (
                  <p className="mt-1 text-xs text-score-rating">★ {formatRating(book.rating)}</p>
                ) : null}
              </div>
            </li>
          ))}
        </ul>
      )}
    </Card>
  );
}
