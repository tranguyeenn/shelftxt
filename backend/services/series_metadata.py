from __future__ import annotations

import re
from typing import Any

from backend.db.models import Book
from backend.services.status import normalize_status

SERIES_TYPES = {"main_series", "prequel", "novella", "companion", "spin-off"}
MAIN_SERIES_TYPES = {None, "main_series"}
NATURALS_SERIES_BOOKS = [
    {
        "title": "The Naturals",
        "author": "Jennifer Lynn Barnes",
        "isbn": "9781423168232",
        "work_id": "/works/OL19987694W",
        "position": 1.0,
        "position_label": "Book 1",
        "installment_type": "main_series",
    },
    {
        "title": "Killer Instinct",
        "author": "Jennifer Lynn Barnes",
        "isbn": "9781423168324",
        "work_id": "/works/OL19987695W",
        "position": 2.0,
        "position_label": "Book 2",
        "installment_type": "main_series",
    },
    {
        "title": "All In",
        "author": "Jennifer Lynn Barnes",
        "isbn": "9781484716434",
        "work_id": "/works/OL20011828W",
        "position": 3.0,
        "position_label": "Book 3",
        "installment_type": "main_series",
    },
    {
        "title": "Bad Blood",
        "author": "Jennifer Lynn Barnes",
        "isbn": "9781484757321",
        "work_id": "/works/OL17639867W",
        "position": 4.0,
        "position_label": "Book 4",
        "installment_type": "main_series",
    },
]

HUNGER_GAMES_SERIES_BOOKS = [
    {
        "title": "The Hunger Games",
        "author": "Suzanne Collins",
        "isbn": "9780439023481",
        "work_id": "/works/HUNGER-GAMES-1",
        "position": 1.0,
        "position_label": "Book 1",
        "installment_type": "main_series",
    },
    {
        "title": "Catching Fire",
        "author": "Suzanne Collins",
        "isbn": "9780439023498",
        "work_id": "/works/HUNGER-GAMES-2",
        "position": 2.0,
        "position_label": "Book 2",
        "installment_type": "main_series",
    },
    {
        "title": "Mockingjay",
        "author": "Suzanne Collins",
        "isbn": "9780439023511",
        "work_id": "/works/HUNGER-GAMES-3",
        "position": 3.0,
        "position_label": "Book 3",
        "installment_type": "main_series",
    },
]

THRONE_OF_GLASS_SERIES_BOOKS = [
    {
        "title": "Throne of Glass",
        "author": "Sarah J. Maas",
        "work_id": "/works/OL16607146W",
        "position": 1.0,
        "position_label": "Book 1",
        "installment_type": "main_series",
    },
    {
        "title": "Crown of Midnight",
        "author": "Sarah J. Maas",
        "work_id": "/works/OL16809980W",
        "position": 2.0,
        "position_label": "Book 2",
        "installment_type": "main_series",
    },
    {
        "title": "Heir of Fire",
        "author": "Sarah J. Maas",
        "work_id": "/works/OL17367560W",
        "position": 3.0,
        "position_label": "Book 3",
        "installment_type": "main_series",
    },
    {
        "title": "Queen of Shadows",
        "author": "Sarah J. Maas",
        "work_id": "/works/OL17718538W",
        "position": 4.0,
        "position_label": "Book 4",
        "installment_type": "main_series",
    },
    {
        "title": "Empire of Storms",
        "author": "Sarah J. Maas",
        "position": 5.0,
        "position_label": "Book 5",
        "installment_type": "main_series",
    },
    {
        "title": "Tower of Dawn",
        "author": "Sarah J. Maas",
        "position": 6.0,
        "position_label": "Book 6",
        "installment_type": "main_series",
    },
    {
        "title": "Kingdom of Ash",
        "author": "Sarah J. Maas",
        "position": 7.0,
        "position_label": "Book 7",
        "installment_type": "main_series",
    },
]

SERIES_TITLE_ALIASES = {
    ("sarah maas", "trono de cristal"): ("Throne of Glass", THRONE_OF_GLASS_SERIES_BOOKS, 1.0),
    ("sarah j maas", "trono de cristal"): ("Throne of Glass", THRONE_OF_GLASS_SERIES_BOOKS, 1.0),
}


def _clean(value: object) -> str | None:
    text = " ".join(str(value or "").split())
    return text or None


def _float(value: object) -> float | None:
    try:
        parsed = float(str(value).strip().lstrip("#"))
    except (TypeError, ValueError):
        return None
    return parsed if parsed > 0 else None


