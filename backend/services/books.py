import numpy as np
import pandas as pd
from fastapi import HTTPException

from backend.book_data import BOOKS_COLUMNS
from backend.repository.books_repository import get_all_books, save_books
from backend.schemas.books import AddBook, PatchBook, ImportBooks, BookProgressPatch
from backend.services.book_api import find_row_by_book_id, series_to_api_book
from backend.services.recommendation import invalidate_recommendation_cache


def parse_date_or_today(date_str):
    try:
        return (
            pd.to_datetime(date_str)
            if date_str
            else pd.Timestamp.today().normalize()
        )
    except (ValueError, TypeError, pd.errors.ParserError):
        return pd.Timestamp.today().normalize()


def add_book_service(book: AddBook):
    df = get_all_books()

    new_row = {
        "Title": book.title,
        "Authors": book.author,
        "ISBN/UID": str(pd.Timestamp.now().timestamp()),
        "Read Status": "to-read",
        "Star Rating": np.nan,
        "Last Date Read": None,
        "Progress (%)": 0,
        "Pages Read": 0,
        "Total Pages": book.total_pages,
    }

    df = pd.concat([df, pd.DataFrame([new_row])], ignore_index=True)
    save_books(df)
    invalidate_recommendation_cache()

    return {"message": "Book added"}


def export_library_csv() -> str:
    df = get_all_books()
    return df.to_csv(index=False)


def clear_library_service(confirm: bool):
    if not confirm:
        raise HTTPException(
            status_code=400,
            detail="Confirmation required to clear the library",
        )

    df = get_all_books()
    deleted = len(df)
    empty = pd.DataFrame(columns=BOOKS_COLUMNS)
    save_books(empty)
    invalidate_recommendation_cache()

    return {"message": "Library cleared", "deleted": deleted}


def delete_book_by_id(book_id: str):
    df = get_all_books()
    row = find_row_by_book_id(df, book_id)

    if row is None:
        raise HTTPException(status_code=404, detail="Book not found")

    df = df.loc[~row].copy()
    save_books(df)
    invalidate_recommendation_cache()

    return {"message": "Book deleted"}


def delete_book_by_title(title: str):
    df = get_all_books()

    if title not in df["Title"].values:
        raise HTTPException(status_code=404, detail="Book not found")

    df = df.loc[df["Title"] != title].copy()
    save_books(df)
    invalidate_recommendation_cache()

    return {"message": "Book deleted"}


def patch_book_service(p: PatchBook):
    df = get_all_books()

    if p.title not in df["Title"].values:
        raise HTTPException(status_code=404, detail="Book not found")

    if p.new_title and p.new_title != p.title:
        if p.new_title in df["Title"].values:
            raise HTTPException(status_code=400, detail="Title already exists")

        df.loc[df["Title"] == p.title, "Title"] = p.new_title

    key = p.new_title if p.new_title else p.title
    row = df["Title"] == key

    if p.author is not None:
        df.loc[row, "Authors"] = p.author

    if p.total_pages is not None:
        df.loc[row, "Total Pages"] = p.total_pages

    if p.move_to:
        move_to = p.move_to.strip().lower()

        if move_to == "want":
            df.loc[row, ["Read Status", "Progress (%)", "Pages Read"]] = [
                "to-read",
                0,
                0,
            ]

        elif move_to == "reading":
            total_pages = df.loc[row, "Total Pages"].values[0]

            if pd.isna(total_pages) or total_pages <= 0:
                raise HTTPException(
                    status_code=400,
                    detail="Set total pages first",
                )

            pages_read = max(
                1,
                min(int(p.pages_read or 1), int(total_pages)),
            )

            df.loc[row, ["Read Status", "Pages Read", "Progress (%)"]] = [
                "to-read",
                pages_read,
                round((pages_read / total_pages) * 100, 2),
            ]

        elif move_to == "read":
            existing_rating = df.loc[row, "Star Rating"].values[0]

            rating = (
                p.rating
                or (
                    existing_rating
                    if pd.notna(existing_rating)
                    else None
                )
            )

            if rating is None or not (1 <= rating <= 5):
                raise HTTPException(
                    status_code=400,
                    detail="Rating 1-5 required",
                )

            total_pages = df.loc[row, "Total Pages"].values[0]

            df.loc[row, "Read Status"] = "read"
            df.loc[row, "Star Rating"] = rating
            df.loc[row, "Progress (%)"] = 100

            if pd.notna(total_pages):
                df.loc[row, "Pages Read"] = int(total_pages)

            df.loc[row, "Last Date Read"] = parse_date_or_today(p.date_read)

        elif move_to == "dnf":
            df.loc[
                row,
                ["Read Status", "Star Rating", "Progress (%)", "Pages Read"],
            ] = [
                "dnf",
                1,
                0,
                0,
            ]

            df.loc[row, "Last Date Read"] = parse_date_or_today(p.date_read)

    save_books(df)
    invalidate_recommendation_cache()

    return {"message": "Book updated"}


