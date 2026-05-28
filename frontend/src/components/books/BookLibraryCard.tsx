import { Link } from "react-router-dom";

import { Badge } from "@/components/ui/Badge";
import { Card } from "@/components/ui/Card";
import { BookDeleteButton } from "@/components/books/BookDeleteButton";
import { BookProgressEditor } from "@/components/books/BookProgressEditor";
import { statusLabel } from "@/lib/bookProgress";
import type { ApiBook } from "@/lib/types";

type BookLibraryCardProps = {
  book: ApiBook;
  onUpdated: (book: ApiBook) => void;
  onDeleted?: (bookId: string) => void;
};

export function BookLibraryCard({ book, onUpdated, onDeleted }: BookLibraryCardProps) {
  const tone =
    book.status === "completed" ? "success" : book.status === "reading" ? "accent" : "neutral";

  return (
    <Card className="grid gap-4">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h3 className="text-lg font-semibold text-text">
            <Link
              to={`/book/${encodeURIComponent(book.id)}`}
              className="hover:text-accent hover:underline"
            >
              {book.title}
            </Link>
          </h3>
          <p className="mt-1 text-sm text-text-muted">{book.author}</p>
        </div>
        <Badge tone={tone}>{statusLabel(book.status)}</Badge>
      </div>

      <dl className="grid grid-cols-2 gap-3 text-sm sm:grid-cols-4">
        <div>
          <dt className="text-xs uppercase tracking-wide text-text-dim">Total pages</dt>
          <dd className="mt-1 font-mono text-text">{book.total_pages ?? "—"}</dd>
        </div>
        <div>
          <dt className="text-xs uppercase tracking-wide text-text-dim">Pages read</dt>
          <dd className="mt-1 font-mono text-text">{book.pages_read}</dd>
        </div>
        <div>
          <dt className="text-xs uppercase tracking-wide text-text-dim">Progress</dt>
          <dd className="mt-1 font-mono text-text">{book.progress_pct.toFixed(0)}%</dd>
        </div>
        <div>
          <dt className="text-xs uppercase tracking-wide text-text-dim">Status</dt>
          <dd className="mt-1 text-text">{statusLabel(book.status)}</dd>
        </div>
      </dl>

      <BookProgressEditor book={book} onUpdated={onUpdated} compact />

      <BookDeleteButton
        bookId={book.id}
        bookTitle={book.title}
        onDeleted={() => onDeleted?.(book.id)}
        compact
      />
    </Card>
  );
}
