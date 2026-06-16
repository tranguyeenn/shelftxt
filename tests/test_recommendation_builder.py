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
                },
            ]
        )

        results = build_recommendations(df, top_n=2)

        self.assertEqual(len(results), 2)
        first = results[0]
        self.assertIn("book", first)
        self.assertIn("score", first)
        self.assertIn("explanation", first)
        self.assertIn("similar_books", first)
        titles = {item["book"]["title"] for item in results}
        self.assertEqual(titles, {"TBR One", "TBR Two"})
        self.assertGreater(len(first["similar_books"]), 0)

    def test_unrelated_book_gets_discovery_reason_without_fake_similarity(self):
        df = pd.DataFrame(
            [
                {"Title": "Fahrenheit 451", "Authors": "Ray Bradbury", "ISBN/UID": "r1", "Read Status": "read", "Star Rating": 5, "Subjects": ["dystopian fiction"], "Total Pages": 200},
                {"Title": "The Great Gatsby", "Authors": "F. Scott Fitzgerald", "ISBN/UID": "r2", "Read Status": "read", "Star Rating": 5, "Subjects": ["classic fiction"], "Total Pages": 180},
                {"Title": "The Alchemist", "Authors": "Paulo Coelho", "ISBN/UID": "r3", "Read Status": "read", "Star Rating": 4, "Subjects": ["self discovery"], "Total Pages": 190},
                {"Title": "Có hạnh phúc", "Authors": "Hari Won", "ISBN/UID": "t1", "Read Status": "to-read", "Pages Read": 0, "Total Pages": None},
            ]
        )

        result = build_recommendations(df, top_n=1)[0]

        self.assertEqual(result["book"]["title"], "Có hạnh phúc")
        self.assertEqual(result["similar_books"], [])
        self.assertEqual(result["explanation"], "Recommended as a discovery pick from your unread books.")

    def test_generic_genres_do_not_create_similarity(self):
        df = pd.DataFrame(
            [
                {"Title": "Read", "Authors": "A", "ISBN/UID": "r1", "Read Status": "read", "Star Rating": 5, "Subjects": ["Fiction"], "Total Pages": 200},
                {"Title": "Unread", "Authors": "B", "ISBN/UID": "t1", "Read Status": "to-read", "Subjects": ["fiction"], "Total Pages": 200},
            ]
        )

        result = build_recommendations(df, top_n=1)[0]

        self.assertEqual(result["similar_books"], [])
        self.assertEqual(result["explanation"], "Recommended as a discovery pick from your unread books.")

    def test_genre_overlap_generates_similarity_reason(self):
        df = pd.DataFrame(
            [
                {"Title": "Read Dystopia", "Authors": "A", "ISBN/UID": "r1", "Read Status": "read", "Star Rating": 5, "Subjects": ["Dystopian fiction"], "Total Pages": 200},
                {"Title": "Unread Dystopia", "Authors": "B", "ISBN/UID": "t1", "Read Status": "to-read", "Subjects": ["dystopian fiction"], "Total Pages": 200},
            ]
        )

        result = build_recommendations(df, top_n=1)[0]

        self.assertEqual(result["explanation"], "This matches genres you’ve read before.")
        self.assertEqual([book["title"] for book in result["similar_books"]], ["Read Dystopia"])

    def test_in_progress_reason_wins(self):
        df = pd.DataFrame(
            [
                {"Title": "Read", "Authors": "A", "ISBN/UID": "r1", "Read Status": "read", "Star Rating": 5, "Subjects": ["memoir"], "Total Pages": 200},
                {"Title": "Started", "Authors": "B", "ISBN/UID": "t1", "Read Status": "to-read", "Pages Read": 25, "Subjects": ["memoir"], "Total Pages": 200},
            ]
        )

        result = build_recommendations(df, top_n=1)[0]

        self.assertEqual(result["explanation"], "You already started this book.")


if __name__ == "__main__":
    unittest.main()
