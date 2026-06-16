import re
import unicodedata
from collections.abc import Iterable


_PUNCT_RE = re.compile(r"[^\w\s]", re.UNICODE)
_SPACE_RE = re.compile(r"\s+")

TITLE_STOPWORDS = {
    "a",
    "an",
    "and",
    "are",
    "as",
    "at",
    "by",
    "for",
    "from",
    "in",
    "into",
    "is",
    "of",
    "on",
    "or",
    "the",
    "to",
    "with",
}

GENERIC_TITLE_WORDS = {
    "book",
    "novel",
    "story",
    "stories",
    "edition",
    "volume",
    "selected",
    "collected",
    "complete",
    "introduction",
    "life",
    "love",
    "world",
}

BROAD_SUBJECTS = {
    "book",
    "books",
    "classic",
    "classics",
    "drama",
    "fiction",
    "general",
    "history",
    "juvenile fiction",
    "language arts disciplines",
    "literature",
    "nonfiction",
    "text",
}


def normalize_text(value: object) -> str:
    if value is None:
        return ""
    text = unicodedata.normalize("NFKC", str(value)).lower()
    text = _PUNCT_RE.sub(" ", text)
    return _SPACE_RE.sub(" ", text).strip()


def normalize_author(value: object) -> str:
    return normalize_text(value)


def normalize_subject(value: object) -> str:
    return normalize_text(value)


def normalize_genre(value: object) -> str:
    return normalize_text(value)


def normalize_language(value: object) -> str:
    text = normalize_text(value)
    aliases = {
        "en": "english",
        "eng": "english",
        "en us": "english",
        "en gb": "english",
        "english language": "english",
        "vi": "vietnamese",
        "vie": "vietnamese",
        "vietnamese language": "vietnamese",
    }
    return aliases.get(text, text)


def _flatten_values(values: object) -> list[object]:
    if values is None:
        return []
    if isinstance(values, str):
        return [part for part in re.split(r"[,;|]", values)]
    if isinstance(values, Iterable):
        flattened: list[object] = []
        for value in values:
            flattened.extend(_flatten_values(value) if not isinstance(value, str) else [value])
        return flattened
    return [values]


def normalize_values(values: object, normalizer) -> list[str]:
    seen: set[str] = set()
    normalized: list[str] = []
    for value in _flatten_values(values):
        item = normalizer(value)
        if not item or item in seen:
            continue
        seen.add(item)
        normalized.append(item)
    return normalized


def normalize_title_keywords(value: object) -> list[str]:
    words = normalize_text(value).split()
    seen: set[str] = set()
    keywords: list[str] = []
    for word in words:
        if len(word) < 4 or word in TITLE_STOPWORDS or word in GENERIC_TITLE_WORDS:
            continue
        if word in seen:
            continue
        seen.add(word)
        keywords.append(word)
    return keywords


def filter_specific_subjects(values: object) -> list[str]:
    return [
        value
        for value in normalize_values(values, normalize_subject)
        if value not in BROAD_SUBJECTS
    ]


def filter_specific_genres(values: object) -> list[str]:
    return [
        value
        for value in normalize_values(values, normalize_genre)
        if value not in BROAD_SUBJECTS
    ]
