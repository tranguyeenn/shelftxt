import { fetchJson } from "@/lib/api";
import { recordToApiBook, type BookRecord } from "@/lib/books";
import type { ApiBook, ReadingStatus } from "@/lib/types";

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

export async function patchBookProgress(
  bookId: string,
  payload: { status: ReadingStatus; pages_read: number }
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
