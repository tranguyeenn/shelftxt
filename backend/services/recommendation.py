# backend/services/recommendation.py

from functools import lru_cache

from backend.book_data import load_data
from backend.services.recommendation_builder import build_recommendations

VALID_STYLES = frozenset({"balanced", "popular", "discovery"})


def _normalize_style(style: str) -> str:
    normalized = (style or "balanced").strip().lower()
    return normalized if normalized in VALID_STYLES else "balanced"


@lru_cache(maxsize=32)
def get_recommendation(top_n: int = 10, style: str = "balanced"):
    df = load_data()
    normalized_style = _normalize_style(style)

    if df.empty:
        return []

    return build_recommendations(df, top_n=top_n, style=normalized_style)


def invalidate_recommendation_cache():
    get_recommendation.cache_clear()
