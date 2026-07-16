from __future__ import annotations

import re
from dataclasses import dataclass, field

from backend.db.models import Book
from backend.services.status import normalize_status


def normalize_title_alias(value: object) -> str:
    text = str(value or "").casefold()
    text = re.sub(r"\([^)]*\)", " ", text)
    text = re.split(r"\s+[:;]\s+", text, maxsplit=1)[0]
    text = re.sub(r"[^a-z0-9]+", " ", text)
    return " ".join(text.split())


def normalize_author_alias(value: object) -> str:
    author = str(value or "").split(",", 1)[0].strip().casefold()
    return re.sub(r"[^a-z0-9]+", "-", author).strip("-")


def _identity(author: object, canonical_title: object) -> str:
    return f"title_author:{normalize_title_alias(canonical_title).replace(' ', '-')}:{normalize_author_alias(author)}"


@dataclass(frozen=True)
class ComponentWork:
    canonical_work_identity: str
    title: str
    series_position: float | None = None
    work_id: str | None = None


@dataclass(frozen=True)
class CanonicalWork:
    canonical_work_identity: str
    canonical_title: str
    original_title: str | None = None
    language: str | None = None
    edition_identity: str | None = None
    collection_type: str = "single_work"
    component_works: tuple[ComponentWork, ...] = ()
    aliases: tuple[str, ...] = field(default_factory=tuple)


HUNGER_GAMES_COMPONENTS = (
    ComponentWork(_identity("Suzanne Collins", "The Hunger Games"), "The Hunger Games", 1.0, "/works/HUNGER-GAMES-1"),
    ComponentWork(_identity("Suzanne Collins", "Catching Fire"), "Catching Fire", 2.0, "/works/HUNGER-GAMES-2"),
    ComponentWork(_identity("Suzanne Collins", "Mockingjay"), "Mockingjay", 3.0, "/works/HUNGER-GAMES-3"),
)


TRUSTED_SINGLE_WORK_ALIASES: dict[tuple[str, str], dict] = {
    ("sarah-j-maas", "a court of mist and fury"): {
        "canonical_title": "A Court of Mist and Fury",
        "original_title": "A Court of Mist and Fury",
        "aliases": ("a court of mist and fury", "una corte de niebla y furia"),
    },
    ("sarah-j-maas", "una corte de niebla y furia"): {
        "canonical_title": "A Court of Mist and Fury",
        "original_title": "A Court of Mist and Fury",
        "aliases": ("a court of mist and fury", "una corte de niebla y furia"),
    },
    ("suzanne-collins", "the hunger games"): {
        "canonical_title": "The Hunger Games",
        "original_title": "The Hunger Games",
        "aliases": ("the hunger games",),
    },
    ("suzanne-collins", "catching fire"): {
        "canonical_title": "Catching Fire",
        "original_title": "Catching Fire",
        "aliases": ("catching fire",),
    },
    ("suzanne-collins", "mockingjay"): {
        "canonical_title": "Mockingjay",
        "original_title": "Mockingjay",
        "aliases": ("mockingjay",),
    },
    ("mary-shelley", "frankenstein"): {
        "canonical_title": "Frankenstein",
        "original_title": "Frankenstein; or, The Modern Prometheus",
        "aliases": (
            "frankenstein",
            "frankenstein or the modern prometheus",
            "frankenstein the 1818 text",
            "mary shelley s frankenstein or the modern prometheus",
        ),
    },
    ("mary-shelley", "frankenstein or the modern prometheus"): {
        "canonical_title": "Frankenstein",
        "original_title": "Frankenstein; or, The Modern Prometheus",
        "aliases": (
            "frankenstein",
            "frankenstein or the modern prometheus",
            "frankenstein the 1818 text",
            "mary shelley s frankenstein or the modern prometheus",
        ),
    },
    ("mary-shelley", "frankenstein the 1818 text"): {
        "canonical_title": "Frankenstein",
        "original_title": "Frankenstein; or, The Modern Prometheus",
        "aliases": (
            "frankenstein",
            "frankenstein or the modern prometheus",
            "frankenstein the 1818 text",
            "mary shelley s frankenstein or the modern prometheus",
        ),
    },
}

TRUSTED_COLLECTION_ALIASES: dict[tuple[str, str], dict] = {
    ("suzanne-collins", "the hunger games trilogy"): {
        "canonical_title": "The Hunger Games Trilogy",
        "original_title": "The Hunger Games Trilogy",
        "collection_type": "omnibus",
        "components": HUNGER_GAMES_COMPONENTS,
        "aliases": (
            "the hunger games trilogy",
            "the hunger games trilogy hunger games catching fire mockingjay",
            "hunger games trilogy",
        ),
    },
}


