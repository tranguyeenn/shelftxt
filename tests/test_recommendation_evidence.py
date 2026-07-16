import pandas as pd

from backend.services.recommendation_evidence import (
    apply_minimum_evidence_filter,
    has_minimum_positive_evidence,
    strong_classification_allowed,
    valid_anchor_similarity,
)


def test_anchor_similarity_threshold_is_deterministic():
    assert valid_anchor_similarity(0.15)
    assert not valid_anchor_similarity(0.149)


def test_minimum_evidence_filter_keeps_fallback_only_when_no_evidence_exists():
    strong = pd.Series({"_signal_scores": {"candidate_similarity": 0.2}})
    weak = pd.Series({"_signal_scores": {"candidate_similarity": 0.01, "genre_fit": 1.0}})
    ranked = pd.DataFrame([strong, weak])

    filtered = apply_minimum_evidence_filter(ranked)

    assert list(filtered.index) == [0]
    assert has_minimum_positive_evidence(strong)
    assert not has_minimum_positive_evidence(weak)


def test_minimum_evidence_filter_allows_cold_start_fallback():
    ranked = pd.DataFrame(
        [
            {"_signal_scores": {"candidate_similarity": 0.0}},
            {"_signal_scores": {"candidate_similarity": 0.01}},
        ]
    )

    filtered = apply_minimum_evidence_filter(ranked)

    assert list(filtered.index) == [0, 1]


def test_strong_classification_requires_explicit_evidence():
    assert strong_classification_allowed(anchor_similarity=0.15)
    assert strong_classification_allowed(direct_series_match=True)
    assert strong_classification_allowed(direct_author_match=True)
    assert strong_classification_allowed(semantic_similarity=0.7, metadata_overlap=0.5)
    assert not strong_classification_allowed(semantic_similarity=0.7, metadata_overlap=0.1)
    assert not strong_classification_allowed(anchor_similarity=0.1)
