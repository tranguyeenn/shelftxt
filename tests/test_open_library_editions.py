from unittest.mock import Mock, patch

from backend.services.book_search import _open_library_results
from backend.services.open_library_editions import (
    edition_fields,
    score_open_library_edition,
    select_best_open_library_edition,
)


def _edition(
    title: str,
    key: str,
    isbn: str,
    cover: int,
    pages: int,
    language: str,
    publisher: str,
    publish_date: str,
) -> dict:
    return {
        "title": title,
        "key": f"/books/{key}",
        "isbn_13": [isbn],
        "covers": [cover],
        "number_of_pages": pages,
        "languages": [{"key": f"/languages/{language}"}],
        "publishers": [publisher],
        "publish_date": publish_date,
    }


def test_small_things_like_these_does_not_select_french_translation():
    french = _edition(
        "Ce genre de petites choses",
        "OL-FR-M",
        "9780000000001",
        11,
        128,
        "fre",
        "Sabine Wespieser",
        "2021",
    )
    english = _edition(
        "Small Things Like These",
        "OL-EN-M",
        "9780802158741",
        22,
        118,
        "eng",
        "Grove Press",
        "2021-11-30",
    )

    selected = select_best_open_library_edition(
        [french, english],
        query="Small Things Like These Claire Keegan",
        displayed_title="Small Things Like These",
        author_work_match=True,
    )

    assert selected is english
    assert score_open_library_edition(
        french,
        query="Small Things Like These Claire Keegan",
        displayed_title="Small Things Like These",
    ) < 0


def test_edition_specific_fields_come_from_one_selected_edition():
    selected = _edition(
        "Small Things Like These",
        "OL-EN-M",
        "9780802158741",
        22,
        118,
        "eng",
        "Grove Press",
        "2021-11-30",
    )

    fields = edition_fields(selected)

    assert fields == {
        "isbn_uid": "9780802158741",
        "cover_url": "https://covers.openlibrary.org/b/id/22-M.jpg?default=false",
        "total_pages": 118,
        "edition_key": "OL-EN-M",
        "publisher": "Grove Press",
        "publish_date": "2021-11-30",
        "language": "eng",
    }


def test_no_good_title_match_leaves_edition_fields_blank():
    french = _edition(
        "Ce genre de petites choses",
        "OL-FR-M",
        "9780000000001",
        11,
        128,
        "fre",
        "Sabine Wespieser",
        "2021",
    )

    selected = select_best_open_library_edition(
        [french],
        query="Small Things Like These Claire Keegan",
        displayed_title="Small Things Like These",
    )

    assert selected is None
    assert all(value is None for value in edition_fields(selected).values())


def test_exact_isbn_search_uses_exact_edition():
    exact = _edition(
        "Ce genre de petites choses",
        "OL-EXACT-M",
        "9780000000001",
        11,
        128,
        "fre",
        "Sabine Wespieser",
        "2021",
    )
    exact["works"] = [{"key": "/works/OL-WORK-W"}]
    response = Mock()
    response.raise_for_status.return_value = None
    response.json.return_value = {
        "docs": [
            {
                "title": "Small Things Like These",
                "author_name": ["Claire Keegan"],
                "key": "/works/OL-WORK-W",
                "first_publish_year": 2021,
            }
        ]
    }

    with (
        patch("backend.services.book_search._fetch_open_library_exact_edition", return_value=exact),
        patch("backend.services.book_search.httpx.get", return_value=response),
        patch("backend.services.book_search._fetch_open_library_work_editions") as fetch_editions,
    ):
        results = _open_library_results("9780000000001")

    assert len(results) == 1
    assert results[0]["title"] == "Ce genre de petites choses"
    assert results[0]["isbn_uid"] == "9780000000001"
    assert results[0]["edition_key"] == "OL-EXACT-M"
    assert results[0]["cover_url"].endswith("/11-M.jpg?default=false")
    assert results[0]["total_pages"] == 128
    fetch_editions.assert_not_called()


def test_title_search_uses_scored_edition_as_an_atomic_record():
    french = _edition(
        "Ce genre de petites choses", "OL-FR-M", "9780000000001", 11, 128,
        "fre", "Sabine Wespieser", "2021",
    )
    english = _edition(
        "Small Things Like These", "OL-EN-M", "9780802158741", 22, 118,
        "eng", "Grove Press", "2021-11-30",
    )
    response = Mock()
    response.raise_for_status.return_value = None
    response.json.return_value = {
        "docs": [{
            "title": "Small Things Like These",
            "author_name": ["Claire Keegan"],
            "key": "/works/OL-WORK-W",
            "first_publish_year": 2021,
        }]
    }

    with (
        patch("backend.services.book_search.httpx.get", return_value=response),
        patch(
            "backend.services.book_search._fetch_open_library_work_editions",
            return_value=[french, english],
        ),
    ):
        result = _open_library_results("Small Things Like These Claire Keegan")[0]

    assert result["title"] == "Small Things Like These"
    assert result["isbn_uid"] == "9780802158741"
    assert result["cover_url"].endswith("/22-M.jpg?default=false")
    assert result["total_pages"] == 118
    assert result["publisher"] == "Grove Press"
    assert result["publish_date"] == "2021-11-30"
