"""Work-level grouping and edition ranking for search results."""

from __future__ import annotations

import re
import unicodedata
from difflib import SequenceMatcher
from typing import Any


BAD_EDITION_TERMS = {
    "adaptation",
    "adapted",
    "interpretation",
    "study guide",
    "study",
    "guide",
    "summary",
    "summaries",
    "retelling",
    "retold",
}
TRANSLATION_TITLE_TERMS = {"tale", "story", "poem", "book"}
COMMON_TITLE_TOKENS = {"the", "a", "an", "of", "and", "or", "in", "to", "for"}


def strip_diacritics(value: str) -> str:
    return "".join(
        char for char in unicodedata.normalize("NFKD", value)
        if not unicodedata.combining(char)
    )


def normalized_text(value: object) -> str:
    text = strip_diacritics(str(value or "").casefold())
    return " ".join(re.sub(r"[^a-z0-9]+", " ", text).split())


def normalized_author(value: object) -> str:
    text = normalized_text(value)
    if not text:
        return ""
    parts = [part for part in text.split() if len(part) > 1]
    if "," in str(value):
        comma_parts = [normalized_text(part) for part in str(value).split(",", 1)]
        if len(comma_parts) == 2:
            parts = [part for part in f"{comma_parts[1]} {comma_parts[0]}".split() if len(part) > 1]
    if len(parts) == 2:
        forward = " ".join(parts)
        reverse = " ".join(reversed(parts))
        return min(forward, reverse)
    return " ".join(parts)


def best_display_author(editions: list[dict]) -> str:
    names: list[str] = []
    for edition in editions:
        names.extend(str(author).strip() for author in edition.get("authors") or [] if str(author).strip())
    if not names:
        return "Unknown author"
    return sorted(names, key=lambda name: (-len(name), name))[0]


def title_matches(left: object, right: object) -> bool:
    a = normalized_text(left)
    b = normalized_text(right)
    return bool(a and b and (a == b or SequenceMatcher(None, a, b).ratio() >= 0.88))


def title_related(left: object, right: object) -> bool:
    a = normalized_text(left)
    b = normalized_text(right)
    if title_matches(a, b):
        return True
    if a and b and (a in b or b in a):
        return True
    a_tokens = set(a.split()) - COMMON_TITLE_TOKENS
    b_tokens = set(b.split()) - COMMON_TITLE_TOKENS
    shared = {token for token in a_tokens.intersection(b_tokens) if len(token) >= 4}
    if not shared:
        return False
    combined = a_tokens.union(b_tokens)
    if combined.intersection(BAD_EDITION_TERMS) or combined.intersection(TRANSLATION_TITLE_TERMS):
        return True
    return False


def author_matches(left: object, right: object) -> bool:
    a = normalized_author(left)
    b = normalized_author(right)
    return bool(a and b and (a == b or SequenceMatcher(None, a, b).ratio() >= 0.82))


def edition_type(edition: dict, canonical_title: str, query: str) -> str:
    haystack = normalized_text(
        " ".join(
            str(edition.get(field) or "")
            for field in ("title", "description", "publisher")
        )
    )
    title_key = normalized_text(edition.get("title"))
    canonical_key = normalized_text(canonical_title)
    query_key = normalized_text(query)
    if any(term in haystack for term in ("study guide", "summary", "interpretation", "adaptation", "retelling", "retold")):
        return "adaptation"
    if "illustrated" in haystack and canonical_key and canonical_key in query_key:
        return "illustrated"
    if title_key and canonical_key and title_key != canonical_key and not title_matches(title_key, canonical_key):
        return "translation"
    language = normalized_text(edition.get("language"))
    if language and language not in {"en", "eng", "english"} and normalized_text(canonical_title) in query_key:
        return "translation"
    return "original" if title_key and canonical_key and title_matches(title_key, canonical_key) else "unknown"


def edition_rank(edition: dict, *, canonical_title: str, canonical_author: str, query: str) -> float:
    score = float(edition.get("confidence_score") or 0.0)
    if normalized_text(edition.get("title")) == normalized_text(canonical_title):
        score += 2.0
    if author_matches((edition.get("authors") or [""])[0], canonical_author):
        score += 1.5
    if edition_type(edition, canonical_title, query) == "original":
        score += 0.75
    if edition.get("isbn_uid"):
        score += 0.5
    if edition.get("cover_url"):
        score += 0.35
    if edition.get("total_pages"):
        score += 0.25
    publish_date = str(edition.get("publish_date") or edition.get("first_publish_year") or "")
    if re.fullmatch(r"\d{4}-\d{1,2}-\d{1,2}", publish_date):
        score += 0.25
    elif re.search(r"\d{4}", publish_date):
        score += 0.1
    if edition_type(edition, canonical_title, query) in {"adaptation", "illustrated"}:
        score -= 2.5
    if any(term in normalized_text(edition.get("title")) for term in BAD_EDITION_TERMS):
        score -= 2.0
    return score


def _work_match(work: dict, edition: dict) -> bool:
    return title_related(work["canonical_title"], edition.get("title")) and author_matches(
        work["canonical_author"], (edition.get("authors") or [""])[0]
    )


def group_search_results(results: list[dict], query: str) -> list[dict]:
    works: list[dict] = []
    for edition in results:
        edition = dict(edition)
        matched = next((work for work in works if _work_match(work, edition)), None)
        if matched is None:
            matched = {
                "work_key": edition.get("work_key") or f"work:{normalized_text(edition.get('title'))}:{normalized_author((edition.get('authors') or [''])[0])}",
                "canonical_title": edition.get("title") or "Untitled",
                "canonical_author": (edition.get("authors") or ["Unknown author"])[0],
                "editions": [],
            }
            works.append(matched)
        matched["editions"].append(edition)
        matched["canonical_author"] = best_display_author(matched["editions"])

    grouped: list[dict] = []
    for work in works:
        editions = []
        for edition in work["editions"]:
            enriched = dict(edition)
            enriched["edition_type"] = edition_type(enriched, work["canonical_title"], query)
            enriched["_edition_rank"] = edition_rank(
                enriched,
                canonical_title=work["canonical_title"],
                canonical_author=work["canonical_author"],
                query=query,
            )
            editions.append(enriched)
        editions.sort(key=lambda item: (-item["_edition_rank"], str(item.get("title") or "")))
        for edition in editions:
            edition.pop("_edition_rank", None)
        primary = editions[0]
        grouped.append(
            {
                **primary,
                "work_key": work["work_key"],
                "canonical_title": work["canonical_title"],
                "canonical_author": work["canonical_author"],
                "edition_count": len(editions),
                "primary_edition": primary,
                "editions": editions,
            }
        )
    grouped.sort(key=lambda work: (-float(work["primary_edition"].get("confidence_score") or 0.0), work["canonical_title"]))
    return grouped
