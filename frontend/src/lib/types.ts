export type ReadingStatus = "not_started" | "reading" | "completed" | "dnf";
export type RecommendationLibraryStatus = ReadingStatus | "to-read" | "read" | "currently-reading";
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

export type RecommendationSource = "library" | "external" | "nyt" | "hardcover";

export type RecommendationBookRef = {
  id?: string | null;
  book_id?: number | string | null;
  external_id?: string | null;
  work_id?: string | null;
  edition_id?: string | null;
  isbn?: string | null;
  isbn_10?: string | null;
  isbn_13?: string | null;
  title: string;
  author: string;
  display_title?: string | null;
  original_title?: string | null;
  authors?: string[];
  cover_url?: string | null;
  description?: string | null;
  publication_year?: number | null;
  first_publish_year?: number | null;
  page_count?: number | null;
  total_pages?: number | null;
  publisher?: string | null;
  source_url?: string | null;
  source_urls?: string[];
  provider_source_id?: string | null;
  provider_rating?: number | null;
  rating?: number | null;
  ratings_count?: number | null;
  users_count?: number | null;
  activities_count?: number | null;
  language?: string | null;
  discovery_reason?: string | null;
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
  publication_year?: number | null;
  first_publish_year?: number | null;
  page_count?: number | null;
  total_pages?: number | null;
  publisher?: string | null;
  source_url?: string | null;
  source_urls?: string[];
  provider_source_id?: string | null;
  provider_rating?: number | null;
  rating?: number | null;
  ratings_count?: number | null;
  users_count?: number | null;
  activities_count?: number | null;
  language?: string | null;
  discovery_reason?: string | null;
  genres?: string[];
  subjects?: string[];
  score: number;
  final_score?: number;
  reader_likelihood_score?: number | null;
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
  external_id?: string | null;
  edition_id?: string | null;
  isbn?: string | null;
  isbn_10?: string | null;
  isbn_13?: string | null;
  canonical_title: string;
  canonical_author: string;
  book_id?: string | null;
  canonical_identity?: string | null;
  cover_url?: string | null;
  publication_year?: number | null;
  first_publish_year?: number | null;
  page_count?: number | null;
  total_pages?: number | null;
  publisher?: string | null;
  source_url?: string | null;
  source_urls?: string[];
  provider_source_id?: string | null;
  provider_rating?: number | null;
  rating?: number | null;
  ratings_count?: number | null;
  users_count?: number | null;
  activities_count?: number | null;
  language?: string | null;
  discovery_reason?: string | null;
  description?: string | null;
  series_name?: string | null;
  series_position?: number | null;
  series_position_label?: string | null;
  series_type?: string | null;
  series_source?: string | null;
  series_confidence?: number | null;
  score?: number | null;
  final_score?: number | null;
  reader_likelihood_score?: number | null;
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
    status: RecommendationLibraryStatus | null;
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
  broad_genre?: string | null;
  discovery_label?: string | null;
  nyt_rank?: number | null;
  nyt_rank_last_week?: number | null;
  nyt_weeks_on_list?: number | null;
  nyt_list_name?: string | null;
  nyt_list_name_encoded?: string | null;
  nyt_published_date?: string | null;
  nyt_bestsellers_date?: string | null;
  contributor?: string | null;
  cluster_id?: string | null;
  diagnostics?: Record<string, unknown>;
};

export type RecommendationSection = {
  id: string;
  type: "shelf_recommendations" | "popular_this_week" | "newly_found" | "cluster" | string;
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

export type RecommendationProviderStatus = {
  enabled?: boolean;
  available?: boolean;
  cached?: boolean;
  request_count?: number;
  error?: string;
};

export type RecommendationSectionsResponse = {
  schema_version: 3;
  sections?: RecommendationSection[];
  legacy_sections_deprecated?: boolean;
  shelf_recommendations: RecommendationSectionItem[];
  popular_this_week: RecommendationSectionItem[];
  newly_found: RecommendationSectionItem[];
  provider_status?: {
    nyt?: RecommendationProviderStatus;
    hardcover?: RecommendationProviderStatus;
  };
  discovery_diagnostics?: {
    nyt_request_count?: number;
    hardcover_query_count?: number;
    nyt_cache?: string;
    hardcover_cache?: string;
    weekly_popularity_supported?: boolean;
    popular_label?: string;
    popularity_basis?: string;
  };
  request_context?: {
    profile_id?: string | null;
    library_count?: number | null;
  };
  generated_at: string;
  style: string;
};

export type ExternalSectionReplaceResponse = {
  replacement: RecommendationSectionItem | null;
  provider_status?: RecommendationProviderStatus;
  remaining_candidate_count: number;
  reason?: string | null;
  diagnostics?: Record<string, unknown>;
};

export type PopularSectionRefreshResponse = {
  popular_this_week: RecommendationSectionItem[];
  provider_status?: RecommendationProviderStatus;
  remaining_candidate_count: number;
  diagnostics?: Record<string, unknown>;
};

export type NewlyFoundSectionRefreshResponse = {
  newly_found: RecommendationSectionItem[];
  provider_status?: RecommendationProviderStatus;
  remaining_candidate_count: number;
  diagnostics?: Record<string, unknown>;
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
