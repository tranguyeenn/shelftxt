from fastapi import APIRouter, Depends, Query
from fastapi.responses import Response
from sqlalchemy.orm import Session

from backend.db.database import get_db
from backend.schemas.books import (
    AddBook,
    BookProgressPatch,
    BooksPage,
    ClearLibraryRequest,
    ImportBooks,
    PatchBook,
)
from backend.services.postgres_books import (
    add_book_service,
    clear_library_service,
    delete_book_by_id_service,
    delete_book_by_title_service,
    export_library_csv,
    get_book_by_id_service,
    get_books_service,
    import_books_service,
    patch_book_service,
    update_book_progress_by_id_service,
)

router = APIRouter()


@router.get("/books", response_model=BooksPage)
async def get_books(
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
):
    return get_books_service(db, page, limit)


@router.get("/books/export")
async def export_books(
    db: Session = Depends(get_db),
):
    csv_content = export_library_csv(db)

    return Response(
        content=csv_content,
        media_type="text/csv",
        headers={
            "Content-Disposition": 'attachment; filename="shelftxt-library.csv"',
        },
    )


@router.post("/books/clear")
async def clear_books(
    body: ClearLibraryRequest,
    db: Session = Depends(get_db),
):
    return clear_library_service(db, body.confirm)


@router.post("/books")
async def add_book(
    book: AddBook,
    db: Session = Depends(get_db),
):
    return add_book_service(db, book)


@router.delete("/books")
async def delete_book(
    title: str = Query(..., min_length=1),
    db: Session = Depends(get_db),
):
    return delete_book_by_title_service(db, title)


@router.patch("/books")
async def patch_book(
    p: PatchBook,
    db: Session = Depends(get_db),
):
    return patch_book_service(db, p)


@router.post("/books/import")
async def import_books(
    data: ImportBooks,
    db: Session = Depends(get_db),
):
    return import_books_service(db, data)


@router.get("/books/{book_id}")
async def get_book_by_id_route(
    book_id: str,
    db: Session = Depends(get_db),
):
    return get_book_by_id_service(db, book_id)


@router.patch("/books/{book_id}/progress")
async def update_book_progress(
    book_id: str,
    body: BookProgressPatch,
    db: Session = Depends(get_db),
):
    return update_book_progress_by_id_service(db, book_id, body)


@router.delete("/books/{book_id}")
async def delete_book_by_id_route(
    book_id: str,
    db: Session = Depends(get_db),
):
    return delete_book_by_id_service(db, book_id)