def normalize_series_book(value: dict) -> dict | None:
    title = _clean(value.get("title") or value.get("name"))
    if not title:
        return None
    position = _float(value.get("position") or value.get("series_position"))
    return {
        "title": title,
        "author": _clean(value.get("author")),
        "isbn": _clean(value.get("isbn") or value.get("isbn_uid")),
        "work_id": _clean(value.get("work_id") or value.get("work_key")),
        "position": position,
        "position_label": _clean(value.get("position_label") or value.get("series_position_label")),
        "installment_type": normalize_series_type(value.get("installment_type") or value.get("series_type")),
        "publication_year": value.get("publication_year") or value.get("first_publish_year"),
    }


def normalize_series_type(value: object) -> str | None:
    text = (_clean(value) or "").casefold().replace("_", "-")
    if not text:
        return None
    if "prequel" in text:
        return "prequel"
    if "novella" in text or "short" in text:
        return "novella"
    if "companion" in text:
        return "companion"
    if "spin" in text:
        return "spin-off"
    if "main" in text or "novel" in text:
        return "main_series"
    return text if text in SERIES_TYPES else None


def normalize_series_metadata(value: dict | None, *, source: str | None = None) -> dict | None:
    if not isinstance(value, dict):
        return None
    name = _clean(value.get("series_name") or value.get("name"))
    books = [
        book
        for raw in value.get("series_books") or value.get("books") or []
        if isinstance(raw, dict)
        if (book := normalize_series_book(raw))
    ]
    position = _float(value.get("series_position") or value.get("position"))
    if not (name or position or books):
        return None
    confidence = value.get("series_confidence") or value.get("confidence_score") or 0.45
    try:
        confidence_float = max(0.0, min(1.0, float(confidence)))
    except (TypeError, ValueError):
        confidence_float = 0.45
    publication_order = [
        book
        for raw in value.get("series_publication_order") or []
        if isinstance(raw, dict)
        if (book := normalize_series_book(raw))
    ]
    chronological_order = [
        book
        for raw in value.get("series_chronological_order") or []
        if isinstance(raw, dict)
        if (book := normalize_series_book(raw))
    ]
    return {
        "series_name": name,
        "series_position": position,
        "series_position_label": _clean(value.get("series_position_label") or value.get("position_label")),
        "series_type": normalize_series_type(value.get("series_type") or value.get("installment_type")) or "main_series",
        "series_books": books,
        "series_source": _clean(value.get("series_source") or value.get("source") or source),
        "series_confidence": confidence_float,
        "series_publication_order": publication_order or books,
        "series_chronological_order": chronological_order or None,
        "series_evidence": value.get("series_evidence") or [],
    }


def series_from_jsonld(node: dict, *, source: str) -> dict | None:
    part = node.get("isPartOf") or node.get("partOfSeries")
    if isinstance(part, list):
        part = next((item for item in part if isinstance(item, dict)), part[0] if part else None)
    name = None
    if isinstance(part, dict):
        name = _clean(part.get("name"))
    elif isinstance(part, str):
        name = _clean(part)
    position = node.get("position") or node.get("volumeNumber")
    if position is None:
        position = _position_from_title(node.get("name") or node.get("headline"))
    return normalize_series_metadata(
        {
            "series_name": name,
            "series_position": position,
            "series_position_label": f"Book {position}" if position else None,
            "series_source": source,
            "series_confidence": 0.75 if name else 0.35,
            "series_evidence": ["jsonld:isPartOf" if name else "title_position_fallback"],
        },
        source=source,
    )


def _position_from_title(value: object) -> float | None:
    text = str(value or "")
    match = re.search(r"(?:book|volume|#)\s*(\d+(?:\.\d+)?)", text, re.IGNORECASE)
    return _float(match.group(1)) if match else None


def book_series_metadata(book: Book) -> dict | None:
    trusted = _trusted_series_metadata(book)
    if trusted:
        return trusted
    metadata = book.book_metadata or {}
    if not isinstance(metadata, dict):
        metadata = {}
    for key in ("series", "open_library", "librarything", "scraped"):
        value = metadata.get(key)
        if isinstance(value, dict):
            series = normalize_series_metadata(value.get("series") if "series" in value else value, source=key)
            if series:
                return series
    return None