def update_book_progress_by_id(book_id: str, body: BookProgressPatch):
    df = get_all_books()
    row = find_row_by_book_id(df, book_id)

    if row is None:
        raise HTTPException(status_code=404, detail="Book not found")

    total_raw = df.loc[row, "Total Pages"].values[0]
    has_total = pd.notna(total_raw) and int(total_raw) > 0
    total_pages = int(total_raw) if has_total else None

    status = body.status
    pages_read = int(body.pages_read)

    if status in ("reading", "completed") and not has_total:
        raise HTTPException(status_code=400, detail="Set total pages first")

    if has_total:
        if pages_read > total_pages:
            raise HTTPException(
                status_code=400,
                detail="pages_read cannot exceed total_pages",
            )
        if status == "completed" and pages_read != total_pages:
            raise HTTPException(
                status_code=400,
                detail="pages_read must equal total_pages when status is completed",
            )
        if pages_read == total_pages and status == "reading":
            status = "completed"

    if status == "not_started":
        df.loc[row, ["Read Status", "Progress (%)", "Pages Read"]] = [
            "to-read",
            0,
            0,
        ]

    elif status == "reading":
        if has_total and pages_read == total_pages:
            status = "completed"
        else:
            progress_pct = (
                round((pages_read / total_pages) * 100, 2) if has_total and total_pages else 0
            )
            df.loc[row, ["Read Status", "Pages Read", "Progress (%)"]] = [
                "to-read",
                pages_read,
                progress_pct,
            ]

    if status == "completed":
        if not has_total:
            raise HTTPException(status_code=400, detail="Set total pages first")
        pages_read = total_pages
        existing_rating = df.loc[row, "Star Rating"].values[0]
        rating = existing_rating if pd.notna(existing_rating) else 3.0
        df.loc[row, "Read Status"] = "read"
        df.loc[row, "Star Rating"] = float(rating)
        df.loc[row, "Progress (%)"] = 100
        df.loc[row, "Pages Read"] = pages_read
        df.loc[row, "Last Date Read"] = parse_date_or_today(None)

    save_books(df)
    invalidate_recommendation_cache()

    updated = series_to_api_book(df.loc[row].iloc[0])
    return {"book": updated}


def import_books_service(data: ImportBooks):
    df = get_all_books()

    imported = 0
    skipped = 0

    for book in data.books:
        title = (book.title or "").strip()

        if not title or title in df["Title"].values:
            skipped += 1
            continue

        new_row = {
            "Title": title,
            "Authors": (book.author or "Unknown").strip(),
            "ISBN/UID": f"{pd.Timestamp.now().timestamp()}_{imported}",
            "Read Status": "to-read",
            "Star Rating": np.nan,
            "Last Date Read": None,
            "Progress (%)": 0,
            "Pages Read": 0,
            "Total Pages": book.total_pages,
        }

        df = pd.concat([df, pd.DataFrame([new_row])], ignore_index=True)
        imported += 1

    if imported > 0:
        save_books(df)
        invalidate_recommendation_cache()

    return {
        "imported": imported,
        "skipped": skipped,
    }