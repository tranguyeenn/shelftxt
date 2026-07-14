import pandas as pd

from backend.services.recommendation import _apply_recommendation_filters


def test_filters_candidates_without_removing_reading_history():
    books = pd.DataFrame(
        [
            {
                "Title": "Liked History",
                "Read Status": "read",
                "Genres": ["history"],
                "Total Pages": 500,
            },
            {
                "Title": "Matching Romance",
                "Read Status": "to-read",
                "Genres": ["romance"],
                "Total Pages": 300,
            },
            {
                "Title": "Short Romance",
                "Read Status": "to-read",
                "Genres": ["romance"],
                "Total Pages": 100,
            },
            {
                "Title": "Matching History",
                "Read Status": "to-read",
                "Genres": ["history"],
                "Total Pages": 300,
            },
        ]
    )

    filtered = _apply_recommendation_filters(
        books,
        genre="romance",
        min_pages=200,
        max_pages=450,
    )

    assert filtered["Title"].tolist() == ["Liked History", "Matching Romance"]


def test_genre_filter_matches_subjects_with_normalized_case_and_plural_variants():
    books = pd.DataFrame(
        [
            {
                "Title": "Liked Anchor",
                "Read Status": "read",
                "Genres": ["fiction"],
                "Subjects": ["New York Times Bestseller"],
                "Total Pages": 300,
                "Progress (%)": 100,
                "Pages Read": 300,
            },
            {
                "Title": "Subject Candidate",
                "Read Status": "to-read",
                "Genres": [],
                "Subjects": ["New   York Times Bestsellers"],
                "Total Pages": 300,
                "Progress (%)": 0,
                "Pages Read": 0,
            },
            {
                "Title": "Other Candidate",
                "Read Status": "to-read",
                "Genres": ["romance"],
                "Subjects": [],
                "Total Pages": 300,
                "Progress (%)": 0,
                "Pages Read": 0,
            },
        ]
    )

    filtered = _apply_recommendation_filters(
        books,
        genre="New York Times Bestseller",
    )

    assert filtered["Title"].tolist() == ["Liked Anchor", "Subject Candidate"]


def test_genre_filter_excludes_currently_reading_and_dnf_candidates():
    books = pd.DataFrame(
        [
            {
                "Title": "Liked Anchor",
                "Read Status": "read",
                "Genres": ["science fiction"],
                "Subjects": [],
                "Progress (%)": 100,
                "Pages Read": 300,
            },
            {
                "Title": "Eligible Candidate",
                "Read Status": "to-read",
                "Genres": ["science fiction"],
                "Subjects": [],
                "Progress (%)": 0,
                "Pages Read": 0,
            },
            {
                "Title": "Reading Candidate",
                "Read Status": "to-read",
                "Genres": ["science fiction"],
                "Subjects": [],
                "Progress (%)": 20,
                "Pages Read": 40,
            },
            {
                "Title": "DNF Candidate",
                "Read Status": "dnf",
                "Genres": ["science fiction"],
                "Subjects": [],
                "Progress (%)": 0,
                "Pages Read": 0,
            },
        ]
    )

    filtered = _apply_recommendation_filters(books, genre="science fiction")

    assert filtered["Title"].tolist() == ["Liked Anchor", "Eligible Candidate", "Reading Candidate", "DNF Candidate"]
