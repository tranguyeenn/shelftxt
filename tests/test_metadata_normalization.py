from backend.services.metadata_normalization import (
    filter_specific_subjects,
    genre_confidence_scores,
    normalize_genre,
    normalize_subject,
    normalize_title_keywords,
    normalize_values,
    subjects_to_genres,
)


def test_open_library_subjects_are_normalized_and_deduplicated():
    result = normalize_values(["Dystopian Fiction!", "dystopian fiction", ""], normalize_subject)

    assert result == ["dystopian fiction"]


def test_open_library_genres_are_normalized():
    result = normalize_values(["Science-Fiction", " Memoir "], normalize_genre)

    assert result == ["science fiction", "memoir"]


def test_broad_subjects_are_filtered():
    result = filter_specific_subjects(["Fiction", "Books", "Adult", "Contemporary", "Witch trials"])

    assert result == ["witch trials"]


def test_title_keywords_ignore_stopwords_and_generic_words():
    result = normalize_title_keywords("The Complete Book of Love Stories")

    assert result == []


def test_subjects_are_mapped_to_normalized_genres():
    result = subjects_to_genres(
        [
            "Dystopias",
            "Dystopian fiction",
            "Fantasy fiction",
            "Detective and mystery stories",
            "Time travel",
            "Fiction",
        ]
    )

    assert result == ["dystopian", "fantasy", "mystery"]


def test_generic_subjects_do_not_create_genres():
    result = subjects_to_genres(["Fiction", "General", "Literature", "Books"])

    assert result == []


def test_weak_single_subject_does_not_create_genre():
    result = subjects_to_genres(["Magic"])

    assert result == []


def test_genre_confidence_requires_strong_or_repeated_support():
    result = genre_confidence_scores(["Magic", "Imaginary places"])

    assert result["fantasy"] == 0.45
    assert subjects_to_genres(["Magic", "Imaginary places"]) == ["fantasy"]
