import { Link } from "react-router-dom";

import { BookCover } from "@/components/ui/BookCover";
import { Card } from "@/components/ui/Card";
import { ProgressBar } from "@/components/ui/ProgressBar";
import { readingProgressLabel } from "@/lib/bookProgress";
import type { ApiBook } from "@/lib/types";

type BookCardProps = {
  book: ApiBook;
};

export function BookCard({ book }: BookCardProps) {
  return (
    <Card padding="sm" className="grid min-w-44 gap-3 border-white/[0.08] bg-[#171719]">
      <BookCover title={book.title} coverUrl={book.cover_url} className="mx-auto w-20 rounded-xl" />
      <div className="min-w-0">
        <Link
          to={`/app/book/${encodeURIComponent(book.id)}`}
          className="line-clamp-2 font-serif text-lg font-semibold leading-tight text-text hover:text-accent-dim"
        >
          {book.title}
        </Link>
        <p className="mt-1 truncate text-xs text-text-muted">{book.author}</p>
      </div>
      <ProgressBar value={book.progress_pct} />
      <p className="text-xs text-text-muted">{readingProgressLabel(book)}</p>
    </Card>
  );
}
