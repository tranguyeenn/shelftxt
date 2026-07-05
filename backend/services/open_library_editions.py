"""Open Library edition scoring and atomic edition-field extraction."""

import re
from difflib import SequenceMatcher
from typing import Any


MIN_EDITION_SCORE = 60.0


def normalize_title(value: object) -> str:
    text = str(value or "").casefold()
    text = re.sub(r"[^a-z0-9]+", " ", text)
    return " ".join(text.split())


def _values(edition: dict, field: str) -> list:
    value = edition.get(field)
    return value if isinstance(value, list) else []


def _has_isbn13(edition: dict) -> bool:
    return any(len(re.sub(r"\D", "", str(value))) == 13 for value in _values(edition, "isbn_13"))


def _language_codes(edition: dict) -> set[str]:
    codes: set[str] = set()
    for value in _values(edition, "languages"):
        key = value.get("key") if isinstance(value, dict) else value
        if key:
            codes.add(str(key).rsplit("/", 1)[-1].casefold())
    return codes


def score_open_library_edition(
    edition: dict,
    *,
    query: str,
    displayed_title: str,
    author_work_match: bool = True,
) -> float:
    """Score one edition without borrowing fields from sibling editions."""
    edition_title = normalize_title(edition.get("title"))
    display_title = normalize_title(displayed_title)
    query_title = normalize_title(query)
    if not edition_title or not display_title:
        return 0.0

    score = 0.0
    if str(edition.get("title") or "").strip().casefold() == displayed_title.strip().casefold():
        score += 110
    elif edition_title == display_title:
        score += 100
    else:
        similarity = SequenceMatcher(None, edition_title, display_title).ratio()
        display_tokens = set(display_title.split())
        edition_tokens = set(edition_title.split())
        if display_tokens and display_tokens.issubset(edition_tokens):
            score += 75
        elif similarity >= 0.82:
            score += 65
        elif similarity >= 0.65:
            score += 35
        elif similarity < 0.45:
            score -= 100

    # The raw search often contains the author too. Containment still confirms
    # the user entered the displayed work title without requiring query parsing.
    if edition_title and edition_title in query_title:
        score += 15
    if author_work_match:
        score += 12
    if _has_isbn13(edition):
        score += 8
    if _values(edition, "covers"):
        score += 6
    if isinstance(edition.get("number_of_pages"), int) and edition["number_of_pages"] > 0:
        score += 6
    if "eng" in _language_codes(edition):
        score += 2
    return score


def select_best_open_library_edition(
    editions: list[dict],
    *,
    query: str,
    displayed_title: str,
    author_work_match: bool = True,
) -> dict | None:
    scored = [
        (
            score_open_library_edition(
                edition,
                query=query,
                displayed_title=displayed_title,
                author_work_match=author_work_match,
            ),
            index,
            edition,
        )
        for index, edition in enumerate(editions)
        if isinstance(edition, dict)
    ]
    if not scored:
        return None
    score, _index, edition = max(scored, key=lambda item: (item[0], -item[1]))
    return edition if score >= MIN_EDITION_SCORE else None


def edition_fields(edition: dict | None) -> dict[str, Any]:
    """Extract edition-bound fields as one indivisible record."""
    if not edition:
        return {
            "isbn_uid": None,
            "cover_url": None,
            "total_pages": None,
            "edition_key": None,
            "publisher": None,
            "publish_date": None,
            "language": None,
        }
    isbn13 = next((str(value) for value in _values(edition, "isbn_13") if value), None)
    isbn10 = next((str(value) for value in _values(edition, "isbn_10") if value), None)
    cover_id = next((value for value in _values(edition, "covers") if isinstance(value, int) and value > 0), None)
    publishers = _values(edition, "publishers")
    key = edition.get("key")
    return {
        "isbn_uid": isbn13 or isbn10,
        "cover_url": (
            f"https://covers.openlibrary.org/b/id/{cover_id}-M.jpg?default=false"
            if cover_id
            else None
        ),
        "total_pages": edition.get("number_of_pages"),
        "edition_key": str(key).rsplit("/", 1)[-1] if key else None,
        "publisher": str(publishers[0]).strip() if publishers else None,
        "publish_date": str(edition.get("publish_date")).strip()
        if edition.get("publish_date")
        else None,
        "language": next(iter(sorted(_language_codes(edition))), None),
    }
