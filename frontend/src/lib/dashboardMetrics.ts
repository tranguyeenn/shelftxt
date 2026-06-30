import {
  bookAuthor,
  bookId,
  bookTitle,
  finishDateValue,
  parseDate,
  recordToApiBook,
  starRating,
  type BookRecord
} from "@/lib/books";
import type { ReadingStatus } from "@/lib/types";
import { openLibraryCoverUrl } from "@/lib/coverUrl";

export type DashboardBook = {
  id: string;
  title: string;
  author: string;
  coverUrl: string | null;
  status: ReadingStatus;
  rating: number | null;
  finishDate: Date | null;
  finishDateValue: string | null;
};

export type ReadingMomentum = {
  currentlyReading: number;
  completedThisMonth: number;
  trackedPagesThisMonth: number;
  lastCompletedDate: Date | null;
};

function dashboardBook(book: BookRecord): DashboardBook {
  const finishValue = finishDateValue(book);
  const apiBook = recordToApiBook(book);
  return {
    id: bookId(book),
    title: bookTitle(book),
    author: bookAuthor(book),
    coverUrl: book.cover_url ?? book["Cover URL"] ?? openLibraryCoverUrl(bookId(book), "S"),
    status: apiBook.status,
    rating: starRating(book),
    finishDate: parseDate(finishValue),
    finishDateValue: finishValue
  };
}

function isSameMonth(date: Date, reference: Date): boolean {
  return date.getFullYear() === reference.getFullYear() && date.getMonth() === reference.getMonth();
}

export function formatRating(rating: number | null): string {
  if (rating === null) return "Unrated";
  return `${Number.isInteger(rating) ? rating.toFixed(0) : rating.toFixed(1)} / 5`;
}

export function getReadingMomentum(
  library: BookRecord[],
  now = new Date()
): ReadingMomentum {
  const completedThisMonth = library.filter((book) => {
    const apiBook = recordToApiBook(book);
    const finishDate = parseDate(finishDateValue(book));
    return apiBook.status === "completed" && finishDate !== null && isSameMonth(finishDate, now);
  });

  const activeStartedThisMonth = library.filter((book) => {
    const apiBook = recordToApiBook(book);
    const startDate = parseDate(apiBook.start_date);
    return apiBook.status === "reading" && startDate !== null && isSameMonth(startDate, now);
  });

  const completedPages = completedThisMonth.reduce((total, book) => {
    const apiBook = recordToApiBook(book);
    return total + (apiBook.total_pages ?? apiBook.pages_read ?? 0);
  }, 0);
  const activePages = activeStartedThisMonth.reduce(
    (total, book) => total + recordToApiBook(book).pages_read,
    0
  );

  const completionDates = library
    .filter((book) => recordToApiBook(book).status === "completed")
    .map((book) => parseDate(finishDateValue(book)))
    .filter((date): date is Date => date !== null && date <= now)
    .sort((a, b) => b.getTime() - a.getTime());

  return {
    currentlyReading: library.filter((book) => recordToApiBook(book).status === "reading").length,
    completedThisMonth: completedThisMonth.length,
    trackedPagesThisMonth: completedPages + activePages,
    lastCompletedDate: completionDates[0] ?? null
  };
}

export function getTopRatedBooks(library: BookRecord[], limit = 5): DashboardBook[] {
  return library
    .map(dashboardBook)
    .filter((book) => book.rating !== null)
    .sort((a, b) => {
      const ratingDifference = (b.rating ?? 0) - (a.rating ?? 0);
      if (ratingDifference !== 0) return ratingDifference;
      return (b.finishDate?.getTime() ?? 0) - (a.finishDate?.getTime() ?? 0);
    })
    .slice(0, limit);
}

export function getRecentlyFinishedBooks(library: BookRecord[], limit = 5): DashboardBook[] {
  return library
    .map(dashboardBook)
    .filter(
      (book) =>
        book.status === "completed" &&
        book.finishDate !== null &&
        book.finishDate.getTime() <= Date.now()
    )
    .sort((a, b) => (b.finishDate?.getTime() ?? 0) - (a.finishDate?.getTime() ?? 0))
    .slice(0, limit);
}
