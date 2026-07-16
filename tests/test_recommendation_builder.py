import unittest

import numpy as np
import pandas as pd

from backend.services.recommendation_builder import (
    _blend_library_and_discovery,
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

    def test_recommendation_sections_keep_external_item_without_local_book_id(self):
        response = recommendation_sections_response(
            [
                {
                    "recommended_book": {
                        "id": None,
                        "book_id": None,
                        "work_id": "/works/OL0001W",
                        "title": "External Candidate",
                        "author": "Outside Author",
                        "cover_url": None,
                    },
                    "recommendation_id": "work:/works/ol0001w",
                    "work_id": "/works/OL0001W",
                    "book_id": None,
                    "score": 0.72,
                    "in_library": False,
                    "external_discovery": True,
                    "discovery_source": "seeded_fixture",
                    "matched_genres": ["Dystopian"],
                    "matched_subjects": ["rebellion"],
                    "reason": "Strong external match.",
                }
            ],
            style="balanced",
        )

        items = response["sections"][0]["items"]
        self.assertEqual(len(items), 1)
        item = items[0]
        self.assertEqual(item["canonical_title"], "External Candidate")
        self.assertEqual(item["work_id"], "/works/OL0001W")
        self.assertIsNone(item["book_id"])
        self.assertEqual(item["canonical_identity"], "work:/works/ol0001w")
        self.assertFalse(item["library_state"]["in_library"])
        self.assertFalse(item["is_in_library"])
        self.assertEqual(item["source"], "external")
        self.assertTrue(item["external_discovery"])
        self.assertEqual(item["provider"], "seeded_fixture")

    def test_recommendation_sections_suppress_raw_near_duplicate_reading_levels(self):
        recommendations = []
        for index, grade in enumerate(["reading level grade 11", "reading level grade 12", "reading level grade 11"]):
            recommendations.append(
                {
                    "recommended_book": {
                        "id": f"work-{index}",
                        "title": f"Candidate {index}",
                        "author": "Author",
                    },
                    "recommendation_id": f"work:{index}",
                    "score": 0.8 - (index * 0.01),
                    "matched_genres": ["Dystopias"],
                    "matched_subjects": [grade, "Love stories"],
                    "reason": "Recommended based on your reading profile.",
                }
            )

        response = recommendation_sections_response(recommendations, style="balanced")

        all_titles = [section["title"].casefold() for section in response["sections"]]
        all_traits = [
            trait.casefold()
            for section in response["sections"]
            for item in section["items"]
            for trait in item["traits"]
        ]
        self.assertNotIn("reading level grade 11", all_titles)
        self.assertNotIn("reading level grade 12", all_titles)
        self.assertNotIn("reading level grade 11", all_traits)
        self.assertNotIn("reading level grade 12", all_traits)
        self.assertIn("advanced reads", all_traits)
        self.assertLessEqual(len(response["sections"]), 4)

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

    def test_political_philosophy_is_not_anchored_to_relationship_fiction(self):
        df = pd.DataFrame(
            [
                {
                    "Title": "Normal People",
                    "Authors": "Sally Rooney",
                    "ISBN/UID": "r1",
                    "Read Status": "read",
                    "Star Rating": 5,
                    "Genres": ["Contemporary fiction"],
                    "Subjects": ["Relationships", "Coming of age"],
                    "Description": "intimate relationship class and young adulthood",
                },
                {
                    "Title": "Second Treatise of Government",
                    "Authors": "John Locke",
                    "ISBN/UID": "t1",
                    "Read Status": "to-read",
                    "Genres": ["Political philosophy"],
                    "Subjects": ["Government", "Natural rights"],
                    "Description": "political authority consent property government",
                },
                {
                    "Title": "Conversations with Friends",
                    "Authors": "Sally Rooney",
                    "ISBN/UID": "t2",
                    "Read Status": "to-read",
                    "Genres": ["Contemporary fiction"],
                    "Subjects": ["Relationships"],
                    "Description": "relationships friendship intimacy",
                },
            ]
        )

        result = build_recommendations(df, top_n=2)
        titles = [item["title"] for item in result]

        self.assertIn("Conversations with Friends", titles)
        self.assertNotIn("Second Treatise of Government", titles)

    def test_fallback_history_only_books_do_not_enter_when_stronger_candidates_exist(self):
        df = pd.DataFrame(
            [
                {"Title": "Loved Mystery", "Authors": "A", "ISBN/UID": "r1", "Read Status": "read", "Star Rating": 5, "Genres": ["Mystery"], "Subjects": ["Detectives"], "Description": "detective investigation"},
                {"Title": "Specific Match", "Authors": "B", "ISBN/UID": "t1", "Read Status": "to-read", "Genres": ["Mystery"], "Subjects": ["Detectives"], "Description": "detective investigation"},
                {"Title": "Generic Fallback", "Authors": "C", "ISBN/UID": "t2", "Read Status": "to-read", "Genres": ["General fiction"], "Subjects": ["Life"], "Description": "a book about people and life"},
            ]
        )

        result = build_recommendations(df, top_n=2)
        titles = [item["title"] for item in result]

        self.assertEqual(titles, ["Specific Match"])

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

    def test_stronger_external_outranks_weak_library_match(self):
        ranked = pd.DataFrame(
            [
                {"Title": "Strong External", "Authors": "A", "score": 0.72, "In Library": False, "Genres": ["mystery"]},
                {"Title": "Weak Library", "Authors": "B", "score": 0.54, "In Library": True, "Genres": ["mystery"]},
            ]
        )

        result = _blend_library_and_discovery(ranked, top_n=2, style="balanced")

        self.assertEqual(result.iloc[0]["Title"], "Strong External")

    def test_library_wins_close_call_margin(self):
        ranked = pd.DataFrame(
            [
                {"Title": "External Close", "Authors": "A", "score": 0.72, "In Library": False, "Genres": ["mystery"]},
                {"Title": "Library Close", "Authors": "B", "score": 0.69, "In Library": True, "Genres": ["mystery"]},
            ]
        )

        result = _blend_library_and_discovery(ranked, top_n=2, style="balanced")

        self.assertEqual(result.iloc[0]["Title"], "Library Close")

    def test_three_strong_external_books_appear_in_ten_results(self):
        rows = [
            {"Title": f"Library {i}", "Authors": f"L{i}", "score": 0.70 - (i * 0.01), "In Library": True, "Genres": ["mystery"]}
            for i in range(7)
        ]
        rows += [
            {"Title": f"External {i}", "Authors": f"E{i}", "score": 0.68 - (i * 0.01), "In Library": False, "Genres": ["mystery"]}
            for i in range(5)
        ]

        result = _blend_library_and_discovery(pd.DataFrame(rows), top_n=10, style="balanced")

        self.assertGreaterEqual(sum(not bool(row["In Library"]) for _, row in result.iterrows()), 3)

    def test_weak_external_candidates_are_not_forced_into_results(self):
        rows = [
            {"Title": f"Library {i}", "Authors": f"L{i}", "score": 0.70 - (i * 0.01), "In Library": True, "Genres": ["mystery"]}
            for i in range(10)
        ]
        rows += [
            {"Title": f"Weak External {i}", "Authors": f"E{i}", "score": 0.20 - (i * 0.01), "In Library": False, "Genres": ["mystery"]}
            for i in range(5)
        ]

        result = _blend_library_and_discovery(pd.DataFrame(rows), top_n=10, style="balanced")

        self.assertEqual(sum(not bool(row["In Library"]) for _, row in result.iterrows()), 0)

    def test_diversity_caps_limit_same_author_and_genre(self):
        rows = [
            {"Title": f"Same Author {i}", "Authors": "One Author", "score": 0.90 - (i * 0.01), "In Library": True, "Genres": ["narrow"]} for i in range(5)
        ]
        rows += [
            {"Title": f"Other {i}", "Authors": f"Author {i}", "score": 0.80 - (i * 0.01), "In Library": True, "Genres": [f"genre-{i}"]} for i in range(5)
        ]

        result = _blend_library_and_discovery(pd.DataFrame(rows), top_n=6, style="balanced")

        self.assertLessEqual(sum(row["Authors"] == "One Author" for _, row in result.iterrows()), 2)

    def test_discovery_style_returns_more_external_candidates(self):
        rows = [{"Title": "Read", "Authors": "A", "ISBN/UID": "r1", "Read Status": "read", "Star Rating": 5, "Genres": ["fantasy"]}]
        rows += [
            {"Title": f"Owned {i}", "Authors": f"B{i}", "ISBN/UID": f"t{i}", "Read Status": "to-read", "Genres": ["fantasy"], "In Library": True}
            for i in range(5)
        ]
        rows += [
            {"Title": f"External {i}", "Authors": f"C{i}", "ISBN/UID": f"x{i}", "Read Status": "to-read", "Genres": ["fantasy"], "In Library": False}
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

    def test_exact_rejected_work_receives_temporary_penalty(self):
        rows = [
            {"Title": "Loved Mystery", "Authors": "A", "ISBN/UID": "r1", "Read Status": "read", "Star Rating": 5, "Genres": ["mystery"]},
            {"Title": "Rejected", "Authors": "B", "ISBN/UID": "reject", "Read Status": "to-read", "Genres": ["mystery"]},
            {"Title": "Alternative", "Authors": "C", "ISBN/UID": "alt", "Read Status": "to-read", "Genres": ["mystery"]},
        ]

        result = build_recommendations(
            pd.DataFrame(rows),
            top_n=2,
            feedback_records=[
                {
                    "recommendation_id": "isbn:REJECT",
                    "isbn": "reject",
                    "feedback_type": "not_interested",
                    "related_genres": ["mystery"],
                }
            ],
        )

        self.assertEqual(result[0]["book"]["title"], "Alternative")
        rejected = next(item for item in result if item["book"]["title"] == "Rejected")
        self.assertGreater(rejected["score_breakdown"]["recommendation_feedback_penalty"], 0.6)

    def test_repeated_feedback_strengthens_exact_penalty(self):
        rows = [
            {"Title": "Loved Mystery", "Authors": "A", "ISBN/UID": "r1", "Read Status": "read", "Star Rating": 5, "Genres": ["mystery"]},
            {"Title": "Rejected", "Authors": "B", "ISBN/UID": "reject", "Read Status": "to-read", "Genres": ["mystery"]},
        ]

        once = build_recommendations(
            pd.DataFrame(rows),
            top_n=1,
            feedback_records=[{"recommendation_id": "isbn:REJECT", "isbn": "reject", "feedback_type": "not_interested"}],
        )[0]
        repeated = build_recommendations(
            pd.DataFrame(rows),
            top_n=1,
            feedback_records=[
                {"recommendation_id": "isbn:REJECT", "isbn": "reject", "feedback_type": "not_interested"},
                {"recommendation_id": "isbn:REJECT", "isbn": "reject", "feedback_type": "not_interested"},
            ],
        )[0]

        self.assertGreater(
            repeated["score_breakdown"]["recommendation_feedback_penalty"],
            once["score_breakdown"]["recommendation_feedback_penalty"],
        )

    def test_one_rejection_does_not_eliminate_entire_genre(self):
        rows = [
            {"Title": "Loved Fantasy", "Authors": "A", "ISBN/UID": "r1", "Read Status": "read", "Star Rating": 5, "Genres": ["fantasy"]},
            {"Title": "Rejected Fantasy", "Authors": "B", "ISBN/UID": "reject", "Read Status": "to-read", "Genres": ["fantasy"]},
            {"Title": "Other Fantasy", "Authors": "C", "ISBN/UID": "other", "Read Status": "to-read", "Genres": ["fantasy"]},
        ]

        result = build_recommendations(
            pd.DataFrame(rows),
            top_n=2,
            feedback_records=[
                {
                    "recommendation_id": "isbn:REJECT",
                    "isbn": "reject",
                    "feedback_type": "not_interested",
                    "related_genres": ["fantasy"],
                }
            ],
        )

        self.assertIn("Other Fantasy", [item["book"]["title"] for item in result])
        other = next(item for item in result if item["book"]["title"] == "Other Fantasy")
        self.assertEqual(other["score_breakdown"].get("similar_feedback_penalty"), 0.0)

    def test_specific_modern_mystery_beats_dense_generic_classic_metadata(self):
        rows = [
            {
                "Title": "The Naturals",
                "Authors": "Jennifer Lynn Barnes",
                "ISBN/UID": "naturals",
                "Read Status": "read",
                "Star Rating": 5,
                "Genres": ["mystery"],
                "Subjects": ["criminal profiling"],
            },
            {
                "Title": "Modern Profiling Mystery",
                "Authors": "Modern Author",
                "ISBN/UID": "modern",
                "Read Status": "to-read",
                "Genres": ["mystery"],
                "Subjects": ["criminal profiling"],
            },
            {
                "Title": "Generic Dense Classic",
                "Authors": "Classic Author",
                "ISBN/UID": "classic",
                "Read Status": "to-read",
                "Genres": ["fiction", "drama", "literature"],
                "Subjects": ["fiction", "drama", "new york times bestseller", "general"],
            },
        ]

        result = build_recommendations(pd.DataFrame(rows), top_n=2)

        self.assertEqual(result[0]["book"]["title"], "Modern Profiling Mystery")
        self.assertNotIn("Generic Dense Classic", [item["book"]["title"] for item in result])

    def test_candidate_sharing_only_drama_is_rejected(self):
        rows = [
            {"Title": "Liked Play", "Authors": "A", "ISBN/UID": "liked", "Read Status": "read", "Star Rating": 5, "Genres": ["drama"]},
            {"Title": "Drama Only", "Authors": "B", "ISBN/UID": "drama", "Read Status": "to-read", "Genres": ["drama"], "Subjects": ["fiction"]},
            {"Title": "Specific Alternative", "Authors": "C", "ISBN/UID": "specific", "Read Status": "to-read", "Genres": ["dystopian"], "Subjects": ["political rebellion"]},
        ]

        result = build_recommendations(pd.DataFrame(rows), top_n=2)

        self.assertNotIn("Drama Only", [item["book"]["title"] for item in result])

    def test_low_rated_completed_book_is_not_positive_anchor(self):
        df = pd.DataFrame(
            [
                {"Title": "Disliked Space", "Authors": "A", "ISBN/UID": "r1", "Read Status": "read", "Star Rating": 2, "Genres": ["science fiction"]},
                {"Title": "Loved Mystery", "Authors": "B", "ISBN/UID": "r2", "Read Status": "read", "Star Rating": 5, "Genres": ["mystery"]},
                {"Title": "Space Candidate", "Authors": "C", "ISBN/UID": "t1", "Read Status": "to-read", "Genres": ["science fiction"]},
                {"Title": "Mystery Candidate", "Authors": "D", "ISBN/UID": "t2", "Read Status": "to-read", "Genres": ["mystery"]},
            ]
        )

        result = build_recommendations(df, top_n=2)

        self.assertEqual(result[0]["book"]["title"], "Mystery Candidate")
        self.assertNotIn("Disliked Space", [book["title"] for book in result[0]["matched_liked_books"]])
        self.assertNotIn("Space Candidate", [item["book"]["title"] for item in result])

    def test_dnf_books_contribute_negative_signal(self):
        df = pd.DataFrame(
            [
                {"Title": "DNF Horror", "Authors": "A", "ISBN/UID": "r1", "Read Status": "dnf", "Genres": ["horror"]},
                {"Title": "Loved Essays", "Authors": "B", "ISBN/UID": "r2", "Read Status": "read", "Star Rating": 5, "Genres": ["essays"]},
                {"Title": "Horror Candidate", "Authors": "C", "ISBN/UID": "t1", "Read Status": "to-read", "Genres": ["horror"]},
                {"Title": "Essay Candidate", "Authors": "D", "ISBN/UID": "t2", "Read Status": "to-read", "Genres": ["essays"]},
            ]
        )

        result = build_recommendations(df, top_n=2)
        horror = next(item for item in result if item["book"]["title"] == "Horror Candidate")

        self.assertGreater(horror["score_breakdown"]["negative_preference_penalty"], 0)
        self.assertEqual(result[0]["book"]["title"], "Essay Candidate")

    def test_unrated_completed_book_does_not_outweigh_explicit_rating(self):
        df = pd.DataFrame(
            [
                {"Title": "Unrated Fantasy", "Authors": "A", "ISBN/UID": "r1", "Read Status": "read", "Star Rating": np.nan, "Genres": ["fantasy"]},
                {"Title": "Rated Mystery", "Authors": "B", "ISBN/UID": "r2", "Read Status": "read", "Star Rating": 5, "Genres": ["mystery"]},
                {"Title": "Fantasy Candidate", "Authors": "C", "ISBN/UID": "t1", "Read Status": "to-read", "Genres": ["fantasy"]},
                {"Title": "Mystery Candidate", "Authors": "D", "ISBN/UID": "t2", "Read Status": "to-read", "Genres": ["mystery"]},
            ]
        )

        result = build_recommendations(df, top_n=2)

        self.assertEqual(result[0]["book"]["title"], "Mystery Candidate")

    def test_historical_library_records_remain_preference_evidence(self):
        df = pd.DataFrame(
            [
                {"Title": "Old Favorite", "Authors": "A", "ISBN/UID": "r1", "Read Status": "read", "Star Rating": 5, "End Date": "2001-01-01", "Genres": ["classic"]},
                {"Title": "Classic Candidate", "Authors": "B", "ISBN/UID": "t1", "Read Status": "to-read", "Genres": ["classic"]},
            ]
        )

        result = build_recommendations(df, top_n=1)[0]

        self.assertEqual(result["book"]["title"], "Classic Candidate")
        self.assertIn("Old Favorite", [book["title"] for book in result["matched_liked_books"]])


if __name__ == "__main__":
    unittest.main()
