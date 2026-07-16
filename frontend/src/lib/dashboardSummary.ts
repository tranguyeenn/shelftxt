import type { ReadingInsightsResponse } from "@/lib/readingInsights";
import { recordToApiBook, type BookRecord } from "@/lib/books";
import type { ApiBook } from "@/lib/types";

export type DashboardSummary = Pick<
  ReadingInsightsResponse,
  "current_streak_days" | "longest_streak_days" | "pages_read_today" | "has_reading_activity" | "read_today"
> & {
  current_books: BookRecord[];
  recent_completed: BookRecord[];
  completed_this_year: number;
  pages_read_this_year: number;
};

export function dashboardSummaryLibrary(summary: DashboardSummary): BookRecord[] {
  return [...(summary.current_books ?? []), ...(summary.recent_completed ?? [])];
}

export function dashboardSummaryBooks(summary: DashboardSummary): ApiBook[] {
  return dashboardSummaryLibrary(summary).map(recordToApiBook);
}

export function dashboardAnnualGoalStat(
  summary: Pick<DashboardSummary, "completed_this_year"> | null,
  annualGoal: number | null
): { value: string; hint: string } {
  const completedThisYear = summary?.completed_this_year ?? 0;
  if (annualGoal === null) {
    return { value: "Not set", hint: "Set a goal in Profile" };
  }
  return {
    value: `${completedThisYear} / ${annualGoal}`,
    hint: `${Math.round((completedThisYear / annualGoal) * 100)}% complete`
  };
}