def _trusted_series_metadata(book: Book) -> dict | None:
    title_author = _title_author_key(book.title, book.authors)
    work_key = _clean(book.work_key)
    isbn = _clean(book.isbn_uid)
    for item in NATURALS_SERIES_BOOKS:
        if (
            title_author == _title_author_key(item["title"], item["author"])
            or (work_key and work_key == item.get("work_id"))
            or (isbn and isbn == item.get("isbn"))
        ):
            return normalize_series_metadata(
                {
                    "series_name": "The Naturals",
                    "series_position": item["position"],
                    "series_position_label": item["position_label"],
                    "series_type": "main_series",
                    "series_books": NATURALS_SERIES_BOOKS,
                    "series_source": "trusted_catalog",
                    "series_confidence": 0.98,
                },
                source="trusted_catalog",
            )
    for item in HUNGER_GAMES_SERIES_BOOKS:
        if (
            title_author == _title_author_key(item["title"], item["author"])
            or (work_key and work_key == item.get("work_id"))
            or (isbn and isbn == item.get("isbn"))
        ):
            return normalize_series_metadata(
                {
                    "series_name": "The Hunger Games",
                    "series_position": item["position"],
                    "series_position_label": item["position_label"],
                    "series_type": "main_series",
                    "series_books": HUNGER_GAMES_SERIES_BOOKS,
                    "series_source": "trusted_catalog",
                    "series_confidence": 0.98,
                },
                source="trusted_catalog",
            )
    for item in THRONE_OF_GLASS_SERIES_BOOKS:
        if (
            title_author == _title_author_key(item["title"], item["author"])
            or (work_key and work_key == item.get("work_id"))
            or (isbn and isbn == item.get("isbn"))
        ):
            return normalize_series_metadata(
                {
                    "series_name": "Throne of Glass",
                    "series_position": item["position"],
                    "series_position_label": item["position_label"],
                    "series_type": item["installment_type"],
                    "series_books": THRONE_OF_GLASS_SERIES_BOOKS,
                    "series_source": "trusted_catalog",
                    "series_confidence": 0.98,
                },
                source="trusted_catalog",
            )
    return None


def trusted_series_metadata_for_result(result: dict) -> dict | None:
    title = result.get("title")
    author = _result_author(result)
    work_key = _clean(result.get("work_key") or result.get("work_id"))
    isbn = _clean(result.get("isbn_uid") or result.get("isbn"))
    title_author = _title_author_key(title, author)
    alias_key = (re.sub(r"[^a-z0-9]+", " ", author.casefold()).strip(), re.sub(r"[^a-z0-9]+", " ", str(title or "").casefold()).strip())
    if alias_key in SERIES_TITLE_ALIASES:
        series_name, books, position = SERIES_TITLE_ALIASES[alias_key]
        item = next((book for book in books if _float(book.get("position")) == position), None)
        if item:
            return normalize_series_metadata(
                {
                    "series_name": series_name,
                    "series_position": item["position"],
                    "series_position_label": item["position_label"],
                    "series_type": item.get("installment_type") or "main_series",
                    "series_books": books,
                    "series_source": "trusted_catalog",
                    "series_confidence": 0.98,
                },
                source="trusted_catalog",
            )
    for series_name, books in (
        ("The Naturals", NATURALS_SERIES_BOOKS),
        ("The Hunger Games", HUNGER_GAMES_SERIES_BOOKS),
        ("Throne of Glass", THRONE_OF_GLASS_SERIES_BOOKS),
    ):
        for item in books:
            if (
                title_author == _title_author_key(item["title"], item["author"])
                or (work_key and work_key == item.get("work_id"))
                or (isbn and isbn == item.get("isbn"))
            ):
                return normalize_series_metadata(
                    {
                        "series_name": series_name,
                        "series_position": item["position"],
                        "series_position_label": item["position_label"],
                        "series_type": item.get("installment_type") or "main_series",
                        "series_books": books,
                        "series_source": "trusted_catalog",
                        "series_confidence": 0.98,
                    },
                    source="trusted_catalog",
                )
    return None


def series_metadata_for_result(result: dict) -> dict | None:
    trusted = trusted_series_metadata_for_result(result)
    if trusted:
        return trusted
    raw_series = result.get("series") if isinstance(result.get("series"), dict) else result
    explicit = normalize_series_metadata(raw_series, source=result.get("metadata_source"))
    if explicit and explicit.get("series_name") and explicit.get("series_position"):
        return explicit
    return None


def canonical_series_identity(series_name: object) -> str | None:
    key = _series_key(series_name)
    return f"series:{key.replace(' ', '-')}" if key else None


