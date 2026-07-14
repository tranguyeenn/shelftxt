import type { ApiBook } from "@/lib/types";

type ProgressBook = Pick<ApiBook, "tracking_mode" | "progress_pct" | "pages_read" | "total_pages">;

export function clampPercent(value: number): number {
  if (!Number.isFinite(value)) return 0;
  return Math.min(100, Math.max(0, value));
}

export function progressPercentValue(book: ProgressBook): number {
  if (book.tracking_mode === "pages") {
    const totalPages = book.total_pages;
    if (totalPages !== null && Number.isFinite(totalPages) && totalPages > 0) {
      return clampPercent(((book.pages_read ?? 0) / totalPages) * 100);
    }
  }
  return clampPercent(book.progress_pct);
}

export function displayProgressPercent(book: ProgressBook): string {
  return `${Math.round(progressPercentValue(book))}%`;
}

export function readingProgressSummary(book: ProgressBook): string {
  if (book.tracking_mode === "pages") {
    if (book.total_pages !== null && book.total_pages > 0) {
      return `${book.pages_read ?? 0} / ${book.total_pages} pages`;
    }
    if ((book.pages_read ?? 0) > 0) return `${book.pages_read} pages read`;
  }
  return displayProgressPercent(book);
}
