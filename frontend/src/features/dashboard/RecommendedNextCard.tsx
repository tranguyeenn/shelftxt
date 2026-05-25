import { Link } from "react-router-dom";

import { Badge } from "@/components/ui/Badge";
import { BookCoverPlaceholder } from "@/components/ui/BookCoverPlaceholder";
import { Card } from "@/components/ui/Card";
import { bookAuthor, bookId, bookTitle, type BookRecord } from "@/lib/books";
import { formatScore, type ScoreBreakdown } from "@/lib/scoring";

type RecommendedNextCardProps = {
  book: BookRecord;
  breakdown: ScoreBreakdown;
};

export function RecommendedNextCard({ book, breakdown }: RecommendedNextCardProps) {
  const title = bookTitle(book);
  const author = bookAuthor(book);
  const id = bookId(book);

  return (
    <Card padding="lg" className="grid gap-6 lg:grid-cols-[140px_1fr]">
      <div className="mx-auto w-full max-w-[140px] lg:mx-0">
        <BookCoverPlaceholder title={title} />
      </div>
      <div className="grid gap-4">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div>
            <h2 className="text-xl font-semibold text-text">{title}</h2>
            <p className="mt-1 text-sm text-text-muted">{author}</p>
          </div>
          <div className="text-right">
            <p className="font-mono text-xs uppercase tracking-wide text-text-dim">
              Recommendation score
            </p>
            <p className="font-mono text-3xl font-semibold text-accent">
              {formatScore(breakdown.composite)}
            </p>
            <Badge tone="success">{breakdown.matchLabel}</Badge>
          </div>
        </div>
        <section className="rounded-lg border border-border-subtle bg-bg-elevated p-4">
          <h3 className="text-sm font-medium text-text">Why this book?</h3>
          <p className="mt-2 text-sm leading-relaxed text-text-muted">
            You&apos;ll likely enjoy this based on your ratings, reading recency, and author
            preferences. The ranker sampled from your top TBR candidates weighted by author
            affinity and light randomness.
          </p>
          <div className="mt-4 flex flex-wrap gap-2">
            <Link
              to={`/book/${encodeURIComponent(id)}`}
              className="inline-flex items-center justify-center rounded-lg bg-accent px-4 py-2 text-sm font-medium text-bg hover:bg-accent-dim"
            >
              View full explanation
            </Link>
            <Link
              to="/ranking"
              className="inline-flex items-center justify-center rounded-lg px-4 py-2 text-sm text-text-muted hover:bg-surface hover:text-text"
            >
              See full TBR ranking
            </Link>
          </div>
        </section>
      </div>
    </Card>
  );
}
