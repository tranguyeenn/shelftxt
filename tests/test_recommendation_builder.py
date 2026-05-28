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


if __name__ == "__main__":
    unittest.main()
