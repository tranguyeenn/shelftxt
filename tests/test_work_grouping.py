from backend.services.work_grouping import group_search_results, normalized_author


def test_truyen_kieu_groups_nguyen_du_and_du_nguyen():
    results = [
        {"title": "Truyện Kiều", "authors": ["Nguyễn Du"], "metadata_source": "open_library"},
        {"title": "Truyen Kieu", "authors": ["Du Nguyễn"], "metadata_source": "scraped"},
    ]

    works = group_search_results(results, "Truyện Kiều Nguyễn Du")

    assert len(works) == 1
    assert works[0]["canonical_title"] == "Truyện Kiều"
    assert works[0]["canonical_author"] == "Du Nguyễn"
    assert works[0]["edition_count"] == 2
    assert normalized_author("Nguyễn Du") == normalized_author("Du Nguyễn")


def test_tale_of_kieu_translation_is_grouped_and_labeled():
    results = [
        {"title": "Truyện Kiều", "authors": ["Nguyễn Du"], "metadata_source": "open_library"},
        {"title": "The Tale of Kieu", "authors": ["Nguyen Du"], "language": "eng", "metadata_source": "open_library"},
    ]

    works = group_search_results(results, "Truyện Kiều Nguyễn Du")

    assert len(works) == 1
    assert [edition["edition_type"] for edition in works[0]["editions"]] == ["original", "translation"]


def test_exact_title_grouping_and_diacritic_insensitive_matching():
    results = [
        {"title": "Cien años de soledad", "authors": ["Gabriel García Márquez"]},
        {"title": "Cien anos de soledad", "authors": ["Garcia Marquez, Gabriel"]},
    ]

    works = group_search_results(results, "Cien años de soledad Gabriel García Márquez")

    assert len(works) == 1
    assert works[0]["edition_count"] == 2


def test_adaptation_penalty_orders_original_first():
    results = [
        {
            "title": "Dune Study Guide",
            "authors": ["Frank Herbert"],
            "description": "summary and interpretation",
            "cover_url": "cover",
            "isbn_uid": "9780000000001",
            "confidence_score": 0.9,
        },
        {
            "title": "Dune",
            "authors": ["Frank Herbert"],
            "isbn_uid": "9780441172719",
            "confidence_score": 0.6,
        },
    ]

    work = group_search_results(results, "Dune Frank Herbert")[0]

    assert work["primary_edition"]["title"] == "Dune"
    assert work["editions"][1]["edition_type"] == "adaptation"


def test_edition_ordering_prefers_complete_original_edition():
    results = [
        {"title": "Dune", "authors": ["Frank Herbert"], "confidence_score": 0.5},
        {
            "title": "Dune",
            "authors": ["Frank Herbert"],
            "isbn_uid": "9780441172719",
            "cover_url": "cover",
            "total_pages": 412,
            "publish_date": "1965-08-01",
            "confidence_score": 0.5,
        },
    ]

    work = group_search_results(results, "Dune Frank Herbert")[0]

    assert work["primary_edition"]["isbn_uid"] == "9780441172719"


def test_single_edition_shortcut_shape():
    works = group_search_results(
        [{"title": "Kindred", "authors": ["Octavia E. Butler"], "isbn_uid": "9780807083697"}],
        "Kindred Octavia Butler",
    )

    assert len(works) == 1
    assert works[0]["edition_count"] == 1
    assert works[0]["primary_edition"]["title"] == "Kindred"
    assert len(works[0]["editions"]) == 1
