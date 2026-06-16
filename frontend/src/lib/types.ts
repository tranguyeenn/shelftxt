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

export type RecommendationItem = {
  book: Pick<ApiBook, "id" | "title" | "author">;
  score: number;
  explanation: string;
  similar_books: SimilarBook[];
};

export type BookProgressResponse = {
  book: ApiBook;
};
