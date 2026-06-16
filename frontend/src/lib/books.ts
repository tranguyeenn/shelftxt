import { fetchJson } from "@/lib/api";
import type { ApiBook, ReadingStatus } from "@/lib/types";

export type PaginatedBooksResponse = {
  page: number;
  limit: number;
  total: number;
  results: BookRecord[];
};

const LIBRARY_PAGE_LIMIT = 100;

export type BookRecord = {
  Title?: string | null;
  Authors?: string | null;
  "ISBN/UID"?: string | null;
  "Read Status"?: string | null;
  "Star Rating"?: number | null;
  "Last Date Read"?: string | null;
  "Progress (%)"?: number | null;
  "Pages Read"?: number | null;
  "Total Pages"?: number | null;
  score?: number | null;
  author_score?: number | null;
  rating_norm?: number | null;
  recency_norm?: number | null;
};

export type ShelfFilter = "all" | "unread" | "reading" | "completed";

export type DerivedShelf = "unread" | "reading" | "completed" | "dnf";

export function bookTitle(book: BookRecord): string {
  return String(book.Title ?? "").trim() || "Untitled";
}

export function bookAuthor(book: BookRecord): string {
  return String(book.Authors ?? "").trim() || "Unknown author";
}

export function bookId(book: BookRecord): string {
  const isbn = String(book["ISBN/UID"] ?? "").trim();
  if (isbn) return isbn;
  return `${bookTitle(book)}::${bookAuthor(book)}`;
}

function toNumber(value: unknown): number | null {
  if (value === null || value === undefined) return null;
  const parsed = Number(String(value).trim());
  return Number.isFinite(parsed) ? parsed : null;
}

export function progressPct(book: BookRecord): number {
  const p = toNumber(book["Progress (%)"]);
  return p === null ? 0 : Math.min(100, Math.max(0, p));
}

function statusNorm(s: string | null | undefined): string {
  return String(s ?? "")
    .trim()
    .toLowerCase();
}

export function recordToApiBook(book: BookRecord): ApiBook {
  const progress = progressPct(book);
  const pagesRead = toNumber(book["Pages Read"]) ?? 0;
  const totalPages = toNumber(book["Total Pages"]);
  const st = statusNorm(book["Read Status"]);
  let status: ReadingStatus = "not_started";
  if (st === "read") status = "completed";
  else if (st === "dnf") status = "dnf";
  else if (st === "to-read" && (progress > 0 || pagesRead > 0)) status = "reading";

  return {
    id: bookId(book),
    title: bookTitle(book),
    author: bookAuthor(book),
    status,
    total_pages: totalPages,
    pages_read: pagesRead,
    progress_pct: progress,
    rating: starRating(book),
    read_status: String(book["Read Status"] ?? "")
  };
}

export type BookPatchPayload = {
  title: string;
  author: string;
  isbn_uid: string;
  total_pages: number | null;
  status: ReadingStatus;
  pages_read: number;
};

export async function patchBook(bookId: string, payload: BookPatchPayload): Promise<ApiBook> {
  const encodedId = encodeURIComponent(bookId);
  const result = await fetchJson<BookRecord>(`/books/${encodedId}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload)
  });
  return recordToApiBook(result);
}

export function derivedShelf(book: BookRecord): DerivedShelf {
  const st = statusNorm(book["Read Status"]);
  const prog = progressPct(book);
  if (st === "dnf") return "dnf";
  if (st === "read") return "completed";
  if (st === "to-read" && prog > 0) return "reading";
  return "unread";
}

export function matchesShelfFilter(book: BookRecord, filter: ShelfFilter): boolean {
  if (filter === "all") return derivedShelf(book) !== "dnf";
  return derivedShelf(book) === filter;
}

export function starRating(book: BookRecord): number | null {
  return toNumber(book["Star Rating"]);
}

export function parseDate(value: string | null | undefined): Date | null {
  if (!value) return null;
  const d = new Date(value);
  return Number.isNaN(d.getTime()) ? null : d;
}

export function daysSince(date: Date): number {
  const ms = Date.now() - date.getTime();
  return Math.max(0, Math.floor(ms / (1000 * 60 * 60 * 24)));
}

/** Fetches all library pages (API max limit is 100 per request). */
export async function fetchAllLibraryBooks(): Promise<BookRecord[]> {
  const records: BookRecord[] = [];
  let page = 1;
  let total = 0;

  do {
    const res = await fetchJson<PaginatedBooksResponse>(
      `/books?page=${page}&limit=${LIBRARY_PAGE_LIMIT}`
    );
    if (!res || !Array.isArray(res.results)) {
      throw new Error("Invalid library response");
    }
    records.push(...res.results);
    total = res.total;
    page += 1;
  } while (records.length < total);

  return records;
}
