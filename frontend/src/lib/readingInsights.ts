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
};

export function fetchReadingInsights(): Promise<ReadingInsightsResponse> {
  return fetchJson<ReadingInsightsResponse>("/stats/reading-insights");
}
