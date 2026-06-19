import re
import unicodedata
from dataclasses import dataclass
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
    "adult",
    "book",
    "books",
    "contemporary",
    "fiction",
    "general",
    "juvenile fiction",
    "language arts disciplines",
    "literature",
    "nonfiction",
    "novel",
    "novels",
    "text",
}

MAX_GENRES_PER_BOOK = 3
MAX_READER_TAGS = 5

READER_TAG_JUNK_PATTERNS = (
    "reading level",
    "grade",
    "large type",
    "large print",
    "electronic book",
    "accessible book",
    "internet archive",
    "works by one author",
    "fictional works",
    "juvenile",
    "bibliography",
    "translations",
    "adaptations",
    "study guides",
    "examinations",
    "textbooks",
    "protected daisy",
)

READER_TAG_GENERIC = {
    "fiction",
    "general",
    "fiction general",
    "literature",
    "english literature",
    "american literature",
}

READER_TAG_VARIANTS = {
    "dystopia": "Dystopian",
    "dystopias": "Dystopian",
    "dystopies": "Dystopian",
    "dystopian": "Dystopian",
    "dystopian fiction": "Dystopian",
    "love stories": "Romance",
    "love story": "Romance",
    "romance": "Romance",
    "romance fiction": "Romance",
    "young adult": "Young Adult",
    "young adult fiction": "Young Adult",
    "historical": "Historical Fiction",
    "historical fiction": "Historical Fiction",
    "science fiction": "Science Fiction",
    "sci fi": "Science Fiction",
}


@dataclass(frozen=True)
class GenreRule:
    genre: str
    strong: tuple[str, ...]
    weak: tuple[str, ...] = ()


SUBJECT_GENRE_RULES: tuple[GenreRule, ...] = (
    GenreRule("memoir", ("memoir", "autobiography", "personal narratives")),
    GenreRule("nonfiction", ("nonfiction", "biography", "autobiography", "personal narratives")),
    GenreRule("dystopian", ("dystopia", "dystopias", "dystopian", "dystopian fiction")),
    GenreRule("political fiction", ("political fiction", "politics and government", "totalitarianism")),
    GenreRule("gothic fiction", ("gothic fiction", "gothic")),
    GenreRule("science fiction", ("science fiction",), ("space", "time travel", "robots")),
    GenreRule("fantasy", ("fantasy fiction",), ("fantasy", "magic", "imaginary place", "imaginary places")),
    GenreRule("contemporary romance", ("contemporary romance",)),
    GenreRule("romance", ("romance fiction", "love stories", "love story"), ("romance",)),
    GenreRule("mystery", ("detective and mystery", "mystery fiction"), ("murder", "crime", "criminal")),
    GenreRule("historical fiction", ("historical fiction",), ("history", "historical")),
    GenreRule("historical", ("holocaust", "world war", "history")),
    GenreRule("young adult", ("young adult", "juvenile literature"), ("teenage", "coming of age")),
    GenreRule("horror", ("horror fiction",), ("horror", "ghost", "ghosts", "monster", "monsters")),
    GenreRule("literary fiction", ("literary fiction", "psychological fiction")),
    GenreRule("philosophy", ("philosophy", "philosophical fiction")),
    GenreRule("drama", ("drama", "plays", "tragedy")),
    GenreRule("classic", ("classic", "classics")),
)

DIRECT_GENRES = {rule.genre for rule in SUBJECT_GENRE_RULES}


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


def _reader_tag_display(value: str) -> str:
    small_words = {"and", "by", "for", "in", "of", "on", "the", "to", "with"}
    words = value.split()
    return " ".join(word if index > 0 and word in small_words else word.capitalize() for index, word in enumerate(words))


def clean_reader_tags(values: object, *, max_tags: int = MAX_READER_TAGS) -> list[str]:
    tags: list[str] = []
    seen: set[str] = set()
    approved_sources = set(READER_TAG_VARIANTS)
    approved_outputs = {normalize_text(value) for value in READER_TAG_VARIANTS.values()}

    for raw in _flatten_values(values):
        normalized = normalize_text(raw)
        if not normalized:
            continue
        if any(pattern in normalized for pattern in READER_TAG_JUNK_PATTERNS):
            continue
        if normalized in READER_TAG_GENERIC:
            continue
        if len(normalized.split()) > 4 and normalized not in approved_sources and normalized not in approved_outputs:
            continue

        display = READER_TAG_VARIANTS.get(normalized, _reader_tag_display(normalized))
        key = display.lower()
        if key in seen:
            continue
        seen.add(key)
        tags.append(display)
        if len(tags) >= max_tags:
            break

    return tags


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
        if value not in BROAD_SUBJECTS and value in DIRECT_GENRES
    ]


def genre_confidence_scores(values: object) -> dict[str, float]:
    subjects = filter_specific_subjects(values)
    scores: dict[str, float] = {}
    support: dict[str, set[str]] = {}
    for subject in subjects:
        for rule in SUBJECT_GENRE_RULES:
            score = 0.0
            if subject == rule.genre or subject == f"{rule.genre} fiction":
                score = 1.0
            elif any(needle == subject or f"{needle} fiction" == subject for needle in rule.strong):
                score = 0.95
            elif any(needle in subject for needle in rule.strong):
                score = 0.8
            elif any(needle in subject for needle in rule.weak):
                score = 0.45

            if score:
                scores[rule.genre] = max(scores.get(rule.genre, 0.0), score)
                support.setdefault(rule.genre, set()).add(subject)

    qualified = {
        genre: score
        for genre, score in scores.items()
        if score >= 0.75 or len(support.get(genre, set())) >= 2
    }

    if "contemporary romance" in qualified:
        qualified.pop("romance", None)
    if "memoir" in qualified:
        qualified.pop("biography", None)
    return qualified


def subjects_to_genres(values: object, *, max_genres: int = MAX_GENRES_PER_BOOK) -> list[str]:
    scores = genre_confidence_scores(values)
    return [
        genre
        for genre, _score in sorted(scores.items(), key=lambda item: (-item[1], item[0]))
    ][:max_genres]


def normalize_genre_list(values: object, *, max_genres: int = MAX_GENRES_PER_BOOK) -> list[str]:
    direct = filter_specific_genres(values)
    if direct:
        return direct[:max_genres]
    return subjects_to_genres(values, max_genres=max_genres)
