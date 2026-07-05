import { fetchJson } from "@/lib/api";
import { recordToApiBook, type BookRecord } from "@/lib/books";
import type { ApiBook, ReadingStatus, TrackingMode } from "@/lib/types";

export type ProgressValidation = {
  valid: boolean;
  message?: string;
};

export function validatePagesRead(
  pagesRead: number,
  totalPages: number | null,
  status: ReadingStatus
): ProgressValidation {
  if (!Number.isFinite(pagesRead) || pagesRead < 0) {
    return { valid: false, message: "Pages read cannot be negative." };
  }
  if (
    (status === "reading" || status === "completed") &&
    (totalPages === null || totalPages <= 0)
  ) {
    return {
      valid: false,
      message: "Set total pages on this book before tracking progress."
    };
  }
  if (totalPages !== null && totalPages > 0 && pagesRead > totalPages) {
    return {
      valid: false,
      message: `Pages read cannot exceed total pages (${totalPages}).`
    };
  }
  if (status === "completed" && totalPages !== null && totalPages > 0 && pagesRead !== totalPages) {
    return {
      valid: false,
      message: `Mark completed by setting pages read to ${totalPages}.`
    };
  }
  return { valid: true };
}

export function validateTotalPages(totalPages: number | null): ProgressValidation {
  if (totalPages !== null && (!Number.isFinite(totalPages) || totalPages <= 0)) {
    return { valid: false, message: "Total pages must be positive or blank." };
  }
  return { valid: true };
}

export function validateProgressPercent(progressPercent: number): ProgressValidation {
  if (!Number.isFinite(progressPercent) || progressPercent < 0 || progressPercent > 100) {
    return { valid: false, message: "Progress must be between 0 and 100%." };
  }
  return { valid: true };
}

export function progressLabel(book: Pick<ApiBook, "status" | "progress_pct">): string {
  if (book.status === "completed" || book.progress_pct >= 100) return "100% complete";
  if (book.progress_pct > 0) return `${book.progress_pct.toFixed(0)}%`;
  return "Progress not set";
}

export function estimatedPagesRead(
  progressPercent: number,
  totalPages: number | null
): number | null {
  if (totalPages === null || !Number.isFinite(totalPages) || totalPages <= 0) return null;
  const clampedPercent = Math.min(100, Math.max(0, Number.isFinite(progressPercent) ? progressPercent : 0));
  return Math.min(totalPages, Math.max(0, Math.round((clampedPercent / 100) * totalPages)));
}

export function readingProgressLabel(
  book: Pick<ApiBook, "status" | "tracking_mode" | "progress_pct" | "pages_read" | "total_pages">
): string {
  if (book.tracking_mode === "pages") return pagesLabel(book);
  const percent = Math.min(100, Math.max(0, Number.isFinite(book.progress_pct) ? book.progress_pct : 0));
  const estimated = estimatedPagesRead(percent, book.total_pages);
  const percentLabel = `${Math.round(percent)}%`;
  if (estimated !== null && book.total_pages !== null) {
    return `${percentLabel} • approx. page ${estimated} of ${book.total_pages}`;
  }
  if (book.status === "completed" || percent >= 100) return "100% complete";
  return percent > 0 ? percentLabel : "Progress not set";
}

export function pagesLabel(book: Pick<ApiBook, "pages_read" | "total_pages">): string {
  if (book.total_pages !== null && book.total_pages > 0) {
    return `${book.pages_read ?? 0} / ${book.total_pages} pages`;
  }
  if ((book.pages_read ?? 0) > 0) return `${book.pages_read} pages read`;
  return "Pages not set";
}

export async function patchBookProgress(
  bookId: string,
  payload: {
    status?: ReadingStatus;
    read_status?: ReadingStatus;
    tracking_mode?: TrackingMode;
    pages_read?: number;
    total_pages?: number | null;
    progress_percent?: number;
    start_date?: string | null;
    end_date?: string | null;
  }
): Promise<ApiBook> {
  const encodedId = encodeURIComponent(bookId);
  const result = await fetchJson<BookRecord>(`/books/${encodedId}/progress`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload)
  });
  return recordToApiBook(result);
}

export function statusLabel(status: ReadingStatus): string {
  switch (status) {
    case "not_started":
      return "Not started";
    case "reading":
      return "Reading";
    case "completed":
      return "Completed";
    case "dnf":
      return "DNF";
  }
}
