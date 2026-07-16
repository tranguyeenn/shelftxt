import pandas as pd

from backend.services.recommendation_builder import build_recommendations


def test_series_hard_filter_blocks_book_three_when_book_two_unread():
    df = pd.DataFrame(
        [
            {
                "Title": "The Naturals",
                "Authors": "Jennifer Lynn Barnes",
                "ISBN/UID": "book-1",
                "Read Status": "read",
                "Star Rating": 5,
                "Genres": ["Mystery"],
                "Series Name": "The Naturals",
                "Series Position": 1,
                "Series Type": "main",
            },
            {
                "Title": "Killer Instinct",
                "Authors": "Jennifer Lynn Barnes",
                "ISBN/UID": "book-2",
                "Read Status": "to-read",
                "Star Rating": None,
                "Genres": ["Mystery"],
                "Series Name": "The Naturals",
                "Series Position": 2,
                "Series Type": "main",
            },
            {
                "Title": "All In",
                "Authors": "Jennifer Lynn Barnes",
                "ISBN/UID": "book-3",
                "Read Status": "to-read",
                "Star Rating": None,
                "Genres": ["Mystery"],
                "Series Name": "The Naturals",
                "Series Position": 3,
                "Series Type": "main",
            },
        ]
    )

    titles = [item["title"] for item in build_recommendations(df, top_n=3)]

    assert "Killer Instinct" in titles
    assert "All In" not in titles


def test_outside_library_candidate_can_reach_final_results():
    df = pd.DataFrame(
        [
            {
                "Title": "Read Anchor",
                "Authors": "A",
                "ISBN/UID": "read-1",
                "Read Status": "read",
                "Star Rating": 5,
                "Genres": ["Mystery"],
                "In Library": True,
            },
            {
                "Title": "External Candidate",
                "Authors": "B",
                "ISBN/UID": "external-1",
                "Read Status": "to-read",
                "Star Rating": None,
                "Genres": ["Mystery"],
                "In Library": False,
                "Source Type": "external_discovery",
                "Discovery Source": "open_library",
                "External ID": "external-1",
            },
        ]
    )

    results = build_recommendations(df, top_n=1, style="discovery")

    assert results[0]["title"] == "External Candidate"
    assert results[0]["outside_library"] is True
