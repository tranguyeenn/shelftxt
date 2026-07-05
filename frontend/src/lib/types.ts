export type ReadingStatus = "not_started" | "reading" | "completed" | "dnf";
export type TrackingMode = "percentage" | "pages";

export type ApiBook = {
  id: string;
  title: string;
  author: string;
  cover_url?: string | null;
  status: ReadingStatus;
  total_pages: number | null;
  pages_read: number;
  estimated_pages_read?: number | null;
  progress_pct: number;
  tracking_mode: TrackingMode;
  rating?: number | null;
  read_status?: string;
  start_date?: string | null;
  end_date?: string | null;
  description?: string | null;
  genres?: string[];
  subjects?: string[];
  first_publish_year?: number | null;
  language?: string | null;
  page_count_checked?: boolean;
  page_count_source?: string | null;
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
  recommended_book?: Pick<ApiBook, "id" | "title" | "author" | "cover_url" | "description">;
  book: Pick<ApiBook, "id" | "title" | "author" | "cover_url" | "description">;
  score: number;
  reason?: string;
  explanation: string;
  matched_genres?: string[];
  matched_subjects?: string[];
  matched_authors?: string[];
  matched_liked_books?: MatchedLikedBook[];
  related_books?: MatchedLikedBook[];
  recommendation_reasons?: Array<{ label: string; detail: string }>;
  signals?: {
    genre_fit?: number | null;
    mood_match?: number | null;
    reader_similarity?: number | null;
    author_affinity?: number | null;
  };
  recommendation_breakdown?: {
    genre_fit?: number | null;
    genre_label?: string | null;
    mood_match?: number | null;
    reader_similarity?: number | null;
    author_affinity?: number | null;
    inspired_by?: MatchedLikedBook[];
  };
  score_breakdown?: Record<string, unknown>;
  similar_books: SimilarBook[];
};

export type BookProgressResponse = {
  book: ApiBook;
};
