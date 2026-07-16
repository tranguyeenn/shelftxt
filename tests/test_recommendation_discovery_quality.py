from uuid import uuid4

import pandas as pd

from backend.db.models import Book
from backend.services.canonical_work import canonical_work_for_values
from backend.services.metadata_specificity import metadata_specificity
from backend.services.recommendation_discovery import (
    DiscoveryQuery,
    _query_is_specific,
    _structured_discovery_queries,
    discovery_results_per_query,
)
from backend.services.recommendation_evidence import has_minimum_positive_evidence
from backend.services.recommendation_builder import build_recommendations


def _book(
    title,
    author,
    *,
    status="read",
    rating=5,
    genres=None,
    subjects=None,
):
    completed = status in {"read", "completed"}
    return Book(
        user_id=uuid4(),
        title=title,
        authors=author,
        isbn_uid=f"isbn-{title.casefold().replace(' ', '-')}",
        read_status=status,
        star_rating=rating,
        total_pages=300,
        pages_read=300 if completed else 0,
        progress_percent=100 if completed else 0,
        genres=genres or [],
        subjects=subjects or [],
    )


def test_cluster_aware_queries_replace_generic_alice_oseman_queries(monkeypatch):
    monkeypatch.setenv("DISCOVERY_MAX_QUERIES", "8")
    books = [
        _book("Heartstopper, Volume 2", "Alice Oseman", genres=["young adult"], subjects=["drama", "new york times bestseller"]),
        _book("The Naturals", "Jennifer Lynn Barnes", genres=["mystery"], subjects=["criminal profiling", "serial murders"]),
        _book("Book Lovers", "Emily Henry", genres=["romance"], subjects=["contemporary romance"]),
        _book("The Hunger Games", "Suzanne Collins", genres=["dystopian"], subjects=["survival", "rebellion"]),
        _book("Anna Karenina", "Leo Tolstoy", genres=["classic"], subjects=["russian literature", "psychological fiction"]),
    ]

    queries = _structured_discovery_queries(books)
    query_text = [query.query for query in queries]

    assert "Alice Oseman drama" not in query_text
    assert "drama new york times bestseller" not in query_text
    assert any("Jennifer Lynn Barnes" in query.query or "The Naturals" in query.query for query in queries)
    assert any("Emily Henry" in query.query or "Book Lovers" in query.query for query in queries)
    assert any(
        any(term in query.query for term in ["The Hunger Games", "Suzanne Collins", "dystopian", "survival", "rebellion"])
        for query in queries
    )
    assert len(query_text) == len(set(query_text))
    assert len(queries) > 3


def test_translated_and_original_titles_resolve_to_same_canonical_work():
    original = canonical_work_for_values(title="A Court of Mist and Fury", author="Sarah J. Maas")
    translated = canonical_work_for_values(
        title="Una corte de niebla y furia",
        author="Sarah J. Maas",
        work_key="/works/DIFFERENT-EDITION",
        language="spa",
    )

    assert translated.canonical_work_identity == original.canonical_work_identity
    assert translated.original_title == "A Court of Mist and Fury"
    assert translated.edition_identity != original.edition_identity


def test_frankenstein_subtitle_variants_resolve_to_same_canonical_work():
    owned = canonical_work_for_values(title="Frankenstein: The 1818 Text", author="Mary Shelley")
    provider = canonical_work_for_values(
        title="Frankenstein; or, The Modern Prometheus",
        author="Mary Shelley",
        work_key="/works/OL450063W",
    )
    alternate = canonical_work_for_values(
        title="Mary Shelley's Frankenstein; or, the Modern Prometheus (1818 text)",
        author="Mary Shelley",
        work_key="/works/OL25595002W",
    )

    assert provider.canonical_work_identity == owned.canonical_work_identity
    assert alternate.canonical_work_identity == owned.canonical_work_identity


def test_each_meaningful_cluster_receives_a_query(monkeypatch):
    monkeypatch.setenv("DISCOVERY_MAX_QUERIES", "8")
    queries = _structured_discovery_queries(
        [
            _book("The Naturals", "Jennifer Lynn Barnes", genres=["mystery"], subjects=["criminal profiling"]),
            _book("Book Lovers", "Emily Henry", genres=["romance"], subjects=["contemporary romance"]),
            _book("The Hunger Games", "Suzanne Collins", genres=["dystopian"], subjects=["rebellion"]),
            _book("Anna Karenina", "Leo Tolstoy", genres=["classic"], subjects=["russian realism"]),
        ]
    )
    clusters = {query.cluster_id for query in queries}

    assert "ya-mystery-thriller" in clusters
    assert "contemporary-romance-new-adult" in clusters
    assert "ya-dystopian-speculative" in clusters
    assert "literary-classics" in clusters


def test_discovery_results_per_query_is_configurable(monkeypatch):
    monkeypatch.setenv("DISCOVERY_RESULTS_PER_QUERY", "25")

    assert discovery_results_per_query() == 25


def test_generic_terms_alone_are_rejected_as_discovery_queries():
    query = DiscoveryQuery(
        query="drama new york times bestseller",
        cluster_id="generic",
        specific_genres=("drama",),
        specific_themes=("new york times bestseller",),
    )

    assert not _query_is_specific(query.query, query)


