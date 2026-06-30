import { fetchJson } from "@/lib/api";
import { recordToApiBook, type BookRecord } from "@/lib/books";
import type { ApiBook } from "@/lib/types";

type PageCountLookupApiResponse = {
  found: boolean;
  source: string;
  book: BookRecord;
};

export type PageCountLookupResult = {
  found: boolean;
  source: string;
  book: ApiBook;
};

export type PageCountBackfillResult = {
  processed: number;
  updated: number;
  unresolved: number;
};

export async function findBookPages(bookId: string): Promise<PageCountLookupResult> {
  const response = await fetchJson<PageCountLookupApiResponse>(
    `/books/${encodeURIComponent(bookId)}/pages/lookup`,
    { method: "POST" }
  );
  return { ...response, book: recordToApiBook(response.book) };
}

export function backfillMissingPages(limit = 50): Promise<PageCountBackfillResult> {
  return fetchJson<PageCountBackfillResult>(`/books/pages/backfill?limit=${limit}`, {
    method: "POST"
  });
}
