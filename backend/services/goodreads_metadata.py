import ast
import csv
import logging
import os
import re
import threading
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path

from backend.services.metadata_normalization import (
    GENERIC_TITLE_WORDS,
    MAX_GENRES_PER_BOOK,
    TITLE_STOPWORDS,
    clean_reader_tags,
    normalize_text,
)

logger = logging.getLogger(__name__)

_HTML_TAG_RE = re.compile(r"<[^>]+>")
_PROJECT_ROOT = Path(__file__).resolve().parents[2]
_DEFAULT_CSV_PATH = _PROJECT_ROOT / "metadata" / "book_details.csv"
_MIN_BASE_TITLE_LENGTH = 4
_MIN_SINGLE_WORD_BASE_LENGTH = 5

_load_lock = threading.Lock()
_loaded_path: Path | None = None
_index: "_GoodreadsIndex | None" = None


@dataclass(frozen=True)
class GoodreadsMetadata:
    description: str | None = None
    genres: list[str] | None = None


@dataclass(frozen=True)
class _GoodreadsRow:
    description: str | None
    genres: list[str]


@dataclass(frozen=True)
class _GoodreadsIndex:
    exact: dict[str, _GoodreadsRow]
    base: dict[str, _GoodreadsRow]


def normalize_title_key(title: str) -> str:
    """Normalize title for exact matching: case, punctuation, whitespace."""
    return normalize_text(title)


def colon_base_title(title: str) -> str | None:
    if ":" not in title:
        return None
    left, _, right = title.partition(":")
    left = left.strip()
    right = right.strip()
    if not left or not right:
        return None
    return left


def is_strong_base_title(title: str) -> bool:
    normalized = normalize_title_key(title)
    if len(normalized) < _MIN_BASE_TITLE_LENGTH:
        return False
    words = normalized.split()
    non_stop = [
        word
        for word in words
        if word not in TITLE_STOPWORDS and word not in GENERIC_TITLE_WORDS
    ]
    if not non_stop:
        return False
    if len(words) == 1 and len(normalized) < _MIN_SINGLE_WORD_BASE_LENGTH:
        return False
    return True


def _csv_path() -> Path:
    configured = os.getenv("GOODREADS_METADATA_CSV", "").strip()
    if not configured:
        return _DEFAULT_CSV_PATH
    path = Path(configured)
    if not path.is_absolute():
        path = _PROJECT_ROOT / path
    return path


def reset_goodreads_cache() -> None:
    global _loaded_path, _index
    with _load_lock:
        _loaded_path = None
        _index = None


def clean_description(value: str | None) -> str | None:
    if not value:
        return None
    text = _HTML_TAG_RE.sub(" ", value)
    text = re.sub(r"\s+", " ", text).strip()
    return text or None


def _parse_genres(raw: str | None) -> list[str]:
    if not raw or not raw.strip():
        return []
    try:
        parsed = ast.literal_eval(raw.strip())
    except (ValueError, SyntaxError):
        return []
    if not isinstance(parsed, list):
        return []
    return clean_reader_tags(parsed, max_tags=MAX_GENRES_PER_BOOK)


def _build_index(rows: list[tuple[str, _GoodreadsRow]]) -> _GoodreadsIndex:
    exact: dict[str, _GoodreadsRow] = {}
    base_to_rows: dict[str, dict[str, _GoodreadsRow]] = defaultdict(dict)

    for title, row in rows:
        full_key = normalize_title_key(title)
        exact[full_key] = row

        base = colon_base_title(title)
        if not base or not is_strong_base_title(base):
            continue
        base_key = normalize_title_key(base)
        if base_key == full_key:
            continue
        base_to_rows[base_key][full_key] = row

    base: dict[str, _GoodreadsRow] = {}
    for base_key, full_map in base_to_rows.items():
        if len(full_map) != 1:
            continue
        _full_key, row = next(iter(full_map.items()))
        if base_key in exact and exact[base_key] is not row:
            continue
        base[base_key] = row

    return _GoodreadsIndex(exact=exact, base=base)


def _load_index() -> _GoodreadsIndex:
    global _loaded_path, _index

    path = _csv_path()
    if _index is not None and _loaded_path == path:
        return _index

    with _load_lock:
        if _index is not None and _loaded_path == path:
            return _index

        rows: list[tuple[str, _GoodreadsRow]] = []
        if not path.is_file():
            logger.info("Goodreads metadata CSV not found at %s; fallback disabled", path)
            _loaded_path = path
            _index = _GoodreadsIndex(exact={}, base={})
            return _index

        try:
            with path.open(newline="", encoding="utf-8") as handle:
                reader = csv.DictReader(handle)
                for row in reader:
                    if not isinstance(row, dict):
                        continue
                    title = (row.get("title") or "").strip()
                    if not title:
                        continue
                    description = clean_description(row.get("description"))
                    genres = _parse_genres(row.get("genres"))
                    if not description and not genres:
                        continue
                    if not normalize_title_key(title):
                        continue
                    rows.append(
                        (
                            title,
                            _GoodreadsRow(description=description, genres=genres or None),
                        )
                    )
        except OSError as exc:
            logger.warning("Failed to read Goodreads metadata CSV at %s: %s", path, exc)
            rows = []

        index = _build_index(rows)
        logger.info(
            "Loaded Goodreads metadata index exact_rows=%s base_rows=%s path=%s",
            len(index.exact),
            len(index.base),
            path,
        )
        _loaded_path = path
        _index = index
        return index


def _find_row(clean_title: str) -> tuple[_GoodreadsRow, str, str] | None:
    index = _load_index()
    full_key = normalize_title_key(clean_title)
    if not full_key:
        return None

    if full_key in index.exact:
        return index.exact[full_key], "exact", "high"

    query_base = colon_base_title(clean_title)
    if query_base and is_strong_base_title(query_base):
        base_key = normalize_title_key(query_base)
        if base_key != full_key:
            if base_key in index.exact:
                return index.exact[base_key], "colon_trim_query", "high"
            if base_key in index.base:
                return index.base[base_key], "colon_trim_query", "medium"

    if is_strong_base_title(clean_title) and full_key in index.base:
        return index.base[full_key], "colon_trim_dataset", "medium"

    return None


def lookup_goodreads_metadata(
    title: str | None,
    author: str | None = None,
) -> GoodreadsMetadata | None:
    clean_title = (title or "").strip()
    if not clean_title:
        return None

    match = _find_row(clean_title)
    if match is None:
        return None

    row, match_type, confidence = match
    logger.info(
        "goodreads_metadata_match confidence=%s match_type=%s title=%r author=%r",
        confidence,
        match_type,
        clean_title,
        author,
    )
    return GoodreadsMetadata(description=row.description, genres=row.genres)
