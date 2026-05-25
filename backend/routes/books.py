import numpy as np
import pandas as pd
from fastapi import APIRouter, HTTPException, Query

from backend.book_data import load_data, save_data
from backend.schemas.books import AddBook, PatchBook, ImportBooks, RemoveBook
from backend.services.books import delete_book_by_title, parse_date_or_today

router = APIRouter()


def clean_for_json(df):
    return df.replace({np.nan: None})


@router.get("/books")
async def get_books(
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1)
):
    df = load_data()
    df = clean_for_json(df)

    total = len(df)
    start = (page - 1) * limit
    results = df.iloc[start:start + limit].to_dict(orient="records")

    return {
        "page": page,
        "limit": limit,
        "total": total,
        "results": results
    }


@router.post("/books")
async def add_book(book: AddBook):
    df = load_data()

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
    save_data(df)

    return {"message": "Book added"}


@router.delete("/books")
async def delete_book(title: str = Query(..., min_length=1)):
    return delete_book_by_title(title)


@router.post("/books/remove")
async def remove_book(body: RemoveBook):
    title = body.title.strip()

    if not title:
        raise HTTPException(status_code=400, detail="title is required")

    return delete_book_by_title(title)


@router.patch("/books")
async def patch_book(p: PatchBook):
    df = load_data()

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

    save_data(df)

    return {"message": "Book updated"}


@router.post("/books/import")
async def import_books(data: ImportBooks):
    df = load_data()

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

    save_data(df)

    return {
        "imported": imported,
        "skipped": skipped,
    }