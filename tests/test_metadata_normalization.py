from backend.services.metadata_normalization import (
    filter_specific_subjects,
    normalize_genre,
    normalize_subject,
    normalize_title_keywords,
    normalize_values,
)


def test_open_library_subjects_are_normalized_and_deduplicated():
    result = normalize_values(["Dystopian Fiction!", "dystopian fiction", ""], normalize_subject)

    assert result == ["dystopian fiction"]


def test_open_library_genres_are_normalized():
    result = normalize_values(["Science-Fiction", " Memoir "], normalize_genre)

    assert result == ["science fiction", "memoir"]


def test_broad_subjects_are_filtered():
    result = filter_specific_subjects(["Fiction", "Books", "Witch trials"])

    assert result == ["witch trials"]


def test_title_keywords_ignore_stopwords_and_generic_words():
    result = normalize_title_keywords("The Complete Book of Love Stories")

    assert result == []
