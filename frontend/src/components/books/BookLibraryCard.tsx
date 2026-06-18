import { Link } from "react-router-dom";
import { useState } from "react";

import { BookEditModal } from "@/components/books/BookEditModal";
import { BookCoverPlaceholder } from "@/components/ui/BookCoverPlaceholder";
import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { Card } from "@/components/ui/Card";
import { ProgressBar } from "@/components/ui/ProgressBar";
import { BookDeleteButton } from "@/components/books/BookDeleteButton";
import { BookProgressEditor } from "@/components/books/BookProgressEditor";
import { statusLabel } from "@/lib/bookProgress";
import { isReadOnlyDemo } from "@/lib/demoMode";
import { formatDisplayDate } from "@/lib/books";
import type { ApiBook } from "@/lib/types";

type BookLibraryCardProps = {
  book: ApiBook;
  onUpdated: (book: ApiBook) => void;
  onDeleted?: (bookId: string) => void;
};

export function BookLibraryCard({ book, onUpdated, onDeleted }: BookLibraryCardProps) {
  const [editing, setEditing] = useState(false);
  const tone =
    book.status === "completed" ? "success" : book.status === "reading" ? "accent" : "neutral";

  return (
    <Card className="grid gap-4 md:grid-cols-[64px_1fr]">
      <BookCoverPlaceholder title={book.title} className="w-16" />
      <div className="grid gap-4">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="min-w-0">
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
        <div className="flex items-center gap-2">
          <Badge tone={tone}>{statusLabel(book.status)}</Badge>
          {!isReadOnlyDemo ? (
            <Button variant="ghost" onClick={() => setEditing(true)}>
              edit
            </Button>
          ) : null}
        </div>
      </div>

      <div className="max-w-lg">
        <ProgressBar value={book.progress_pct} />
      </div>

      <dl className="grid grid-cols-2 gap-3 text-sm sm:grid-cols-6">
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
        <div>
          <dt className="text-xs uppercase tracking-wide text-text-dim">Started</dt>
          <dd className="mt-1 text-text">{formatDisplayDate(book.start_date)}</dd>
        </div>
        <div>
          <dt className="text-xs uppercase tracking-wide text-text-dim">Finished</dt>
          <dd className="mt-1 text-text">{formatDisplayDate(book.end_date)}</dd>
        </div>
      </dl>

      <BookProgressEditor book={book} onUpdated={onUpdated} compact />

      <BookDeleteButton
        bookId={book.id}
        bookTitle={book.title}
        onDeleted={() => onDeleted?.(book.id)}
        compact
      />
      {editing ? (
        <BookEditModal
          book={book}
          onClose={() => setEditing(false)}
          onUpdated={onUpdated}
        />
      ) : null}
      </div>
    </Card>
  );
}
