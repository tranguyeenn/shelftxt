"""Shared progress normalization and page estimation."""


def clamp_progress_percent(value: float | int | None) -> float:
    try:
        numeric = float(value or 0)
    except (TypeError, ValueError):
        return 0.0
    return min(100.0, max(0.0, numeric))


def clamp_pages_read(value: int | None, total_pages: int | None) -> int:
    try:
        pages = round(float(value or 0))
    except (TypeError, ValueError):
        pages = 0
    pages = max(0, pages)
    return min(pages, total_pages) if total_pages and total_pages > 0 else pages


def estimated_pages_read(progress_percent: float | int | None, total_pages: int | None) -> int | None:
    if total_pages is None or total_pages <= 0:
        return None
    estimate = round((clamp_progress_percent(progress_percent) / 100) * total_pages)
    return clamp_pages_read(estimate, total_pages)
