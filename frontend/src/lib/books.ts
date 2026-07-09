import { fetchJson } from "@/lib/api";
import { openLibraryCoverUrl } from "@/lib/coverUrl";
import type { ApiBook, ReadingStatus, TrackingMode } from "@/lib/types";

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
  "Start Date"?: string | null;
  "End Date"?: string | null;
  last_date_read?: string | null;
  start_date?: string | null;
  end_date?: string | null;
  "Progress (%)"?: number | null;
  "Pages Read"?: number | null;
  estimated_pages_read?: number | null;
  "Total Pages"?: number | null;
  "Tracking Mode"?: string | null;
  tracking_mode?: string | null;
  Description?: string | null;
  "Cover URL"?: string | null;
  cover_url?: string | null;
  Subjects?: string[] | string | null;
  Genres?: string[] | string | null;
  "First Publish Year"?: number | null;
  Language?: string | null;
  metadata_source?: string | null;
  metadata_enriched_at?: string | null;
  page_count_checked?: boolean;
  page_count_source?: string | null;
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

function trackingModeValue(book: BookRecord): TrackingMode {
  const raw = String(book.tracking_mode ?? book["Tracking Mode"] ?? "")
    .trim()
    .toLowerCase();
  if (raw === "percentage" || raw === "pages") return raw;
  return toNumber(book["Total Pages"]) !== null ? "pages" : "percentage";
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
    cover_url: book.cover_url ?? book["Cover URL"] ?? openLibraryCoverUrl(bookId(book)),
    status,
    total_pages: totalPages,
    pages_read: pagesRead,
    estimated_pages_read: toNumber(book.estimated_pages_read),
    progress_pct: progress,
    tracking_mode: trackingModeValue(book),
    rating: starRating(book),
    read_status: String(book["Read Status"] ?? ""),
    start_date: startDateValue(book),
    end_date: endDateValue(book),
    description: book.Description ?? null,
    genres: normalizeStringList(book.Genres),
    subjects: normalizeStringList(book.Subjects),
    first_publish_year: toNumber(book["First Publish Year"]),
    language: book.Language ?? null,
    page_count_checked: book.page_count_checked ?? false,
    page_count_source: book.page_count_source ?? null
  };
}

function normalizeStringList(value: string[] | string | null | undefined): string[] {
  const values = Array.isArray(value) ? value : String(value ?? "").split(/[,;|]/);
  return values.map((item) => String(item).trim()).filter(Boolean);
}

export type BookPatchPayload = {
  title: string;
  author: string;
  isbn_uid: string;
  total_pages: number | null;
  status: ReadingStatus;
  tracking_mode?: TrackingMode;
  pages_read?: number;
  progress_percent?: number;
  start_date?: string | null;
  end_date?: string | null;
  star_rating?: number | null;
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
  const text = String(value).trim();
  const isoDate = /^(\d{4})-(\d{1,2})-(\d{1,2})$/.exec(text);
  const ymdSlash = /^(\d{4})\/(\d{1,2})\/(\d{1,2})$/.exec(text);
  const mdySlash = /^(\d{1,2})\/(\d{1,2})\/(\d{4})$/.exec(text);
  if (isoDate) {
    return new Date(Number(isoDate[1]), Number(isoDate[2]) - 1, Number(isoDate[3]));
  }
  if (ymdSlash) {
    return new Date(Number(ymdSlash[1]), Number(ymdSlash[2]) - 1, Number(ymdSlash[3]));
  }
  if (mdySlash) {
    return new Date(Number(mdySlash[3]), Number(mdySlash[1]) - 1, Number(mdySlash[2]));
  }
  const d = new Date(text);
  return Number.isNaN(d.getTime()) ? null : d;
}

export function finishDateValue(book: BookRecord): string | null {
  return endDateValue(book) ?? book["Last Date Read"] ?? book.last_date_read ?? null;
}

export function startDateValue(book: BookRecord): string | null {
  return book["Start Date"] ?? book.start_date ?? null;
}

export function endDateValue(book: BookRecord): string | null {
  return book["End Date"] ?? book.end_date ?? null;
}

export function formatDisplayDateFromDate(date: Date | null | undefined): string {
  if (!date) return "—";
  return date.toLocaleDateString(undefined, {
    month: "short",
    day: "numeric",
    year: "numeric"
  });
}

export function formatDisplayDate(value: string | null | undefined): string {
  const date = parseDate(value);
  return formatDisplayDateFromDate(date);
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