def canonical_series_states(library_books: list[Book]) -> dict[str, dict]:
    states: dict[str, dict] = {}
    for book in library_books:
        series = book_series_metadata(book)
        if not series or not series.get("series_name") or not series.get("series_books"):
            continue
        series_type = normalize_series_type(series.get("series_type"))
        if series_type not in MAIN_SERIES_TYPES:
            continue
        key = _series_key(series["series_name"])
        entry = states.setdefault(
            key,
            {
                "series_name": series["series_name"],
                "ordered": {},
                "completed_positions": set(),
                "owned_positions": set(),
            },
        )
        for item in series.get("series_publication_order") or series.get("series_books") or []:
            position = _float(item.get("position"))
            item_type = normalize_series_type(item.get("installment_type"))
            if position is None or item_type not in MAIN_SERIES_TYPES:
                continue
            entry["ordered"][position] = item

        current_position = _float(series.get("series_position"))
        if current_position is not None:
            entry["owned_positions"].add(current_position)
            if current_position not in entry["ordered"]:
                entry["ordered"][current_position] = {
                    "title": book.title,
                    "author": book.authors,
                    "isbn": book.isbn_uid,
                    "work_id": book.work_key,
                    "position": current_position,
                    "position_label": series.get("series_position_label"),
                    "installment_type": "main_series",
                    "publication_year": book.first_publish_year,
                }
            status = normalize_status(
                book.read_status,
                progress_percent=float(book.progress_percent or 0),
                pages_read=int(book.pages_read or 0),
            )
            if status == "completed":
                entry["completed_positions"].add(current_position)

    for entry in states.values():
        ordered_positions = sorted(entry["ordered"])
        prefix = 0.0
        expected = 1.0
        completed = entry["completed_positions"]
        while expected in completed:
            prefix = expected
            expected += 1.0
        entry["ordered_list"] = [entry["ordered"][position] for position in ordered_positions]
        entry["longest_contiguous_read_prefix"] = prefix
        entry["next_required_position"] = expected
        entry["next_required_item"] = entry["ordered"].get(expected)
    return states


def result_allowed_by_series_order(result: dict, library_books: list[Book]) -> bool:
    return series_order_decision_for_result(result, library_books)["decision"] == "allowed"


def series_order_decision_for_result(result: dict, library_books: list[Book]) -> dict:
    series = series_metadata_for_result(result)
    if not series or not series.get("series_name"):
        return {
            "decision": "allowed",
            "reason": "series_metadata_missing",
            "series_name": None,
            "canonical_series_identity": None,
            "series_position": None,
            "series_source": None,
            "series_confidence": None,
            "user_owned_positions": [],
            "user_completed_positions": [],
            "required_next_position": None,
        }
    series_type = normalize_series_type(series.get("series_type"))
    is_main = series_type in MAIN_SERIES_TYPES
    series_name = series.get("series_name")
    identity = canonical_series_identity(series_name)
    position = _float(series.get("series_position"))
    states = canonical_series_states(library_books)
    key = _series_key(series_name)
    entry = states.get(key)
    owned_positions = sorted(entry.get("owned_positions", set())) if entry else []
    completed_positions = sorted(entry.get("completed_positions", set())) if entry else []

    if not is_main:
        return {
            "decision": "allowed",
            "reason": "non_main_series_entry",
            "series_name": series_name,
            "canonical_series_identity": identity,
            "series_position": position,
            "series_source": series.get("series_source"),
            "series_confidence": series.get("series_confidence"),
            "user_owned_positions": owned_positions,
            "user_completed_positions": completed_positions,
            "required_next_position": None,
        }

    if position is None:
        return {
            "decision": "allowed",
            "reason": "series_position_missing",
            "series_name": series_name,
            "canonical_series_identity": identity,
            "series_position": None,
            "series_source": series.get("series_source"),
            "series_confidence": series.get("series_confidence"),
            "user_owned_positions": owned_positions,
            "user_completed_positions": completed_positions,
            "required_next_position": None,
        }

    required_next = entry.get("next_required_position") if entry else 1.0
    if position == required_next:
        decision = "allowed"
        reason = "next_unread_installment"
    elif position < required_next:
        decision = "rejected"
        reason = "already_read_or_before_next_unread_installment"
    else:
        decision = "rejected"
        reason = "later_than_next_unread_installment"
    return {
        "decision": decision,
        "reason": reason,
        "series_name": series_name,
        "canonical_series_identity": identity,
        "series_position": position,
        "series_source": series.get("series_source"),
        "series_confidence": series.get("series_confidence"),
        "is_main_series_entry": is_main,
        "user_owned_positions": owned_positions,
        "user_completed_positions": completed_positions,
        "required_next_position": required_next,
    }


