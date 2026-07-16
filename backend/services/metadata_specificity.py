from __future__ import annotations

import re

ZERO_SPECIFICITY_TERMS = {
    "fiction",
    "drama",
    "novel",
    "novels",
    "book",
    "books",
    "literature",
    "bestseller",
    "new york times bestseller",
    "juvenile fiction",
    "children's fiction",
    "children s fiction",
    "general",
    "reading",
}

LOW_SPECIFICITY_TERMS = {
    "young adult",
    "young adult fiction",
    "contemporary",
    "romance",
    "fantasy",
    "mystery",
    "historical fiction",
}

HIGH_SPECIFICITY_PHRASES = {
    "academic rivals",
    "criminal profiling",
    "detective and mystery stories",
    "dystopian",
    "enemies to lovers",
    "locked room mystery",
    "political rebellion",
    "psychological thriller",
    "russian realism",
    "serial murders",
    "survival competition",
    "women in stem",
}


def normalize_specificity_term(value: object) -> str:
    return re.sub(r"[^a-z0-9]+", " ", str(value or "").casefold()).strip()


def metadata_specificity(value: object) -> float:
    term = normalize_specificity_term(value)
    if not term:
        return 0.0
    if term in ZERO_SPECIFICITY_TERMS:
        return 0.0
    if term in LOW_SPECIFICITY_TERMS:
        return 0.2
    if term in HIGH_SPECIFICITY_PHRASES:
        return 1.0
    if any(phrase in term for phrase in HIGH_SPECIFICITY_PHRASES):
        return 1.0
    if len(term.split()) >= 2:
        return 0.75
    return 0.5


def is_generic_metadata(value: object) -> bool:
    return metadata_specificity(value) <= 0.0


def specific_terms(values: list[str] | tuple[str, ...] | set[str], *, minimum: float = 0.5) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for value in values:
        key = normalize_specificity_term(value)
        if not key or key in seen or metadata_specificity(key) < minimum:
            continue
        seen.add(key)
        result.append(str(value))
    return result
