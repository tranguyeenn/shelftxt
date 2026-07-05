import { Link } from "react-router-dom";

import { BookCoverPlaceholder } from "@/components/ui/BookCoverPlaceholder";
import { ProgressBar } from "@/components/ui/ProgressBar";
import { readingProgressLabel, statusLabel } from "@/lib/bookProgress";
import type { ApiBook } from "@/lib/types";

type BookRowProps = {
  book: ApiBook;
  actions?: React.ReactNode;
};

export function BookRow({ book, actions }: BookRowProps) {
  return (
    <div className="grid gap-4 rounded-lg border border-border bg-surface p-4 sm:grid-cols-[48px_1fr_auto] sm:items-center">
      <BookCoverPlaceholder title={book.title} className="w-12" />
      <div className="min-w-0">
        <Link
          to={`/book/${encodeURIComponent(book.id)}`}
          className="font-medium text-text hover:text-accent"
        >
          {book.title}
        </Link>
        <p className="mt-0.5 text-sm text-text-muted">{book.author}</p>
        <div className="mt-3 max-w-xs">
          <ProgressBar value={book.progress_pct} />
        </div>
      </div>
      <div className="flex flex-wrap items-center gap-3 text-sm text-text-muted sm:justify-end">
        <span>{statusLabel(book.status).toLowerCase()}</span>
        <span>{readingProgressLabel(book)}</span>
        {book.rating != null ? <span className="text-score-rating">{Number(book.rating).toFixed(1)}★</span> : null}
        {actions}
      </div>
    </div>
  );
}
