import pandas as pd

from backend.services.recommendation_composition import blend_library_and_discovery


def test_close_call_prefers_library_book():
    ranked = pd.DataFrame(
        [
            {"Title": "External", "Authors": "A", "score": 0.72, "In Library": False},
            {"Title": "Library", "Authors": "B", "score": 0.69, "In Library": True},
        ]
    )

    result = blend_library_and_discovery(ranked, top_n=2, style="balanced")

    assert result.iloc[0]["Title"] == "Library"


def test_stronger_external_beats_weak_library_book():
    ranked = pd.DataFrame(
        [
            {"Title": "External", "Authors": "A", "score": 0.72, "In Library": False},
            {"Title": "Library", "Authors": "B", "score": 0.50, "In Library": True},
        ]
    )

    result = blend_library_and_discovery(ranked, top_n=2, style="balanced")

    assert result.iloc[0]["Title"] == "External"


def test_balanced_top_ten_includes_strong_external_target():
    rows = [
        {"Title": f"Library {i}", "Authors": f"L{i}", "score": 0.7 - (i * 0.01), "In Library": True}
        for i in range(8)
    ]
    rows += [
        {"Title": f"External {i}", "Authors": f"E{i}", "score": 0.68 - (i * 0.01), "In Library": False}
        for i in range(4)
    ]

    result = blend_library_and_discovery(pd.DataFrame(rows), top_n=10, style="balanced")

    assert sum(not bool(row["In Library"]) for _, row in result.iterrows()) == 4


def test_global_list_defaults_to_one_title_per_author_when_distinct_authors_exist():
    ranked = pd.DataFrame(
        [
            {"Title": "A1", "Authors": "Same", "score": 0.95, "In Library": True, "Discovery Cluster ID": "fantasy"},
            {"Title": "A2", "Authors": "Same", "score": 0.94, "In Library": True, "Discovery Cluster ID": "fantasy"},
            {"Title": "B1", "Authors": "Other B", "score": 0.80, "In Library": True, "Discovery Cluster ID": "fantasy"},
            {"Title": "C1", "Authors": "Other C", "score": 0.79, "In Library": True, "Discovery Cluster ID": "fantasy"},
        ]
    )

    result = blend_library_and_discovery(ranked, top_n=3, style="balanced")

    assert list(result["Title"]) == ["A1", "B1", "C1"]


def test_second_same_author_allowed_when_not_enough_strong_distinct_authors(monkeypatch):
    monkeypatch.setenv("SECOND_AUTHOR_TITLE_SCORE_THRESHOLD", "0.70")
    ranked = pd.DataFrame(
        [
            {"Title": "A1", "Authors": "Same", "score": 0.95, "In Library": True, "Discovery Cluster ID": "fantasy"},
            {"Title": "A2", "Authors": "Same", "score": 0.90, "In Library": True, "Discovery Cluster ID": "fantasy"},
            {"Title": "B1", "Authors": "Other B", "score": 0.80, "In Library": True, "Discovery Cluster ID": "fantasy"},
        ]
    )

    result = blend_library_and_discovery(ranked, top_n=3, style="balanced")

    assert list(result["Title"]) == ["A1", "A2", "B1"]


def test_second_same_author_allowed_for_strong_different_cluster(monkeypatch):
    monkeypatch.setenv("SECOND_AUTHOR_TITLE_SCORE_THRESHOLD", "0.70")
    ranked = pd.DataFrame(
        [
            {"Title": "A Fantasy", "Authors": "Same", "score": 0.95, "In Library": True, "Discovery Cluster ID": "fantasy"},
            {"Title": "A Romance", "Authors": "Same", "score": 0.90, "In Library": True, "Discovery Cluster ID": "romance"},
            {"Title": "B1", "Authors": "Other B", "score": 0.85, "In Library": True, "Discovery Cluster ID": "fantasy"},
        ]
    )

    result = blend_library_and_discovery(ranked, top_n=3, style="balanced")

    assert "A Romance" in set(result["Title"])


def test_second_same_author_below_threshold_is_rejected_even_on_shortfall(monkeypatch):
    monkeypatch.setenv("SECOND_AUTHOR_TITLE_SCORE_THRESHOLD", "0.90")
    ranked = pd.DataFrame(
        [
            {"Title": "A1", "Authors": "Same", "score": 0.95, "In Library": True, "Discovery Cluster ID": "fantasy"},
            {"Title": "A2", "Authors": "Same", "score": 0.70, "In Library": True, "Discovery Cluster ID": "romance"},
            {"Title": "B1", "Authors": "Other B", "score": 0.80, "In Library": True, "Discovery Cluster ID": "fantasy"},
        ]
    )

    result = blend_library_and_discovery(ranked, top_n=3, style="balanced")

    assert "A2" not in set(result["Title"])
