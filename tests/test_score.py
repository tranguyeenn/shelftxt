import unittest
from unittest.mock import patch

import pandas as pd

from backend.ranking.score import (
    recommend_one,
    score_read_books,
    score_tbr_books,
)


class ScoreTests(unittest.TestCase):

    def test_score_read_books_returns_only_read_books(self):
        df = pd.DataFrame(
            [
                {
                    "title": "Dune",
                    "read_status": "read",
                    "rating_norm": 1.0,
                    "recency_norm": 1.0,
                },
                {
                    "title": "Snow Crash",
                    "read_status": "to-read",
                    "rating_norm": 0.5,
                    "recency_norm": 0.5,
                },
            ]
        )

        result = score_read_books(df)

        self.assertEqual(len(result), 1)
        self.assertEqual(result.iloc[0]["title"], "Dune")

    def test_score_read_books_empty_dataframe(self):
        df = pd.DataFrame()

        result = score_read_books(df)

        self.assertTrue(result.empty)

    def test_score_read_books_generates_expected_score(self):
        df = pd.DataFrame(
            [
                {
                    "title": "Dune",
                    "read_status": "read",
                    "rating_norm": 1.0,
                    "recency_norm": 0.0,
                }
            ]
        )

        result = score_read_books(df)

        expected = 0.7
        self.assertAlmostEqual(result.iloc[0]["score"], expected)

    def test_score_read_books_clips_scores(self):
        df = pd.DataFrame(
            [
                {
                    "title": "Dune",
                    "read_status": "read",
                    "rating_norm": 5.0,
                    "recency_norm": 5.0,
                }
            ]
        )

        result = score_read_books(df)

        self.assertEqual(result.iloc[0]["score"], 1.0)

    def test_score_read_books_sorted_descending(self):
        df = pd.DataFrame(
            [
                {
                    "title": "Low",
                    "read_status": "read",
                    "rating_norm": 0.2,
                    "recency_norm": 0.2,
                },
                {
                    "title": "High",
                    "read_status": "read",
                    "rating_norm": 1.0,
                    "recency_norm": 1.0,
                },
            ]
        )

        result = score_read_books(df)

        self.assertEqual(result.iloc[0]["title"], "High")

    @patch("numpy.random.uniform")
    def test_score_tbr_books_scores_by_author_preference(
        self,
        mock_uniform,
    ):
        mock_uniform.return_value = [0.0]

        df = pd.DataFrame(
            [
                {
                    "title": "Dune",
                    "author": "Frank Herbert",
                    "read_status": "read",
                    "rating_norm": 1.0,
                    "Star Rating": 5,
                    "Genres": ["science fiction"],
                    "Subjects": ["desert planet"],
                    "Total Pages": 500,
                },
                {
                    "title": "Dune Messiah",
                    "author": "Frank Herbert",
                    "read_status": "to-read",
                    "rating_norm": 0.0,
                    "Genres": ["science fiction"],
                    "Subjects": ["desert planet"],
                    "Total Pages": 400,
                },
            ]
        )

        result = score_tbr_books(df)

        self.assertEqual(len(result), 1)
        self.assertGreaterEqual(result.iloc[0]["score"], 0.35)

    @patch("numpy.random.uniform")
    def test_score_tbr_books_removes_duplicates(
        self,
        mock_uniform,
    ):
        # After duplicate removal only one row remains,
        # so mocked noise must also contain one value.
        mock_uniform.return_value = [0.0]

        df = pd.DataFrame(
            [
                {
                    "title": "Dune",
                    "author": "Frank Herbert",
                    "read_status": "to-read",
                    "rating_norm": 0.5,
                    "Genres": ["science fiction"],
                },
                {
                    "title": "Dune",
                    "author": "Frank Herbert",
                    "read_status": "to-read",
                    "rating_norm": 0.5,
                    "Genres": ["science fiction"],
                },
            ]
        )

        result = score_tbr_books(df)

        self.assertEqual(len(result), 0)

    @patch("numpy.random.uniform")
    def test_score_tbr_books_diverse_authors(
        self,
        mock_uniform,
    ):
        mock_uniform.return_value = [0.0, 0.0]

        df = pd.DataFrame(
            [
                {
                    "title": "Book 1",
                    "author": "Author A",
                    "read_status": "to-read",
                    "rating_norm": 0.5,
                    "Genres": ["science fiction"],
                },
                {
                    "title": "Book 2",
                    "author": "Author A",
                    "read_status": "to-read",
                    "rating_norm": 0.5,
                    "Genres": ["science fiction"],
                },
            ]
        )

        result = score_tbr_books(df, diverse_authors=True)

        self.assertEqual(len(result), 0)

    def test_recommend_one_returns_none_for_empty(self):
        df = pd.DataFrame()

        result = recommend_one(df)

        self.assertIsNone(result)

    def test_recommend_one_returns_single_row(self):
        df = pd.DataFrame(
            [
                {"title": "Dune", "score": 1.0},
                {"title": "Hyperion", "score": 0.9},
            ]
        )

        result = recommend_one(df)

        self.assertEqual(len(result), 1)


if __name__ == "__main__":
    unittest.main()
