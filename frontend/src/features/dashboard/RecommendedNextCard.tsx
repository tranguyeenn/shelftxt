import { useState } from "react";
import { Link } from "react-router-dom";

import { Badge } from "@/components/ui/Badge";
import { BookCoverPlaceholder } from "@/components/ui/BookCoverPlaceholder";
import { Card } from "@/components/ui/Card";
import { MoodTags } from "@/components/ui/MoodTags";
import {
  recommendationMatchPercent,
  recommendationSignals,
  readerFacingExplanation
} from "@/lib/recommendationDisplay";
import type { RecommendationItem } from "@/lib/types";

type RecommendedNextCardProps = {
  item: RecommendationItem;
};

export function RecommendedNextCard({ item }: RecommendedNextCardProps) {
  const [showWhy, setShowWhy] = useState(false);
  const { book, score, matched_genres = [], matched_subjects = [] } = item;
  const match = recommendationMatchPercent(score);
  const tags = [...matched_genres, ...matched_subjects].slice(0, 5);
  const signals = recommendationSignals(item);
  const relatedBooks = (item.related_books ?? item.recommendation_breakdown?.inspired_by ?? item.matched_liked_books ?? []).slice(0, 3);
  const explanation = readerFacingExplanation(item);

  return (
    <Card padding="lg" className="grid gap-6 lg:grid-cols-[156px_1fr]">
      <div className="mx-auto w-full max-w-[140px] lg:mx-0">
        <BookCoverPlaceholder title={book.title} />
      </div>
      <div className="grid gap-4">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div>
            <p className="mb-2 text-xs font-medium lowercase text-text-dim">read next</p>
            <h2 className="text-xl font-semibold text-text">{book.title}</h2>
            <p className="mt-1 text-sm text-text-muted">{book.author}</p>
          </div>
          <div className="text-right">
            <p className="text-xs lowercase text-text-dim">match</p>
            <p className="text-3xl font-semibold text-accent">{match}%</p>
            <Badge tone="success">Top pick</Badge>
          </div>
        </div>
        <section className="rounded-lg border border-border-subtle bg-bg-elevated p-4">
          <h3 className="text-sm font-medium text-text">Why this book</h3>
          <p className="mt-3 text-sm leading-relaxed text-text-muted">{explanation}</p>
          {tags.length > 0 ? (
            <div className="mt-4">
              <MoodTags tags={tags} />
            </div>
          ) : null}
          {relatedBooks.length > 0 ? (
            <div className="mt-4">
              <p className="text-xs font-medium text-text-dim">Related books</p>
              <ul className="mt-2 grid gap-1 text-sm text-text-muted">
                {relatedBooks.map((book) => (
                  <li key={book.id || `${book.title}-${book.author}`}>{book.title}</li>
                ))}
              </ul>
            </div>
          ) : null}
          <div className="mt-4 flex flex-wrap gap-2">
            <Link
              to={`/book/${encodeURIComponent(book.id)}`}
              className="inline-flex items-center justify-center rounded-lg bg-accent px-4 py-2 text-sm font-medium text-text hover:bg-accent-dim"
            >
              start reading
            </Link>
            <button
              type="button"
              onClick={() => setShowWhy((current) => !current)}
              className="inline-flex cursor-pointer items-center justify-center rounded-lg px-4 py-2 text-sm text-text-muted hover:bg-surface hover:text-text"
            >
              why this book?
            </button>
          </div>
          {showWhy ? (
            <div className="mt-4 rounded-lg border border-border bg-surface p-4">
              <h4 className="text-sm font-medium text-text">Recommendation Breakdown</h4>
              <p className="mt-2 text-sm leading-relaxed text-text-muted">{explanation}</p>
              {signals.length > 0 ? (
                <dl className="mt-3 grid gap-3 text-sm sm:grid-cols-2">
                  {signals.map((signal) => (
                    <div key={signal.label}>
                      <dt className="text-text-dim">{signal.label}</dt>
                      <dd className="mt-1 text-text">{signal.display}</dd>
                    </div>
                  ))}
                </dl>
              ) : (
                <p className="mt-2 text-sm text-text-muted">ShelfTxt has a top pick, but not enough visible signals to explain it well yet.</p>
              )}
              {relatedBooks.length > 0 ? (
                <div className="mt-4 border-t border-border-subtle pt-4">
                  <p className="text-xs font-medium text-text-dim">Related books</p>
                  <ul className="mt-2 grid gap-1 text-sm text-text-muted">
                    {relatedBooks.map((book) => (
                      <li key={book.id || `${book.title}-${book.author}`}>{book.title}</li>
                    ))}
                  </ul>
                </div>
              ) : null}
            </div>
          ) : null}
        </section>
      </div>
    </Card>
  );
}
