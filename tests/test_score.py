import unittest
from unittest.mock import patch

import pandas as pd

from backend.ranking.score import (
    _rating_influence,
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

    def test_score_read_books_treats_completed_as_read_anchor(self):
        df = pd.DataFrame(
            [
                {
                    "title": "Anna Karenina",
                    "read_status": "completed",
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
        self.assertEqual(result.iloc[0]["title"], "Anna Karenina")

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

        self.assertEqual(len(result), 1)

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

        self.assertEqual(len(result), 2)

    @patch("numpy.random.uniform")
    def test_score_tbr_books_uses_low_rated_and_unrated_completed_books(
        self,
        mock_uniform,
    ):
        mock_uniform.return_value = [0.0, 0.0]

        df = pd.DataFrame(
            [
                {
                    "title": "Low Rated Anchor",
                    "author": "Author A",
                    "read_status": "read",
                    "rating_norm": 0.2,
                    "Star Rating": 1,
                    "Genres": ["horror"],
                },
                {
                    "title": "Unrated Anchor",
                    "author": "Author B",
                    "read_status": "read",
                    "rating_norm": 0.5,
                    "Genres": ["memoir"],
                },
                {
                    "title": "Horror Candidate",
                    "author": "Author C",
                    "read_status": "to-read",
                    "Genres": ["horror"],
                },
                {
                    "title": "Memoir Candidate",
                    "author": "Author D",
                    "read_status": "to-read",
                    "Genres": ["memoir"],
                },
            ]
        )

        result = score_tbr_books(df, diverse_authors=False)

        self.assertEqual(set(result["title"]), {"Horror Candidate", "Memoir Candidate"})
        self.assertTrue((result["score"] > 0).all())

    @patch("numpy.random.uniform")
    def test_score_tbr_books_uses_completed_status_as_preference_anchor(
        self,
        mock_uniform,
    ):
        mock_uniform.return_value = [0.0]

        df = pd.DataFrame(
            [
                {
                    "title": "Anna Karenina",
                    "author": "Leo Tolstoy",
                    "read_status": "completed",
                    "rating_norm": 1.0,
                    "Star Rating": 5,
                    "Genres": ["classic", "romance"],
                    "Subjects": ["Russian literature", "married women"],
                },
                {
                    "title": "The Scarlet Letter",
                    "author": "Nathaniel Hawthorne",
                    "read_status": "to-read",
                    "Genres": ["classic", "romance"],
                    "Subjects": ["married women"],
                },
            ]
        )

        result = score_tbr_books(df, diverse_authors=False)

        self.assertEqual(result.iloc[0]["title"], "The Scarlet Letter")
        self.assertGreater(result.iloc[0]["score"], 0.5)
        self.assertEqual(result.iloc[0]["_similar_matches"][0][0], 0)
        score_anchors = result.iloc[0].get("_score_anchors", [])
        self.assertTrue(score_anchors)
        self.assertEqual(score_anchors[0][0], 0)

    @patch("numpy.random.uniform")
    def test_score_tbr_books_records_score_anchors_for_explanations(
        self,
        mock_uniform,
    ):
        mock_uniform.return_value = [0.0]

        df = pd.DataFrame(
            [
                {
                    "title": "Anna Karenina",
                    "author": "Leo Tolstoy",
                    "read_status": "read",
                    "rating_norm": 1.0,
                    "Star Rating": 4.75,
                    "Genres": ["drama", "classic"],
                    "Subjects": ["adultery"],
                },
                {
                    "title": "Othello",
                    "author": "William Shakespeare",
                    "read_status": "read",
                    "rating_norm": 1.0,
                    "Star Rating": 5,
                    "Genres": ["drama", "historical fiction"],
                    "Subjects": ["drama"],
                },
                {
                    "title": "Romeo and Juliet",
                    "author": "William Shakespeare",
                    "read_status": "to-read",
                    "Genres": ["drama", "classic"],
                    "Subjects": ["love stories"],
                },
            ]
        )

        result = score_tbr_books(df, diverse_authors=False)
        romeo = result.iloc[0]
        anchor_titles = [
            df.loc[index]["title"]
            for index, _contribution, _similarity in romeo["_score_anchors"]
        ]

        self.assertIn("Anna Karenina", anchor_titles)

    def test_rating_influence_treats_unrated_as_neutral(self):
        self.assertEqual(_rating_influence(None), 1.0)
        self.assertEqual(_rating_influence(5), 1.0)
        self.assertEqual(_rating_influence(4), 1.0)
        self.assertEqual(_rating_influence(3), 0.85)
        self.assertEqual(_rating_influence(2), 0.55)
        self.assertEqual(_rating_influence(1), 0.35)

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

        assert result is not None
        self.assertEqual(len(result), 1)

    def test_recommend_one_samples_from_top_ten_with_score_weights(self):
        df = pd.DataFrame(
            [{"title": f"Book {index}", "score": 1.0} for index in range(12)]
        )

        with patch.object(pd.DataFrame, "sample", return_value=df.head(1)) as mock_sample:
            recommend_one(df)

        self.assertEqual(mock_sample.call_args.args, (1,))
        weights = mock_sample.call_args.kwargs["weights"]
        self.assertEqual(len(weights), 10)
        self.assertEqual(weights.index.tolist(), list(range(10)))


if __name__ == "__main__":
    unittest.main()
