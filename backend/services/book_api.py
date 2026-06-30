import numpy as np
import pandas as pd


def find_row_by_book_id(df: pd.DataFrame, book_id: str):
    book_id = str(book_id).strip()
    if not book_id or "ISBN/UID" not in df.columns:
        return None

    matches = df["ISBN/UID"].astype(str).str.strip() == book_id
    if not matches.any():
        return None
    return matches


def reading_status_from_values(read_status: str, progress_pct: float, pages_read: int) -> str:
    status = str(read_status).strip().lower()
    if status == "read":
        return "completed"
    if status == "to-read" and (progress_pct > 0 or pages_read > 0):
        return "reading"
    return "not_started"


def series_to_api_book(row: pd.Series) -> dict:
    def _int_or_none(value):
        if value is None or (isinstance(value, float) and np.isnan(value)):
            return None
        try:
            return int(value)
        except (TypeError, ValueError):
            return None

    def _float_or_none(value):
        if value is None or (isinstance(value, float) and np.isnan(value)):
            return None
        try:
            return float(value)
        except (TypeError, ValueError):
            return None

    title = str(row.get("Title", "")).strip()
    author = str(row.get("Authors", "")).strip() or "Unknown author"
    book_id = str(row.get("ISBN/UID", "")).strip()
    total_pages = _int_or_none(row.get("Total Pages"))
    pages_read = _int_or_none(row.get("Pages Read")) or 0
    progress = _float_or_none(row.get("Progress (%)")) or 0.0
    read_status = str(row.get("Read Status", "to-read"))
    tracking_mode = str(row.get("tracking_mode", row.get("Tracking Mode", ""))).strip().lower()
    if tracking_mode not in {"percentage", "pages"}:
        tracking_mode = "pages" if total_pages is not None else "percentage"

    return {
        "id": book_id,
        "title": title,
        "author": author,
        "status": reading_status_from_values(read_status, progress, pages_read),
        "total_pages": total_pages,
        "pages_read": pages_read,
        "progress_pct": round(min(100.0, max(0.0, progress)), 2),
        "tracking_mode": tracking_mode,
        "rating": _float_or_none(row.get("Star Rating")),
        "read_status": read_status,
        "description": None
        if pd.isna(row.get("Description"))
        else str(row.get("Description") or "").strip() or None,
        "cover_url": None
        if pd.isna(row.get("Cover URL"))
        else str(row.get("Cover URL") or "").strip() or None,
    }


def row_to_api_book(df: pd.DataFrame, row_mask) -> dict:
    return series_to_api_book(df.loc[row_mask].iloc[0])
