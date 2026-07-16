export type ReadingStatus = "not_started" | "reading" | "completed" | "dnf";
export type TrackingMode = "percentage" | "pages";

export type ApiBook = {
  id: string;
  title: string;
  author: string;
  display_title?: string | null;
  original_title?: string | null;
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

export type RecommendationSource = "library" | "external";

export type RecommendationBookRef = {
  id?: string | null;
  book_id?: number | string | null;
  external_id?: string | null;
  work_id?: string | null;
  edition_id?: string | null;
  isbn?: string | null;
  title: string;
  author: string;
  display_title?: string | null;
  original_title?: string | null;
  authors?: string[];
  cover_url?: string | null;
  description?: string | null;
  genres?: string[];
  subjects?: string[];
};

export type RecommendationItem = {
  recommendation_id?: string;
  recommended_book?: RecommendationBookRef;
  book: RecommendationBookRef;
  book_id?: number | string | null;
  external_id?: string | null;
  work_id?: string | null;
  edition_id?: string | null;
  isbn?: string | null;
  title?: string;
  author?: string;
  cover_url?: string | null;
  genres?: string[];
  subjects?: string[];
  score: number;
  final_score?: number;
  match_score?: number;
  qualitative_match_label?: string | null;
  in_library?: boolean;
  is_in_library?: boolean;
  source?: RecommendationSource;
  source_type?: "library" | "external_discovery";
  external_discovery?: boolean;
  discovery_source?: string | null;
  discovery_query?: string | null;
  discovery_cluster_id?: string | null;
  exploration_mode?: string | null;
  exploration_source?: string | null;
  novelty_score?: number | null;
  provider_rank?: number | null;
  provider?: string | null;
  library_status?: string | null;
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
  diagnostics?: Record<string, unknown>;
  similar_books: SimilarBook[];
};

export type RecommendationFacet = {
  label: string;
  score: number;
  candidate_count: number;
  external_candidate_count: number;
};

export type RecommendationFacetResponse = {
  items: RecommendationFacet[];
};

export type RecommendationSectionItem = {
  recommendation_id?: string;
  work_id: string;
  canonical_title: string;
  canonical_author: string;
  book_id?: string | null;
  canonical_identity?: string | null;
  cover_url?: string | null;
  series_name?: string | null;
  series_position?: number | null;
  series_position_label?: string | null;
  series_type?: string | null;
  series_source?: string | null;
  series_confidence?: number | null;
  score?: number | null;
  final_score?: number | null;
  match_percentage?: number | null;
  qualitative_match_label?: string | null;
  match_label: string;
  display_title?: string | null;
  original_title?: string | null;
  genres: string[];
  traits: string[];
  explanation: {
    primary_reason: string;
    related_books: SimilarBook[];
    shared_genres: string[];
    shared_traits: string[];
    style: string;
  };
  reader_explanation: string;
  library_state: {
    in_library: boolean;
    status: ReadingStatus | null;
    selected_edition_id: string | null;
  };
  in_library?: boolean;
  is_in_library?: boolean;
  source?: RecommendationSource;
  external_discovery?: boolean;
  discovery_source?: string | null;
  discovery_query?: string | null;
  discovery_cluster_id?: string | null;
  exploration_mode?: string | null;
  exploration_source?: string | null;
  novelty_score?: number | null;
  provider_rank?: number | null;
  score_breakdown?: Record<string, unknown>;
  provider?: string | null;
  cluster_id?: string | null;
  diagnostics?: Record<string, unknown>;
};

export type RecommendationSection = {
  id: string;
  type: string;
  title: string;
  reading_identity?: string;
  source_book: SimilarBook | null;
  items: RecommendationSectionItem[];
  why?: string;
  anchors?: AnchorBook[];
  dominant_genres?: string[];
  dominant_themes?: string[];
  cluster_size?: number;
  cluster_id?: string;
};

export type RecommendationSectionsResponse = {
  sections: RecommendationSection[];
  generated_at: string;
  style: string;
};

export type AnchorBook = {
  title: string;
  author: string;
  rating?: number | null;
  book_id?: string | null;
  work_id?: string | null;
  genres?: string[];
  subjects?: string[];
};

export type RecommendationCluster = {
  cluster_id: string;
  title: string;
  reading_identity?: string;
  why: string;
  anchors: AnchorBook[];
  dominant_genres: string[];
  dominant_themes: string[];
  cluster_size: number;
  recommendations: RecommendationSectionItem[];
};

export type RecommendationClustersResponse = RecommendationCluster[];

export type BookProgressResponse = {
  book: ApiBook;
};
