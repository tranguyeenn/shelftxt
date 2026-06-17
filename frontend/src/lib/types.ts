export type ReadingStatus = "not_started" | "reading" | "completed" | "dnf";

export type ApiBook = {
  id: string;
  title: string;
  author: string;
  status: ReadingStatus;
  total_pages: number | null;
  pages_read: number;
  progress_pct: number;
  rating?: number | null;
  read_status?: string;
  start_date?: string | null;
  end_date?: string | null;
};

export type SimilarBook = {
  id: string;
  title: string;
  author: string;
};

export type MatchedLikedBook = SimilarBook & {
  rating?: number | null;
};

export type RecommendationItem = {
  recommended_book?: Pick<ApiBook, "id" | "title" | "author">;
  book: Pick<ApiBook, "id" | "title" | "author">;
  score: number;
  reason?: string;
  explanation: string;
  matched_genres?: string[];
  matched_subjects?: string[];
  matched_authors?: string[];
  matched_liked_books?: MatchedLikedBook[];
  score_breakdown?: Record<string, unknown>;
  similar_books: SimilarBook[];
};

export type BookProgressResponse = {
  book: ApiBook;
};