def _trusted_record(title: object, author: object) -> dict | None:
    title_key = normalize_title_alias(title)
    author_key = normalize_author_alias(author)
    key = (author_key, title_key)
    if key in TRUSTED_COLLECTION_ALIASES:
        return TRUSTED_COLLECTION_ALIASES[key]
    if key in TRUSTED_SINGLE_WORK_ALIASES:
        return TRUSTED_SINGLE_WORK_ALIASES[key]
    for (known_author, known_title), record in TRUSTED_COLLECTION_ALIASES.items():
        if known_author == author_key and title_key in {normalize_title_alias(alias) for alias in record.get("aliases", ())}:
            return record
    for (known_author, known_title), record in TRUSTED_SINGLE_WORK_ALIASES.items():
        if known_author == author_key and title_key in {normalize_title_alias(alias) for alias in record.get("aliases", ())}:
            return record
    return None


def canonical_work_for_values(
    *,
    title: object,
    author: object,
    work_key: object = None,
    edition_key: object = None,
    isbn: object = None,
    language: object = None,
    original_title: object = None,
    related_isbns: list[str] | None = None,
) -> CanonicalWork:
    record = _trusted_record(title, author)
    title_text = str(title or "").strip() or "Untitled"
    title_key = normalize_title_alias(title_text)
    author_key = normalize_author_alias(author)
    canonical_title = str((record or {}).get("canonical_title") or original_title or title_text).strip()
    raw_work = str(work_key or "").strip()
    if record:
        canonical_identity = _identity(author, canonical_title)
    elif raw_work:
        canonical_identity = f"work:{re.sub(r'\\s+', '', raw_work).casefold()}"
    else:
        canonical_identity = _identity(author, canonical_title)
    edition = str(edition_key or isbn or "").strip() or None
    if edition:
        edition_identity = f"edition:{re.sub(r'\\s+', '', edition).casefold()}"
    else:
        edition_identity = f"title_author:{normalize_title_alias(title_text).replace(' ', '-')}:{author_key}"
    components = tuple((record or {}).get("components") or ())
    collection_type = str((record or {}).get("collection_type") or "single_work")
    if collection_type == "single_work" and any(term in title_key for term in ("boxed set", "box set", "trilogy", "omnibus")):
        collection_type = "box_set" if "box" in title_key else "omnibus"
    return CanonicalWork(
        canonical_work_identity=canonical_identity,
        canonical_title=canonical_title,
        original_title=str((record or {}).get("original_title") or original_title or canonical_title).strip() or None,
        language=str(language or "").strip() or None,
        edition_identity=edition_identity,
        collection_type=collection_type,
        component_works=components,
        aliases=tuple(str(alias) for alias in (record or {}).get("aliases", ()) if str(alias).strip()),
    )


def canonical_work_for_result(result: dict) -> CanonicalWork:
    authors = result.get("authors") or []
    author = authors[0] if authors else result.get("author")
    return canonical_work_for_values(
        title=result.get("title"),
        author=author,
        work_key=result.get("work_key") or result.get("work_id"),
        edition_key=result.get("edition_key") or result.get("edition_id"),
        isbn=result.get("isbn_uid") or result.get("isbn"),
        language=result.get("language"),
        original_title=result.get("original_title"),
        related_isbns=result.get("related_isbns") or [],
    )


def canonical_work_for_book(book: Book) -> CanonicalWork:
    metadata = book.book_metadata if isinstance(book.book_metadata, dict) else {}
    return canonical_work_for_values(
        title=book.title,
        author=book.authors,
        work_key=book.work_key,
        edition_key=book.edition_key,
        isbn=book.isbn_uid,
        language=book.language,
        original_title=metadata.get("original_title") or getattr(book, "original_title", None),
    )


def completed_component_identities(library_books: list[Book]) -> set[str]:
    identities: set[str] = set()
    for book in library_books:
        status = normalize_status(
            book.read_status,
            progress_percent=float(book.progress_percent or 0),
            pages_read=int(book.pages_read or 0),
        )
        if status == "completed":
            identities.add(canonical_work_for_book(book).canonical_work_identity)
    return identities


def owned_component_identities(library_books: list[Book]) -> set[str]:
    return {canonical_work_for_book(book).canonical_work_identity for book in library_books}
