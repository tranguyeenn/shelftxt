import { describe, expect, it } from "vitest";
import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";

import { StatCard } from "@/components/ui/StatCard";
import { primaryCurrentReadForDashboard } from "@/pages/DashboardPage";
import {
  dashboardAnnualGoalStat,
  dashboardSummaryBooks,
  type DashboardSummary
} from "@/lib/dashboardSummary";
import { displayProgressPercent, readingProgressSummary } from "@/lib/progressDisplay";

const baseSummary: DashboardSummary = {
  current_books: [
    {
      Title: "Percent Book",
      Authors: "Percent Author",
      "ISBN/UID": "percent-book",
      "Read Status": "to-read",
      "Progress (%)": 42,
      "Pages Read": 0,
      "Total Pages": null,
      "Tracking Mode": "percentage",
      tracking_mode: "percentage",
      "Start Date": "2026-07-01",
      cover_url: null,
      Genres: null,
      Subjects: null
    },
    {
      Title: "Pages Book",
      Authors: "Pages Author",
      "ISBN/UID": "pages-book",
      "Read Status": "to-read",
      "Progress (%)": null,
      "Pages Read": 120,
      "Total Pages": 300,
      "Tracking Mode": "pages",
      tracking_mode: "pages",
      "Start Date": "2026-07-02",
      "Cover URL": null,
      Genres: null,
      Subjects: null
    }
  ],
  recent_completed: [],
  completed_this_year: 1,
  pages_read_this_year: 320,
  current_streak_days: 0,
  longest_streak_days: 0,
  pages_read_today: 0,
  has_reading_activity: false,
  read_today: false
};

describe("dashboard summary contract", () => {
  it("reads current_books and keeps currently-reading cards renderable with null optional metadata", () => {
    const books = dashboardSummaryBooks(baseSummary);

    expect(books).toHaveLength(2);
    expect(books.every((book) => book.status === "reading")).toBe(true);
    expect(books[0]).toMatchObject({
      id: "percent-book",
      title: "Percent Book",
      author: "Percent Author",
      progress_pct: 42,
      tracking_mode: "percentage",
      cover_url: null
    });
    expect(books[1]).toMatchObject({
      id: "pages-book",
      title: "Pages Book",
      author: "Pages Author",
      pages_read: 120,
      total_pages: 300,
      tracking_mode: "pages",
      cover_url: null
    });
  });

  it("preserves dashboard primary-current sorting and progress for both tracking modes", () => {
    const books = dashboardSummaryBooks(baseSummary);

    expect(primaryCurrentReadForDashboard(books)?.id).toBe("pages-book");
    expect(readingProgressSummary(books[0])).toBe("42%");
    expect(displayProgressPercent(books[0])).toBe("42%");
    expect(readingProgressSummary(books[1])).toBe("120 / 300 pages");
    expect(displayProgressPercent(books[1])).toBe("40%");
  });

  it("renders annual goal progress from completed_this_year in the summary", () => {
    const summary = { ...baseSummary, completed_this_year: 31 };
    const stat = dashboardAnnualGoalStat(summary, 50);
    const html = renderToStaticMarkup(
      createElement(StatCard, { label: "annual goal", value: stat.value, hint: stat.hint })
    );

    expect(stat.value).toBe("31 / 50");
    expect(stat.hint).toBe("62% complete");
    expect(html).toContain("annual goal");
    expect(html).toContain("31 / 50");
    expect(html).toContain("62% complete");
  });
});
