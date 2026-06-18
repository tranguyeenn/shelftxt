import { Link } from "react-router-dom";

import { BookCoverPlaceholder } from "@/components/ui/BookCoverPlaceholder";
import { Card } from "@/components/ui/Card";
import { ProgressBar } from "@/components/ui/ProgressBar";
import type { ApiBook } from "@/lib/types";

type BookCardProps = {
  book: ApiBook;
};

export function BookCard({ book }: BookCardProps) {
  return (
    <Card padding="sm" className="grid min-w-44 gap-3">
      <BookCoverPlaceholder title={book.title} className="mx-auto w-20" />
      <div className="min-w-0">
        <Link
          to={`/book/${encodeURIComponent(book.id)}`}
          className="line-clamp-2 text-sm font-semibold text-text hover:text-accent"
        >
          {book.title}
        </Link>
        <p className="mt-1 truncate text-xs text-text-muted">{book.author}</p>
      </div>
      <ProgressBar value={book.progress_pct} />
      <p className="text-xs text-text-muted">{book.progress_pct.toFixed(0)}%</p>
    </Card>
  );
}
