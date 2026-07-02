from backend.services.metadata_normalization import (
    clean_reader_tags,
    filter_specific_subjects,
    genre_confidence_scores,
    normalize_genre,
    normalize_genre_list,
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


def test_machine_subjects_and_identifiers_are_filtered():
    result = filter_specific_subjects(
        [
            "Censorship",
            "censorship",
            "123456",
            "OCLC:12345",
            "list:OL123L",
            "Internet Archive",
            "Grade level 7",
            "Political fiction",
        ]
    )

    assert result == ["censorship", "political fiction"]


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


def test_noisy_single_word_subjects_are_not_genre_evidence():
    assert subjects_to_genres(["romance"]) == []
    assert subjects_to_genres(["romance fiction"]) == ["romance"]
    assert subjects_to_genres(["love stories"]) == ["romance"]
    assert subjects_to_genres(["detective and mystery stories"]) == ["mystery"]
    assert subjects_to_genres(["mystery"]) == []
    assert subjects_to_genres(["murder", "crime", "criminal"]) == []
    assert subjects_to_genres(["drama"]) == []
    assert subjects_to_genres(["plays"]) == ["drama"]
    assert subjects_to_genres(["history"]) == []


def test_explicit_reader_genre_still_accepts_romance():
    assert normalize_genre_list(["romance"]) == ["Romance"]


def test_heart_of_darkness_subject_noise_does_not_add_false_genres():
    subjects = [
        "form novella",
        "genre historical fiction",
        "romance",
        "degeneration",
        "description and travel",
        "diaries",
        "sailors",
        "short stories",
        "english literature",
        "suffering",
        "trading posts",
        "classic literature",
        "travel",
        "discovery and exploration",
        "mystery",
        "open library staff picks",
        "drama",
        "fugitives from justice",
        "english psychological fiction",
        "imperialism",
        "psychological fiction",
        "detective and mystery stories",
        "history",
        "study guides",
        "examinations",
        "fiction historical general",
        "literary criticism",
        "good and evil",
        "kolonialismus",
    ]

    result = subjects_to_genres(subjects)

    assert "romance" not in result
    assert "drama" not in result
    assert "historical fiction" in result
    assert "literary fiction" in result


def test_reader_tag_cleaner_removes_open_library_cataloging_noise():
    result = clean_reader_tags(
        [
            "reading level grade 11",
            "Large type books",
            "Dramatic works by one author",
            "Fiction General",
            "Dystopias",
            "Love stories",
            "Historical Fiction",
            "historical fiction",
            "continental european drama dramatic works by one author",
        ]
    )

    assert result == ["Dystopian", "Romance", "Historical Fiction"]
