import unittest

import numpy as np
import pandas as pd

from backend.services.recommendation_builder import build_recommendations


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
        self.assertEqual(result[0]["recommendation_reasons"], [])

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


if __name__ == "__main__":
    unittest.main()
