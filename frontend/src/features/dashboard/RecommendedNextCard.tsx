import { useState } from "react";
import { Link } from "react-router-dom";

import { Badge } from "@/components/ui/Badge";
import { BookCover } from "@/components/ui/BookCover";
import { Card } from "@/components/ui/Card";
import { MoodTags } from "@/components/ui/MoodTags";
import {
  buildRecommendationReasons,
  recommendationMatchPercent,
  recommendationSignals,
  readerFacingExplanation
} from "@/lib/recommendationDisplay";
import type { RecommendationItem } from "@/lib/types";
import { openLibraryCoverUrl } from "@/lib/coverUrl";

type RecommendedNextCardProps = {
  item: RecommendationItem;
};

export function RecommendedNextCard({ item }: RecommendedNextCardProps) {
  const [showWhy, setShowWhy] = useState(false);
  const { book, score, matched_genres = [], matched_subjects = [] } = item;
  const match = recommendationMatchPercent(score);
  const tags = [...matched_genres, ...matched_subjects].slice(0, 5);
  const signals = recommendationSignals(item);
  const reasons = buildRecommendationReasons(item).slice(0, 3);
  const relatedBooks = (item.related_books ?? item.recommendation_breakdown?.inspired_by ?? item.matched_liked_books ?? []).slice(0, 3);
  const explanation = readerFacingExplanation(item);
  const description = book.description?.trim();

  return (
    <Card padding="md" className="grid gap-5 border-white/[0.08] bg-[#171719] lg:grid-cols-[112px_1fr]">
      <div className="mx-auto w-full max-w-[112px] lg:mx-0">
        <BookCover title={book.title} coverUrl={book.cover_url ?? openLibraryCoverUrl(book.id)} className="rounded-xl" />
      </div>
      <div className="grid gap-3">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div>
            <p className="mb-2 text-[11px] font-medium uppercase tracking-[0.12em] text-accent">Read next</p>
            <h2 className="font-serif text-2xl font-semibold leading-tight text-text">{book.title}</h2>
            <p className="mt-1 text-sm text-text-muted">{book.author}</p>
          </div>
          <div className="text-right">
            <p className="text-xs uppercase tracking-[0.08em] text-text-dim">Match</p>
            <p className="text-2xl font-semibold text-accent">{match}%</p>
            <Badge tone="success">Top pick</Badge>
          </div>
        </div>
        {description ? (
          <p className="line-clamp-3 text-sm leading-6 text-text-muted">{description}</p>
        ) : null}
        <section className="rounded-[14px] border border-border-subtle bg-bg-elevated p-4">
          <h3 className="text-sm font-semibold text-text">Why this book</h3>
          {reasons.length > 0 ? (
            <ul className="mt-3 grid gap-2 text-sm leading-6 text-text-muted">
              {reasons.map((reason) => (
                <li key={`${reason.label}-${reason.detail}`}>
                  <span className="font-medium text-text">{reason.label}:</span> {reason.detail}
                </li>
              ))}
            </ul>
          ) : (
            <p className="mt-3 text-sm leading-6 text-text-muted">{explanation}</p>
          )}
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
              to={`/app/book/${encodeURIComponent(book.id)}`}
              className="inline-flex items-center justify-center rounded-[14px] bg-accent px-4 py-2 text-sm font-semibold text-bg hover:bg-accent-dim"
            >
              Start reading
            </Link>
            <button
              type="button"
              onClick={() => setShowWhy((current) => !current)}
              className="inline-flex cursor-pointer items-center justify-center rounded-[14px] px-4 py-2 text-sm text-text-muted hover:bg-white/[0.05] hover:text-text"
            >
              Details
            </button>
          </div>
          {showWhy ? (
            <div className="mt-4 rounded-[14px] border border-border bg-surface p-4">
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
