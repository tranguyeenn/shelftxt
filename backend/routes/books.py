import numpy as np
from fastapi import APIRouter, Query
from fastapi.responses import Response

from backend.book_data import load_data
from backend.schemas.books import (
    AddBook,
    PatchBook,
    ImportBooks,
    BookProgressPatch,
    ClearLibraryRequest,
)
from backend.services.books import (
    add_book_service,
    clear_library_service,
    delete_book_by_id,
    delete_book_by_title,
    export_library_csv,
    patch_book_service,
    import_books_service,
    update_book_progress_by_id,
)

router = APIRouter()


def clean_for_json(df):
    return df.replace({np.nan: None})


@router.get("/books")
async def get_books():
    df = load_data()
    df = clean_for_json(df)
    return df.to_dict(orient="records")


@router.get("/books/export")
async def export_books():
    csv_content = export_library_csv()
    return Response(
        content=csv_content,
        media_type="text/csv",
        headers={
            "Content-Disposition": 'attachment; filename="shelftxt-library.csv"',
        },
    )


@router.post("/books/clear")
async def clear_books(body: ClearLibraryRequest):
    return clear_library_service(body.confirm)


@router.post("/books")
async def add_book(book: AddBook):
    return add_book_service(book)


@router.delete("/books")
async def delete_book(title: str = Query(..., min_length=1)):
    return delete_book_by_title(title)


@router.patch("/books")
async def patch_book(p: PatchBook):
    return patch_book_service(p)


@router.post("/books/import")
async def import_books(data: ImportBooks):
    return import_books_service(data)


@router.patch("/books/{book_id}/progress")
async def update_book_progress(book_id: str, body: BookProgressPatch):
    return update_book_progress_by_id(book_id, body)


@router.delete("/books/{book_id}")
async def delete_book_by_id_route(book_id: str):
    return delete_book_by_id(book_id)
