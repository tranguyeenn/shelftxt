import {
  bookAuthor,
  bookTitle,
  daysSince,
  finishDateValue,
  parseDate,
  recordToApiBook,
  starRating,
  type BookRecord
} from "@/lib/books";
import type { ApiBook, RecommendationItem } from "@/lib/types";

export type ReadingSummary = {
  totalBooks: number;
  completed: number;
  reading: number;
  notStarted: number;
  totalPagesRead: number;
  averageRating: number | null;
  ratedCount: number;
};

export type PatternInsight =
  | { kind: "value"; label: string; value: string; detail?: string }
  | { kind: "empty"; label: string; message: string };

function genreFromBook(book: BookRecord): string | null {
  const raw =
    (book as Record<string, unknown>).Genre ??
    (book as Record<string, unknown>).genre ??
    (book as Record<string, unknown>)["Book Genre"];
  const text = String(raw ?? "").trim();
  return text ? text : null;
}

export function libraryHasGenre(library: BookRecord[]): boolean {
  return library.some((book) => genreFromBook(book) !== null);
}

export function computeReadingSummary(library: BookRecord[]): ReadingSummary {
  const apiBooks = library.map(recordToApiBook);
  const completed = apiBooks.filter((b) => b.status === "completed").length;
  const reading = apiBooks.filter((b) => b.status === "reading").length;
  const notStarted = apiBooks.filter((b) => b.status === "not_started").length;

  const totalPagesRead = apiBooks.reduce((sum, book) => sum + (book.pages_read ?? 0), 0);

  const rated = library
    .filter((b) => recordToApiBook(b).status === "completed")
    .map((b) => starRating(b))
    .filter((r): r is number => r !== null);

  const averageRating =
    rated.length > 0 ? rated.reduce((a, b) => a + b, 0) / rated.length : null;

  return {
    totalBooks: library.length,
    completed,
    reading,
    notStarted,
    totalPagesRead,
    averageRating,
    ratedCount: rated.length
  };
}

export function currentlyReadingBooks(library: BookRecord[]): ApiBook[] {
  return library.map(recordToApiBook).filter((b) => b.status === "reading");
}

export function computeReadingPatterns(library: BookRecord[]): PatternInsight[] {
  const completed = library.filter((b) => recordToApiBook(b).status === "completed");
  const patterns: PatternInsight[] = [];

  if (libraryHasGenre(library)) {
    const genreCounts = new Map<string, number>();
    for (const book of completed) {
      const genre = genreFromBook(book);
      if (!genre) continue;
      genreCounts.set(genre, (genreCounts.get(genre) ?? 0) + 1);
    }
    if (genreCounts.size > 0) {
      const [topGenre, count] = [...genreCounts.entries()].sort((a, b) => b[1] - a[1])[0];
      patterns.push({
        kind: "value",
        label: "Favorite genre",
        value: topGenre,
        detail: `${count} completed book${count === 1 ? "" : "s"}`
      });
    } else {
      patterns.push({
        kind: "empty",
        label: "Favorite genre",
        message: "Genre is on your books, but none are marked completed yet."
      });
    }
  } else {
    patterns.push({
      kind: "empty",
      label: "Favorite genre",
      message: "Genre is not tracked in your library yet."
    });
  }

  if (completed.length > 0) {
    const authorCounts = new Map<string, number>();
    for (const book of completed) {
      const author = bookAuthor(book);
      authorCounts.set(author, (authorCounts.get(author) ?? 0) + 1);
    }
    const [topAuthor, count] = [...authorCounts.entries()].sort((a, b) => b[1] - a[1])[0];
    patterns.push({
      kind: "value",
      label: "Most read author",
      value: topAuthor,
      detail: `${count} completed book${count === 1 ? "" : "s"}`
    });
  } else {
    patterns.push({
      kind: "empty",
      label: "Most read author",
      message: "Finish a book to see which authors you read most."
    });
  }

  if (libraryHasGenre(library)) {
    const genreRatings = new Map<string, number[]>();
    for (const book of completed) {
      const genre = genreFromBook(book);
      const rating = starRating(book);
      if (!genre || rating === null) continue;
      const list = genreRatings.get(genre) ?? [];
      list.push(rating);
      genreRatings.set(genre, list);
    }
    if (genreRatings.size > 0) {
      const ranked = [...genreRatings.entries()]
        .map(([genre, ratings]) => ({
          genre,
          avg: ratings.reduce((a, b) => a + b, 0) / ratings.length
        }))
        .sort((a, b) => b.avg - a.avg);
      const top = ranked[0];
      patterns.push({
        kind: "value",
        label: "Highest rated genre",
        value: top.genre,
        detail: `${top.avg.toFixed(1)} / 5 average`
      });
    } else {
      patterns.push({
        kind: "empty",
        label: "Highest rated genre",
        message: "Rate completed books with genres to see this insight."
      });
    }
  } else {
    patterns.push({
      kind: "empty",
      label: "Highest rated genre",
      message: "Genre and ratings together are not available in your library yet."
    });
  }

  const finishDates = completed
    .map((b) => parseDate(finishDateValue(b)))
    .filter((d): d is Date => d !== null);

  if (finishDates.length > 0) {
    const mostRecent = finishDates.reduce((a, b) => (a > b ? a : b));
    const days = daysSince(mostRecent);
    const recentTitle =
      completed.find((b) => {
        const d = parseDate(finishDateValue(b));
        return d && d.getTime() === mostRecent.getTime();
      }) ?? completed[0];

    patterns.push({
      kind: "value",
      label: "Recent reading activity",
      value: days === 0 ? "Today" : `${days} day${days === 1 ? "" : "s"} ago`,
      detail: `Last finished: ${bookTitle(recentTitle)}`
    });
  } else {
    patterns.push({
      kind: "empty",
      label: "Recent reading activity",
      message: "Finish dates are not recorded for your completed books yet."
    });
  }

  return patterns;
}

export type RecommendationTheme = {
  label: string;
  count: number;
};

export function topRecommendationThemes(
  recommendations: RecommendationItem[],
  limit = 3
): RecommendationTheme[] {
  const authorCounts = new Map<string, number>();
  for (const item of recommendations) {
    const author = item.book.author.trim();
    if (!author) continue;
    authorCounts.set(author, (authorCounts.get(author) ?? 0) + 1);
  }

  return [...authorCounts.entries()]
    .sort((a, b) => b[1] - a[1])
    .slice(0, limit)
    .map(([label, count]) => ({ label, count }));
}

export const RECOMMENDATION_SIGNALS = [
  "Your recommendations are influenced by books you completed.",
  "Highly rated books have stronger impact on what we suggest next.",
  "Recent reads may affect your recommendations more.",
  "Books with similar authors, genres, or ratings may appear higher."
] as const;