def _legacy_result_allowed_by_series_order(result: dict, library_books: list[Book]) -> bool:
    states = canonical_series_states(library_books)
    if not states:
        return True
    match = _result_series_match(result, states)
    if not match:
        return True
    _key, entry, item = match
    next_required = entry.get("next_required_item")
    if not next_required:
        return False
    return _series_item_key(item) == _series_item_key(next_required)


def next_series_candidates(library_books: list[Book]) -> list[dict]:
    owned_titles = {_title_author_key(book.title, book.authors) for book in library_books}
    owned_works = {str(book.work_key or "").strip() for book in library_books if book.work_key}
    owned_isbns = {str(book.isbn_uid or "").strip() for book in library_books if book.isbn_uid}
    candidates: list[dict] = []
    seen: set[str] = set()
    states = canonical_series_states(library_books)
    first_book_by_series = {
        _series_key(series["series_name"]): book
        for book in library_books
        if (series := book_series_metadata(book)) and series.get("series_name")
    }

    for key, state in states.items():
        item = state.get("next_required_item")
        book = first_book_by_series.get(key)
        if not item or not book:
            continue
        candidate_key = _series_item_key(item)
        if candidate_key in seen:
            continue
        if item.get("work_id") and item["work_id"] in owned_works:
            continue
        if item.get("isbn") and item["isbn"] in owned_isbns:
            continue
        if _title_author_key(item.get("title"), item.get("author") or book.authors) in owned_titles:
            continue
        seen.add(candidate_key)
        candidates.append(
            {
                "title": item["title"],
                "authors": [item.get("author") or book.authors],
                "isbn_uid": item.get("isbn"),
                "subjects": book.subjects or [],
                "genres": book.genres or [],
                "metadata_source": "series_metadata",
                "work_key": item.get("work_id"),
                "confidence_score": max(0.5, float(book_series_metadata(book).get("series_confidence") or 0.5)),
                "series": {
                    **book_series_metadata(book),
                    "series_position": item.get("position"),
                    "series_position_label": item.get("position_label"),
                    "series_type": item.get("installment_type") or "main_series",
                },
            }
        )
    return candidates


def _series_item_key(item: dict) -> str:
    return str(item.get("work_id") or item.get("isbn") or _title_author_key(item.get("title"), item.get("author"))).strip()


def _series_key(value: object) -> str:
    return re.sub(r"[^a-z0-9]+", " ", str(value or "").casefold()).strip()


def _result_series_match(result: dict, states: dict[str, dict]) -> tuple[str, dict, dict] | None:
    raw_series = result.get("series") if isinstance(result.get("series"), dict) else {}
    series_name = _clean(result.get("series_name") or raw_series.get("series_name"))
    position = _float(result.get("series_position") or raw_series.get("series_position"))
    if series_name:
        key = _series_key(series_name)
        entry = states.get(key)
        if entry:
            if position is not None and position in entry["ordered"]:
                return key, entry, entry["ordered"][position]
            matched = _match_result_to_ordered_item(result, entry)
            if matched:
                return key, entry, matched

    for key, entry in states.items():
        matched = _match_result_to_ordered_item(result, entry)
        if matched:
            return key, entry, matched
    return None


def _match_result_to_ordered_item(result: dict, entry: dict) -> dict | None:
    result_work = _clean(result.get("work_key") or result.get("work_id"))
    result_isbn = _clean(result.get("isbn_uid") or result.get("isbn"))
    result_title_author = _title_author_key(result.get("title"), _result_author(result))
    for item in entry["ordered"].values():
        if result_work and result_work == item.get("work_id"):
            return item
        if result_isbn and result_isbn == item.get("isbn"):
            return item
        if result_title_author and result_title_author == _title_author_key(item.get("title"), item.get("author")):
            return item
    return None


def _result_author(result: dict) -> str:
    authors = result.get("authors") or []
    return str(authors[0]).strip() if authors else "Unknown author"


def _title_author_key(title: object, author: object) -> str:
    return re.sub(r"[^a-z0-9]+", " ", f"{title or ''} {str(author or '').split(',', 1)[0]}".casefold()).strip()
