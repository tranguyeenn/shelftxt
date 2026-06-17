import math
from collections.abc import Mapping
from typing import Any


RATING_COLUMN_ALIASES = (
    "Star Rating",
    "star_rating",
    "rating",
    "Rating",
    "Stars",
    "My Rating",
)


def parse_rating_value(value: Any) -> float | None:
    if value is None:
        return None

    if isinstance(value, float) and math.isnan(value):
        return None

    text = str(value).strip()
    if not text or text.lower() in {"nan", "none", "null"}:
        return None

    try:
        parsed = float(text)
    except (TypeError, ValueError):
        return None

    if math.isnan(parsed):
        return None
    return parsed


def rating_from_row(row: Mapping[str, Any]) -> float | None:
    for column in RATING_COLUMN_ALIASES:
        if column in row:
            return parse_rating_value(row[column])
    return None
