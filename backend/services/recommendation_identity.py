from __future__ import annotations

import re


def normalize_identifier(value: object) -> str:
    return re.sub(r"\s+", "", str(value or "").strip()).casefold()


def normalize_isbn(value: object) -> str:
    return re.sub(r"[^0-9Xx]", "", str(value or "")).upper()


def normalize_title(value: object) -> str:
    return re.sub(r"[^a-z0-9]+", "-", str(value or "").casefold()).strip("-")


def normalize_author(value: object) -> str:
    author = str(value or "").split(",", 1)[0].strip()
    return re.sub(r"[^a-z0-9]+", "-", author.casefold()).strip("-")


def recommendation_identity(
    *,
    work_id: str | None,
    isbn: str | None,
    title: str | None,
    author: str | None,
) -> str:
    work = normalize_identifier(work_id)
    if work:
        return f"work:{work}"

    normalized_isbn = normalize_isbn(isbn)
    if normalized_isbn:
        return f"isbn:{normalized_isbn}"

    return f"title_author:{normalize_title(title)}:{normalize_author(author)}"


def recommendation_identity_aliases(
    *,
    work_id: str | None,
    isbn: str | None,
    title: str | None,
    author: str | None,
    related_isbns: list[str] | None = None,
) -> set[str]:
    aliases = {
        recommendation_identity(
            work_id=work_id,
            isbn=isbn,
            title=title,
            author=author,
        )
    }
    work = normalize_identifier(work_id)
    if work:
        aliases.add(f"work:{work}")
    for value in [isbn, *(related_isbns or [])]:
        normalized = normalize_isbn(value)
        if normalized:
            aliases.add(f"isbn:{normalized}")
    title_key = normalize_title(title)
    author_key = normalize_author(author)
    if title_key or author_key:
        aliases.add(f"title_author:{title_key}:{author_key}")
    return {alias for alias in aliases if alias and alias != "title_author::"}
