import math
import re
from dataclasses import dataclass

import pandas as pd

from backend.services.metadata_normalization import (
    filter_specific_genres,
    filter_specific_subjects,
    normalize_author,
    normalize_language,
    normalize_title_keywords,
    normalize_values,
)


VIETNAMESE_RE = re.compile(r"[ăâđêôơưáàảãạấầẩẫậắằẳẵặéèẻẽẹếềểễệíìỉĩịóòỏõọốồổỗộớờởỡợúùủũụứừửữựýỳỷỹỵ]", re.IGNORECASE)


def _resolve_column(df, candidates):
    for col in candidates:
        if col in df.columns:
            return col
    return None


@dataclass(frozen=True)
class Similarity:
    same_author: bool
    shared_genres: tuple[str, ...]
    shared_subjects: tuple[str, ...]
    keyword_overlap: tuple[str, ...]
    language_match: bool

    @property
    def has_meaningful_signal(self) -> bool:
        return bool(
            self.same_author
            or self.shared_genres
            or self.shared_subjects
            or self.keyword_overlap
        )


def _is_missing(value: object) -> bool:
    return value is None or (isinstance(value, float) and math.isnan(value))


def _row_value(row: pd.Series, names: list[str], default=None):
    for name in names:
        if name in row.index:
            value = row.get(name)
            if not _is_missing(value):
                return value
    return default


def row_author(row: pd.Series) -> str:
    return normalize_author(_row_value(row, ["author", "Authors"], ""))


def row_title(row: pd.Series) -> str:
    value = _row_value(row, ["title", "Title"], "")
    return "" if _is_missing(value) else str(value)


def row_subjects(row: pd.Series) -> list[str]:
    return filter_specific_subjects(_row_value(row, ["subjects", "Subjects"], []))


def row_genres(row: pd.Series) -> list[str]:
    genres = filter_specific_genres(_row_value(row, ["genres", "genre", "Genres", "Genre"], []))
    if genres:
        return genres
    return filter_specific_subjects(_row_value(row, ["subjects", "Subjects"], []))


def row_languages(row: pd.Series) -> list[str]:
    return normalize_values(_row_value(row, ["language", "Language"], []), normalize_language)


def row_keywords(row: pd.Series) -> list[str]:
    return normalize_title_keywords(row_title(row))


def infer_language(row: pd.Series) -> str | None:
    languages = row_languages(row)
    if languages:
        return languages[0]
    text = f"{row_title(row)} {_row_value(row, ['author', 'Authors'], '')}"
    if VIETNAMESE_RE.search(text):
        return "vietnamese"
    if re.search(r"[a-zA-Z]", text):
        return "english"
    return None


def similarity_between(candidate: pd.Series, read_book: pd.Series) -> Similarity:
    candidate_author = row_author(candidate)
    read_author = row_author(read_book)
    same_author = bool(
        candidate_author
        and read_author
        and candidate_author != "unknown"
        and read_author != "unknown"
        and candidate_author == read_author
    )

    shared_genres = tuple(sorted(set(row_genres(candidate)) & set(row_genres(read_book))))
    shared_subjects = tuple(sorted(set(row_subjects(candidate)) & set(row_subjects(read_book))))
    keyword_overlap = tuple(sorted(set(row_keywords(candidate)) & set(row_keywords(read_book))))
    candidate_language = infer_language(candidate)
    read_language = infer_language(read_book)

    return Similarity(
        same_author=same_author,
        shared_genres=shared_genres,
        shared_subjects=shared_subjects,
        keyword_overlap=keyword_overlap,
        language_match=bool(candidate_language and read_language and candidate_language == read_language),
    )


def meaningful_similar_books(
    candidate: pd.Series,
    read_df: pd.DataFrame,
    limit: int = 3,
) -> list[tuple[pd.Series, Similarity]]:
    if read_df.empty:
        return []

    matches: list[tuple[float, pd.Series, Similarity]] = []
    for _, read_book in read_df.iterrows():
        similarity = similarity_between(candidate, read_book)
        if not similarity.has_meaningful_signal:
            continue
        rating = float(read_book.get("rating_norm", 0.5) or 0.5)
        strength = (
            (3.0 if similarity.same_author else 0.0)
            + (1.5 * len(similarity.shared_genres))
            + (1.2 * len(similarity.shared_subjects))
            + (0.8 * len(similarity.keyword_overlap))
            + rating
        )
        matches.append((strength, read_book, similarity))

    matches.sort(key=lambda item: item[0], reverse=True)
    return [(row, similarity) for _, row, similarity in matches[:limit]]


def user_primary_language(read_df: pd.DataFrame) -> str | None:
    counts: dict[str, int] = {}
    for _, row in read_df.iterrows():
        language = infer_language(row)
        if language:
            counts[language] = counts.get(language, 0) + 1
    if not counts:
        return None
    language, count = max(counts.items(), key=lambda item: item[1])
    return language if count / max(1, sum(counts.values())) >= 0.6 else None


def read_dataframe(df: pd.DataFrame) -> pd.DataFrame:
    status_col = _resolve_column(df, ["read_status", "Read Status"])
    if status_col is None:
        return df.iloc[0:0].copy()
    return df[df[status_col].astype(str).str.strip().str.lower() == "read"].copy()
