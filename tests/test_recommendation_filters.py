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
