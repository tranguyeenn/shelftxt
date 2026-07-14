import { fetchJson } from "@/lib/api";

export type ReadingInsight = {
  type: string;
  label: string;
  value: string;
  detail?: string | null;
};

export type ReadingInsightsResponse = {
  profile_label: string;
  insights: ReadingInsight[];
  completed_books: number;
  unlock_threshold: number;
  status: "ready" | "insufficient_activity";
  message: string | null;
  current_streak_days: number;
  longest_streak_days: number;
  read_today: boolean;
  last_reading_date: string | null;
  pages_read_today: number;
  active_days_this_year: number;
  has_reading_activity: boolean;
};

export function fetchReadingInsights(): Promise<ReadingInsightsResponse> {
  return fetchJson<ReadingInsightsResponse>("/stats/reading-insights");
}
