import numpy as np
import pandas as pd
from fastapi import APIRouter, HTTPException, Query

from backend.book_data import load_data
from backend.schemas.books import AddBook, PatchBook, ImportBooks, RemoveBook
from backend.services.books import (
    add_book_service,
    delete_book_by_title,
    patch_book_service,
    import_books_service,
)

router = APIRouter()


def clean_for_json(df):
    return df.replace({np.nan: None})


@router.get("/books")
async def get_books():
    df = load_data()
    df = clean_for_json(df)
    return df.to_dict(orient="records")


@router.post("/books")
async def add_book(book: AddBook):
    return add_book_service(book)


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
    return patch_book_service(p)


@router.post("/books/import")
async def import_books(data: ImportBooks):
    return import_books_service(data)