def test_metadata_specificity_weights_generic_terms_lower():
    assert metadata_specificity("fiction") == 0.0
    assert metadata_specificity("drama") < metadata_specificity("criminal profiling")
    assert metadata_specificity("young adult") == 0.2
    assert metadata_specificity("criminal profiling") == 1.0


def test_young_adult_alone_cannot_satisfy_minimum_evidence():
    row = pd.Series(
        {
            "Genres": ["young adult"],
            "Subjects": [],
            "_signal_scores": {
                "candidate_similarity": 0.0,
                "genre_fit": 0.7,
                "mood_match": 0.7,
                "author_affinity": 0.0,
            },
            "_feedback_breakdown": {},
        }
    )

    assert not has_minimum_positive_evidence(row)


def test_two_specific_signals_can_satisfy_minimum_evidence():
    row = pd.Series(
        {
            "Genres": ["dystopian"],
            "Subjects": ["political rebellion"],
            "_signal_scores": {
                "candidate_similarity": 0.13,
                "genre_fit": 0.7,
                "mood_match": 0.7,
                "author_affinity": 0.0,
            },
            "_feedback_breakdown": {},
        }
    )

    assert has_minimum_positive_evidence(row)


def test_candidate_sharing_only_drama_is_rejected():
    row = pd.Series(
        {
            "Genres": ["drama"],
            "Subjects": ["fiction", "new york times bestseller"],
            "_signal_scores": {
                "candidate_similarity": 0.01,
                "genre_fit": 0.9,
                "mood_match": 0.9,
                "author_affinity": 0.0,
            },
            "_feedback_breakdown": {},
        }
    )

    assert not has_minimum_positive_evidence(row)


def test_sparse_specific_ya_mystery_beats_dense_generic_classic():
    df = pd.DataFrame(
        [
            {
                "Title": "The Naturals",
                "Authors": "Jennifer Lynn Barnes",
                "ISBN/UID": "owned-naturals",
                "Read Status": "read",
                "Star Rating": 5,
                "Genres": ["young adult mystery"],
                "Subjects": ["criminal profiling"],
                "In Library": True,
            },
            {
                "Title": "Modern Profilers",
                "Authors": "New YA Author",
                "ISBN/UID": "external-modern",
                "Read Status": "to-read",
                "Genres": ["thriller"],
                "Subjects": ["criminal profiling"],
                "In Library": False,
                "Source Type": "external_discovery",
                "Discovery Query": "Jennifer Lynn Barnes young adult mystery thriller",
                "Discovery Cluster ID": "ya-mystery-thriller",
                "Discovery Query Confidence": 0.92,
                "Discovery Anchor Titles": ["The Naturals"],
                "Discovery Anchor Authors": ["Jennifer Lynn Barnes"],
                "Discovery Specific Genres": ["young adult mystery", "thriller"],
                "Discovery Specific Themes": ["criminal profiling"],
                "Provider Metadata Confidence": 0.25,
            },
            {
                "Title": "Generic Old Classic",
                "Authors": "Classic Author",
                "ISBN/UID": "external-classic",
                "Read Status": "to-read",
                "Genres": ["fiction", "drama", "literature"],
                "Subjects": ["novel", "general", "new york times bestseller"],
                "In Library": False,
                "Source Type": "external_discovery",
                "Discovery Query": "drama new york times bestseller",
                "Discovery Cluster ID": "literary-classics",
                "Discovery Query Confidence": 0.4,
                "Provider Metadata Confidence": 0.95,
            },
        ]
    )

    results = build_recommendations(df, top_n=2, style="balanced")
    titles = [item["title"] for item in results]

    assert "Modern Profilers" in titles
    assert "Generic Old Classic" not in titles


def test_romance_candidate_keeps_romance_cluster_attribution():
    df = pd.DataFrame(
        [
            {
                "Title": "Book Lovers",
                "Authors": "Emily Henry",
                "ISBN/UID": "owned-book-lovers",
                "Read Status": "read",
                "Star Rating": 5,
                "Genres": ["contemporary romance"],
                "Subjects": ["publishing", "romantic comedy"],
                "In Library": True,
            },
            {
                "Title": "Lab Partners",
                "Authors": "Romance Author",
                "ISBN/UID": "external-romance",
                "Read Status": "to-read",
                "Genres": ["romance"],
                "Subjects": ["women in STEM", "academic rivals"],
                "In Library": False,
                "Source Type": "external_discovery",
                "Discovery Query": "Emily Henry contemporary romance",
                "Discovery Cluster ID": "contemporary-romance-new-adult",
                "Discovery Query Confidence": 0.9,
                "Discovery Anchor Titles": ["Book Lovers"],
                "Discovery Anchor Authors": ["Emily Henry"],
                "Discovery Specific Genres": ["contemporary romance"],
                "Discovery Specific Themes": ["women in STEM", "academic rivals"],
                "Provider Metadata Confidence": 0.4,
            },
        ]
    )

    result = build_recommendations(df, top_n=1, style="balanced")[0]

    assert result["title"] == "Lab Partners"
    assert result["discovery_cluster_id"] == "contemporary-romance-new-adult"
