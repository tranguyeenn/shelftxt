import unittest

import numpy as np
import pandas as pd

from backend.services.recommendation_builder import (
    _select_reason_anchor,
    build_recommendations,
)
from backend.services.recommendation import recommendation_sections_response


class RecommendationBuilderTests(unittest.TestCase):
    def test_build_recommendations_returns_top_structured_items(self):
        df = pd.DataFrame(
            [
                {
                    "Title": "Read A",
                    "Authors": "Loved Author",
                    "ISBN/UID": "r1",
                    "Read Status": "read",
                    "Star Rating": 5.0,
                    "Last Date Read": "2024-01-01",
                    "Progress (%)": 100,
                    "Pages Read": 300,
                    "Total Pages": 300,
                    "Genres": ["science fiction"],
                    "Subjects": ["desert planet"],
                    "Description": "desert empire prophecy",
                },
                {
                    "Title": "TBR One",
                    "Authors": "Loved Author",
                    "ISBN/UID": "t1",
                    "Read Status": "to-read",
                    "Star Rating": np.nan,
                    "Last Date Read": None,
                    "Progress (%)": 0,
                    "Pages Read": 0,
                    "Total Pages": 400,
                    "Genres": ["science fiction"],
                    "Subjects": ["desert planet"],
                    "Description": "desert empire sequel",
                },
                {
                    "Title": "TBR Two",
                    "Authors": "New Author",
                    "ISBN/UID": "t2",
                    "Read Status": "to-read",
                    "Star Rating": np.nan,
                    "Last Date Read": None,
                    "Progress (%)": 0,
                    "Pages Read": 0,
                    "Total Pages": 200,
                    "Genres": ["science fiction"],
                    "Subjects": ["desert planet"],
                    "Description": "desert empire anthology",
                },
            ]
        )

        results = build_recommendations(df, top_n=2)

        self.assertEqual(len(results), 2)
        first = results[0]
        self.assertIn("book", first)
        self.assertIn("recommended_book", first)
        self.assertIn("score", first)
        self.assertIn("explanation", first)
        self.assertIn("reason", first)
        self.assertIn("matched_genres", first)
        self.assertIn("matched_liked_books", first)
        self.assertIn("score_breakdown", first)
        self.assertIn("recommendation_reasons", first)
        self.assertIn("recommendation_breakdown", first)
        self.assertIn("signals", first)
        self.assertIn("related_books", first)
        self.assertIn("similar_books", first)
        titles = {item["book"]["title"] for item in results}
        self.assertEqual(titles, {"TBR One", "TBR Two"})
        self.assertGreater(len(first["similar_books"]), 0)
        self.assertTrue(first["in_library"])
        self.assertFalse(first["external_discovery"])

    def test_recommendation_sections_are_structured_and_deduplicated(self):
        response = recommendation_sections_response(
            [
                {
                    "recommended_book": {
                        "id": "work-1",
                        "title": "Candidate",
                        "author": "Author",
                        "cover_url": None,
                    },
                    "score": 0.91,
                    "reason": "Shares mystery with a completed book.",
                    "matched_genres": ["Mystery"],
                    "matched_subjects": ["Detective"],
                    "related_books": [
                        {"id": "a", "title": "A", "author": "One"},
                        {"id": "b", "title": "B", "author": "Two"},
                        {"id": "c", "title": "C", "author": "Three"},
                        {"id": "d", "title": "D", "author": "Four"},
                    ],
                },
                {
                    "recommended_book": {
                        "id": "work-1",
                        "title": "Candidate Duplicate",
                        "author": "Author",
                    },
                    "score": 0.8,
                },
            ],
            style="balanced",
        )

        self.assertEqual(response["style"], "balanced")
        self.assertEqual(len(response["sections"]), 1)
        items = response["sections"][0]["items"]
        self.assertEqual(len(items), 1)
        item = items[0]
        self.assertEqual(item["work_id"], "work-1")
        self.assertEqual(item["match_percentage"], 91)
        self.assertEqual(item["match_label"], "Strong match")
        self.assertEqual(item["explanation"]["primary_reason"], "Shares mystery with a completed book.")
        self.assertEqual(len(item["explanation"]["related_books"]), 3)
        self.assertEqual(item["explanation"]["shared_genres"], ["Mystery"])
        self.assertEqual(item["explanation"]["shared_traits"], ["Detective"])

    def test_recommendation_reason_names_matched_genre_and_liked_book(self):
        df = pd.DataFrame(
            [
                {
                    "Title": "Book Lovers",
                    "Authors": "Emily Henry",
                    "ISBN/UID": "r1",
                    "Read Status": "read",
                    "Star Rating": 5,
                    "Genres": ["romance", "contemporary romance"],
                    "Total Pages": 320,
                },
                {
                    "Title": "Beach Read",
                    "Authors": "Emily Henry",
                    "ISBN/UID": "t1",
                    "Read Status": "to-read",
                    "Genres": ["romance", "contemporary romance"],
                    "Total Pages": 300,
                },
            ]
        )

        result = build_recommendations(df, top_n=1)[0]

        self.assertIn("romance", result["reason"].lower())
        self.assertIn("Book Lovers", result["reason"])
        self.assertIn("5★", result["reason"])
        self.assertIn("Romance", result["matched_genres"])
        self.assertEqual(result["matched_liked_books"][0]["title"], "Book Lovers")
        self.assertEqual(result["related_books"][0]["title"], "Book Lovers")

    def test_normal_recommendation_is_deterministic(self):
        df = pd.DataFrame(
            [{"Title": "Read", "Authors": "A", "ISBN/UID": "r1", "Read Status": "read", "Star Rating": 5, "Genres": ["sci-fi"]}]
            + [
                {"Title": f"TBR {i}", "Authors": "B", "ISBN/UID": f"t{i}", "Read Status": "to-read", "Genres": ["sci-fi"]}
                for i in range(12)
            ]
        )

        first = build_recommendations(df, top_n=10)
        second = build_recommendations(df, top_n=10)

        self.assertEqual(
            [item["recommended_book"]["id"] for item in first],
            [item["recommended_book"]["id"] for item in second],
        )

    def test_refresh_exclude_ids_returns_alternatives_first(self):
        df = pd.DataFrame(
            [{"Title": "Read", "Authors": "A", "ISBN/UID": "r1", "Read Status": "read", "Star Rating": 5, "Genres": ["sci-fi"]}]
            + [
                {"Title": f"TBR {i}", "Authors": "B", "ISBN/UID": f"t{i}", "Read Status": "to-read", "Genres": ["sci-fi"]}
                for i in range(14)
            ]
        )
        normal = build_recommendations(df, top_n=10)
        excluded = {item["recommended_book"]["id"] for item in normal}

        refreshed = build_recommendations(df, top_n=10, refresh=True, exclude_ids=excluded)

        self.assertTrue(refreshed)
        self.assertNotIn(refreshed[0]["recommended_book"]["id"], excluded)

    def test_low_scoring_candidates_still_fill_top_ten(self):
        df = pd.DataFrame(
            [{"Title": "Read", "Authors": "A", "ISBN/UID": "r1", "Read Status": "read", "Star Rating": 5, "Genres": ["history"]}]
            + [
                {"Title": f"Candidate {i}", "Authors": f"Author {i}", "ISBN/UID": f"t{i}", "Read Status": "to-read", "Genres": ["romance"]}
                for i in range(12)
            ]
        )

        result = build_recommendations(df, top_n=10)

        self.assertEqual(len(result), 10)

    def test_candidates_fill_top_ten_without_reading_history(self):
        df = pd.DataFrame(
            [
                {
                    "Title": f"Candidate {i}",
                    "Authors": f"Author {i}",
                    "ISBN/UID": f"t{i}",
                    "Read Status": "to-read",
                }
                for i in range(12)
            ]
        )

        result = build_recommendations(df, top_n=10)

        self.assertEqual(len(result), 10)

    def test_refresh_keeps_weak_candidates_after_strong_candidates(self):
        df = pd.DataFrame(
            [
                {"Title": "Read", "Authors": "A", "ISBN/UID": "r1", "Read Status": "read", "Star Rating": 5, "Subjects": ["dystopian fiction", "political fiction"]},
                {"Title": "Strong", "Authors": "B", "ISBN/UID": "t1", "Read Status": "to-read", "Subjects": ["dystopian fiction", "political fiction"]},
                {"Title": "Weak", "Authors": "C", "ISBN/UID": "t2", "Read Status": "to-read", "Subjects": ["wedding"]},
            ]
        )

        refreshed = build_recommendations(df, top_n=10, refresh=True, exclude_ids={"t1"})

        self.assertEqual(
            [item["recommended_book"]["title"] for item in refreshed],
            ["Strong", "Weak"],
        )

    def test_unrelated_book_uses_rating_recency_fallback_without_overlap(self):
        df = pd.DataFrame(
            [
                {"Title": "Fahrenheit 451", "Authors": "Ray Bradbury", "ISBN/UID": "r1", "Read Status": "read", "Star Rating": 5, "Subjects": ["dystopian fiction"], "Total Pages": 200},
                {"Title": "The Great Gatsby", "Authors": "F. Scott Fitzgerald", "ISBN/UID": "r2", "Read Status": "read", "Star Rating": 5, "Subjects": ["classic fiction"], "Total Pages": 180},
                {"Title": "The Alchemist", "Authors": "Paulo Coelho", "ISBN/UID": "r3", "Read Status": "read", "Star Rating": 4, "Subjects": ["self discovery"], "Total Pages": 190},
                {"Title": "Có hạnh phúc", "Authors": "Hari Won", "ISBN/UID": "t1", "Read Status": "to-read", "Pages Read": 0, "Total Pages": None},
            ]
        )

        result = build_recommendations(df, top_n=1)

        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["book"]["title"], "Có hạnh phúc")
        self.assertEqual(result[0]["explanation"], "Recommended based on your reading history.")
        self.assertEqual(result[0]["matched_liked_books"], [])
        self.assertEqual(result[0]["recommendation_reasons"][0]["label"], "Already on your shelf")

    def test_generic_genres_do_not_create_similarity_but_can_fallback(self):
        df = pd.DataFrame(
            [
                {"Title": "Read", "Authors": "A", "ISBN/UID": "r1", "Read Status": "read", "Star Rating": 5, "Subjects": ["Fiction"], "Total Pages": 200},
                {"Title": "Unread", "Authors": "B", "ISBN/UID": "t1", "Read Status": "to-read", "Subjects": ["fiction"], "Total Pages": 200},
            ]
        )

        result = build_recommendations(df, top_n=1)

        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["book"]["title"], "Unread")
        self.assertEqual(result[0]["similar_books"], [])

    def test_genre_overlap_generates_similarity_reason(self):
        df = pd.DataFrame(
            [
                {"Title": "Read Dystopia", "Authors": "A", "ISBN/UID": "r1", "Read Status": "read", "Star Rating": 5, "Subjects": ["Dystopian fiction"], "Total Pages": 200},
                {"Title": "Unread Dystopia", "Authors": "B", "ISBN/UID": "t1", "Read Status": "to-read", "Subjects": ["dystopian fiction"], "Total Pages": 200},
            ]
        )

        result = build_recommendations(df, top_n=1)[0]

        self.assertEqual(result["explanation"], "Because you enjoyed Read Dystopia, this may fit your reading taste.")
        self.assertIn("Read Dystopia", result["explanation"])
        self.assertEqual([book["title"] for book in result["similar_books"]], ["Read Dystopia"])

    def test_in_progress_reason_wins(self):
        df = pd.DataFrame(
            [
                {"Title": "Read", "Authors": "A", "ISBN/UID": "r1", "Read Status": "read", "Star Rating": 5, "Subjects": ["memoir"], "Total Pages": 200},
                {"Title": "Started", "Authors": "B", "ISBN/UID": "t1", "Read Status": "to-read", "Pages Read": 25, "Subjects": ["memoir"], "Total Pages": 200},
            ]
        )

        result = build_recommendations(df, top_n=1)

        self.assertEqual(result, [])

    def test_strong_metadata_match_beats_unrelated_candidate(self):
        df = pd.DataFrame(
            [
                {"Title": "Fahrenheit 451", "Authors": "Ray Bradbury", "ISBN/UID": "r1", "Read Status": "read", "Star Rating": 5, "Genres": ["dystopian"], "Subjects": ["censorship"], "Description": "books censorship fire", "Total Pages": 200},
                {"Title": "Matched", "Authors": "B", "ISBN/UID": "t1", "Read Status": "to-read", "Genres": ["dystopian"], "Subjects": ["censorship"], "Description": "books censorship surveillance", "Total Pages": 210},
                {"Title": "Unrelated", "Authors": "C", "ISBN/UID": "t2", "Read Status": "to-read", "Genres": ["romance"], "Subjects": ["weddings"], "Description": "weddings family", "Total Pages": 200},
            ]
        )

        result = build_recommendations(df, top_n=2)

        self.assertEqual(
            [item["book"]["title"] for item in result],
            ["Matched", "Unrelated"],
        )
        self.assertIn("censorship", result[0]["explanation"].lower())

    def test_external_books_are_returned_and_library_candidates_get_boost(self):
        df = pd.DataFrame(
            [
                {"Title": "Read", "Authors": "A", "ISBN/UID": "r1", "Read Status": "read", "Star Rating": 5, "Genres": ["mystery"]},
                {"Title": "Owned Match", "Authors": "B", "ISBN/UID": "t1", "Read Status": "to-read", "Genres": ["mystery"], "In Library": True, "Discovery Source": "library"},
                {"Title": "External Match", "Authors": "C", "ISBN/UID": "x1", "Read Status": "to-read", "Genres": ["mystery"], "In Library": False, "Discovery Source": "local_catalog"},
            ]
        )

        result = build_recommendations(df, top_n=2, style="balanced")

        self.assertEqual([item["book"]["title"] for item in result], ["Owned Match", "External Match"])
        self.assertTrue(result[0]["in_library"])
        self.assertTrue(result[1]["external_discovery"])

    def test_discovery_style_returns_more_external_candidates(self):
        rows = [{"Title": "Read", "Authors": "A", "ISBN/UID": "r1", "Read Status": "read", "Star Rating": 5, "Genres": ["fantasy"]}]
        rows += [
            {"Title": f"Owned {i}", "Authors": "B", "ISBN/UID": f"t{i}", "Read Status": "to-read", "Genres": ["fantasy"], "In Library": True}
            for i in range(5)
        ]
        rows += [
            {"Title": f"External {i}", "Authors": "C", "ISBN/UID": f"x{i}", "Read Status": "to-read", "Genres": ["fantasy"], "In Library": False}
            for i in range(5)
        ]

        balanced = build_recommendations(pd.DataFrame(rows), top_n=6, style="balanced")
        discovery = build_recommendations(pd.DataFrame(rows), top_n=6, style="discovery")

        assert sum(1 for item in discovery if item["external_discovery"]) > sum(1 for item in balanced if item["external_discovery"])

    def test_completed_duplicate_work_is_excluded(self):
        df = pd.DataFrame(
            [
                {"Title": "Completed Work", "Authors": "A", "ISBN/UID": "r1", "Read Status": "read", "Star Rating": 5, "Work Key": "W1", "Genres": ["classic"]},
                {"Title": "Completed Work", "Authors": "A", "ISBN/UID": "x1", "Read Status": "to-read", "Work Key": "W1", "Genres": ["classic"], "In Library": False},
                {"Title": "Different Work", "Authors": "B", "ISBN/UID": "t1", "Read Status": "to-read", "Genres": ["classic"], "In Library": True},
            ]
        )

        result = build_recommendations(df, top_n=3)

        self.assertEqual([item["book"]["title"] for item in result], ["Different Work"])

    def test_newly_read_high_rated_classic_appears_as_anchor(self):
        df = pd.DataFrame(
            [
                {
                    "Title": "A Midsummer Night's Dream",
                    "Authors": "William Shakespeare",
                    "ISBN/UID": "old-1",
                    "Read Status": "read",
                    "Star Rating": 4.75,
                    "End Date": "2020-01-01",
                    "Genres": ["Drama", "Classic"],
                    "Subjects": ["Plays"],
                },
                {
                    "Title": "Pride and Prejudice",
                    "Authors": "Jane Austen",
                    "ISBN/UID": "old-2",
                    "Read Status": "read",
                    "Star Rating": 4.75,
                    "End Date": "2020-01-02",
                    "Genres": ["Romance", "Classic"],
                    "Subjects": ["Courtship"],
                },
                {
                    "Title": "Antigone",
                    "Authors": "Sophocles",
                    "ISBN/UID": "old-3",
                    "Read Status": "read",
                    "Star Rating": 4.75,
                    "End Date": "2020-01-03",
                    "Genres": ["Drama", "Classic"],
                    "Subjects": ["Greek drama"],
                },
                {
                    "Title": "Anna Karenina",
                    "Authors": "Leo Tolstoy",
                    "ISBN/UID": "9780345803924",
                    "Read Status": "read",
                    "Star Rating": 4.75,
                    "End Date": "2026-07-01",
                    "Genres": ["Drama", "Romance", "Classic"],
                    "Subjects": ["Adultery", "Married Women", "Russian Literature"],
                },
                {
                    "Title": "Madame Bovary",
                    "Authors": "Gustave Flaubert",
                    "ISBN/UID": "t1",
                    "Read Status": "to-read",
                    "Genres": ["Drama", "Romance", "Classic"],
                    "Subjects": ["Adultery", "Married Women"],
                },
            ]
        )

        result = build_recommendations(df, top_n=1)[0]

        self.assertEqual(result["book"]["title"], "Madame Bovary")
        self.assertIn(
            "Anna Karenina",
            [book["title"] for book in result["matched_liked_books"]],
        )
        self.assertIn("Anna Karenina", result["explanation"])

    def test_duplicate_to_read_same_isbn_does_not_suppress_read_rated_anchor(self):
        df = pd.DataFrame(
            [
                {
                    "Title": "Anna Karenina",
                    "Authors": "Leo Tolstoy",
                    "ISBN/UID": "9780345803924",
                    "Read Status": "to-read",
                    "Star Rating": np.nan,
                    "Genres": ["Drama", "Romance", "Classic"],
                    "Subjects": ["Adultery", "Married Women", "Russian Literature"],
                },
                {
                    "Title": "Anna Karenina",
                    "Authors": "Leo Tolstoy",
                    "ISBN/UID": "9780345803924",
                    "Read Status": "read",
                    "Star Rating": 4.75,
                    "Genres": ["Drama", "Romance", "Classic"],
                    "Subjects": ["Adultery", "Married Women", "Russian Literature"],
                },
                {
                    "Title": "The Scarlet Letter",
                    "Authors": "Nathaniel Hawthorne",
                    "ISBN/UID": "scarlet-letter",
                    "Read Status": "to-read",
                    "Genres": ["Drama", "Romance", "Classic"],
                    "Subjects": ["Adultery", "Married Women"],
                },
            ]
        )

        result = build_recommendations(df, top_n=2)

        self.assertEqual([item["book"]["title"] for item in result], ["The Scarlet Letter"])
        self.assertEqual(result[0]["matched_liked_books"][0]["title"], "Anna Karenina")

    def test_completed_books_influence_scores_but_are_not_recommended(self):
        base_rows = [
            {
                "Title": "Unrelated Read",
                "Authors": "A",
                "ISBN/UID": "read-1",
                "Read Status": "read",
                "Star Rating": 4,
                "Genres": ["history"],
                "Subjects": ["war"],
            },
            {
                "Title": "The Scarlet Letter",
                "Authors": "Nathaniel Hawthorne",
                "ISBN/UID": "scarlet-letter",
                "Read Status": "to-read",
                "Genres": ["Drama", "Romance", "Classic"],
                "Subjects": ["Adultery", "Married Women"],
            },
            {
                "Title": "Space Opera",
                "Authors": "B",
                "ISBN/UID": "space-opera",
                "Read Status": "to-read",
                "Genres": ["science fiction"],
                "Subjects": ["space"],
            },
        ]
        before = build_recommendations(pd.DataFrame(base_rows), top_n=2)
        before_scarlet = next(item for item in before if item["book"]["title"] == "The Scarlet Letter")

        after = build_recommendations(
            pd.DataFrame(
                base_rows
                + [
                    {
                        "Title": "Anna Karenina",
                        "Authors": "Leo Tolstoy",
                        "ISBN/UID": "9780345803924",
                        "Read Status": "completed",
                        "Star Rating": 5,
                        "Genres": ["Drama", "Romance", "Classic"],
                        "Subjects": ["Adultery", "Married Women", "Russian Literature"],
                    }
                ]
            ),
            top_n=3,
        )

        after_titles = [item["book"]["title"] for item in after]
        after_scarlet = next(item for item in after if item["book"]["title"] == "The Scarlet Letter")

        self.assertNotIn("Anna Karenina", after_titles)
        self.assertGreater(after_scarlet["score"], before_scarlet["score"])
        self.assertIn(
            "Anna Karenina",
            [book["title"] for book in after_scarlet["matched_liked_books"]],
        )

    def test_explanation_prefers_score_contributors_over_similarity_rank(self):
        rows = [
            {
                "Title": "Anna Karenina",
                "Authors": "Leo Tolstoy",
                "ISBN/UID": "anna",
                "Read Status": "read",
                "Star Rating": 4.75,
                "End Date": "2026-07-01",
                "Genres": ["Drama", "Romance", "Classic"],
                "Subjects": ["Adultery", "Married Women"],
            },
        ]
        for index in range(12):
            rows.append(
                {
                    "Title": f"Other Read {index}",
                    "Authors": f"Author {index}",
                    "ISBN/UID": f"read-{index}",
                    "Read Status": "read",
                    "Star Rating": 5,
                    "End Date": "2020-01-01",
                    "Genres": ["Historical Fiction", "Young Adult"],
                    "Subjects": ["History"],
                }
            )
        rows.append(
            {
                "Title": "Romeo and Juliet",
                "Authors": "William Shakespeare",
                "ISBN/UID": "romeo",
                "Read Status": "to-read",
                "Genres": ["Drama", "Classic"],
                "Subjects": ["Love stories"],
            }
        )

        result = build_recommendations(pd.DataFrame(rows), top_n=1)[0]

        self.assertEqual(result["book"]["title"], "Romeo and Juliet")
        self.assertIn(
            "Anna Karenina",
            [book["title"] for book in result["matched_liked_books"]],
        )
        self.assertIn("Anna Karenina", result["reason"])

    def test_select_reason_anchor_prefers_high_rating_when_contribution_close(self):
        candidates = [
            {
                "title": "Othello",
                "rating": 3.0,
                "_score_weight": 0.59,
                "_match_score": 4,
                "_shared_genres": ["Drama"],
                "_shared_subjects": [],
            },
            {
                "title": "Anna Karenina",
                "rating": 4.75,
                "_score_weight": 0.40,
                "_match_score": 2,
                "_shared_genres": ["Drama", "Classic"],
                "_shared_subjects": [],
            },
            {
                "title": "Lysistrata",
                "rating": 4.5,
                "_score_weight": 0.39,
                "_match_score": 2,
                "_shared_genres": ["Drama"],
                "_shared_subjects": [],
            },
        ]

        anchor = _select_reason_anchor(candidates)

        self.assertEqual(anchor["title"], "Anna Karenina")

    def test_select_reason_anchor_keeps_much_stronger_low_rated_anchor(self):
        candidates = [
            {
                "title": "Othello",
                "rating": 3.0,
                "_score_weight": 0.90,
                "_match_score": 5,
                "_shared_genres": ["Drama"],
                "_shared_subjects": [],
            },
            {
                "title": "Anna Karenina",
                "rating": 4.75,
                "_score_weight": 0.20,
                "_match_score": 2,
                "_shared_genres": ["Drama", "Classic"],
                "_shared_subjects": [],
            },
        ]

        anchor = _select_reason_anchor(candidates)

        self.assertEqual(anchor["title"], "Othello")

    def test_reason_headline_prefers_higher_rated_anchor_over_first_match(self):
        df = pd.DataFrame(
            [
                {
                    "Title": "Othello",
                    "Authors": "William Shakespeare",
                    "ISBN/UID": "othello",
                    "Read Status": "read",
                    "Star Rating": 3,
                    "End Date": "2020-01-01",
                    "Genres": ["Drama", "Historical Fiction"],
                    "Subjects": ["Drama"],
                },
                {
                    "Title": "Anna Karenina",
                    "Authors": "Leo Tolstoy",
                    "ISBN/UID": "anna",
                    "Read Status": "read",
                    "Star Rating": 4.75,
                    "End Date": "2026-07-01",
                    "Genres": ["Drama", "Romance", "Classic"],
                    "Subjects": ["Adultery"],
                },
                {
                    "Title": "Lysistrata",
                    "Authors": "Aristophanes",
                    "ISBN/UID": "lysistrata",
                    "Read Status": "read",
                    "Star Rating": 4.5,
                    "End Date": "2020-01-02",
                    "Genres": ["Drama", "Classic"],
                    "Subjects": ["Drama"],
                },
                {
                    "Title": "Romeo and Juliet",
                    "Authors": "William Shakespeare",
                    "ISBN/UID": "romeo",
                    "Read Status": "to-read",
                    "Genres": ["Drama", "Classic"],
                    "Subjects": ["Courtship", "Love stories"],
                },
            ]
        )

        result = build_recommendations(df, top_n=1)[0]

        self.assertEqual(result["book"]["title"], "Romeo and Juliet")
        matched_titles = [book["title"] for book in result["matched_liked_books"]]
        self.assertIn("Othello", matched_titles)
        self.assertIn("Anna Karenina", matched_titles)
        self.assertIn("Anna Karenina", result["reason"])
        self.assertIn("4.75★", result["reason"])
        self.assertNotIn("which you rated 3★", result["reason"])


if __name__ == "__main__":
    unittest.main()
