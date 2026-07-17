from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass(frozen=True)
class CandidateIntegrity:
    classification: str
    confidence: float
    evidence: tuple[str, ...]
    recommendation_eligible: bool


INELIGIBLE_CLASSIFICATIONS = {"omnibus", "boxed_set", "bundle"}


def _text(value: object) -> str:
    return str(value or "").strip()


def _haystack(candidate: dict) -> str:
    parts: list[str] = []
    for key in ("title", "subtitle", "headline", "description"):
        parts.append(_text(candidate.get(key)))
    for key in ("genres", "subjects", "cached_tags"):
        values = candidate.get(key)
        if isinstance(values, (list, tuple)):
            parts.extend(_text(value) for value in values)
        else:
            parts.append(_text(values))
    return " ".join(part for part in parts if part).casefold()


def _title(candidate: dict) -> str:
    return _text(candidate.get("title")).casefold()


def _evidence(pattern: str, text: str, label: str) -> str | None:
    return label if re.search(pattern, text, flags=re.IGNORECASE) else None


def evaluate_candidate_integrity(candidate: dict) -> CandidateIntegrity:
    title = _title(candidate)
    text = _haystack(candidate)
    evidence: list[str] = []

    anthology = _evidence(r"\b(anthology|short stories|stories and poems|collected stories)\b", text, "anthology_metadata")
    if anthology:
        evidence.append(anthology)

    boxed = [
        _evidence(r"\b(boxed|box)\s+set\b", title, "title_boxed_set"),
        _evidence(r"\b(set|collection)\s+boxed\b", title, "title_boxed_collection"),
        _evidence(r"\bbox\s+set\b", text, "metadata_box_set"),
    ]
    evidence.extend(item for item in boxed if item)
    if any(boxed):
        return CandidateIntegrity("boxed_set", 0.95, tuple(evidence), False)

    bundle = [
        _evidence(r"\bbooks?\s+\d+\s*(?:-|–|—|to|&|and)\s*\d+\b", title, "title_books_range"),
        _evidence(r"\b(?:volumes?|vols?)\s+\d+\s*(?:-|–|—|to|&|and)\s*\d+\b", title, "title_volumes_range"),
        _evidence(r"\b\d+\s*(?:book|volume)\s+(?:collection|bundle|set)\b", title, "title_multi_book_bundle"),
        _evidence(r"\bcollection\s+\d+\s*books?\s+set\b", title, "title_collection_books_set"),
        _evidence(r"\b(?:book|volume)\s+bundle\b", text, "metadata_book_bundle"),
    ]
    evidence.extend(item for item in bundle if item)
    if any(bundle):
        return CandidateIntegrity("bundle", 0.9, tuple(evidence), False)

    omnibus = [
        _evidence(r"\bomnibus\b", text, "omnibus_metadata"),
        _evidence(r"\bcomplete\s+(?:series|collection|set|saga)\b", title, "title_complete_series"),
        _evidence(r"\bcomplete\s+[a-z0-9' -]+(?:chronicles|saga|series)\b", title, "title_complete_named_series"),
        _evidence(r"\b(?:trilogy|quartet|duology)\b", title, "title_multi_book_series"),
        _evidence(r"\b(?:books?|volumes?)\s+\d+\s*(?:-|–|—|to)\s*\d+\b", text, "metadata_books_range"),
    ]
    evidence.extend(item for item in omnibus if item)
    if any(omnibus):
        return CandidateIntegrity("omnibus", 0.88, tuple(evidence), False)

    if anthology:
        return CandidateIntegrity("anthology", 0.75, tuple(evidence), True)

    if title:
        return CandidateIntegrity("individual_book", 0.65, tuple(evidence), True)
    return CandidateIntegrity("unknown", 0.2, tuple(evidence), True)
