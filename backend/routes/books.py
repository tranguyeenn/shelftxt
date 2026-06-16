from fastapi import APIRouter, BackgroundTasks, Depends, Query
from fastapi.responses import Response
from sqlalchemy.orm import Session

from backend.auth.dependencies import get_current_user
from backend.db.database import get_db
from backend.db.models import Profile
from backend.schemas.books import (
    AddBook,
    BookProgressPatch,
    BooksPage,
    ClearLibraryRequest,
    ImportBooks,
    ImportResult,
    PatchBook,
    PatchBookById,
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
    patch_book_by_id_service,
    update_book_progress_by_id_service,
)
from backend.services.page_count_lookup import backfill_missing_page_counts

router = APIRouter()


@router.get("/books", response_model=BooksPage)
async def get_books(
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
    current_user: Profile = Depends(get_current_user),
):
    return get_books_service(db, current_user.id, page, limit)


@router.get("/books/export")
async def export_books(
    db: Session = Depends(get_db),
    current_user: Profile = Depends(get_current_user),
):
    csv_content = export_library_csv(db, current_user.id)

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
    current_user: Profile = Depends(get_current_user),
):
    return clear_library_service(db, body.confirm, current_user.id)


@router.post("/books")
async def add_book(
    book: AddBook,
    db: Session = Depends(get_db),
    current_user: Profile = Depends(get_current_user),
):
    return add_book_service(db, book, current_user.id)


@router.delete("/books")
async def delete_book(
    title: str = Query(..., min_length=1),
    db: Session = Depends(get_db),
    current_user: Profile = Depends(get_current_user),
):
    return delete_book_by_title_service(db, title, current_user.id)


@router.patch("/books")
async def patch_book(
    p: PatchBook,
    db: Session = Depends(get_db),
    current_user: Profile = Depends(get_current_user),
):
    return patch_book_service(db, p, current_user.id)


@router.post("/books/import", response_model=ImportResult)
async def import_books(
    data: ImportBooks,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    current_user: Profile = Depends(get_current_user),
):
    result = import_books_service(db, data, current_user.id)
    background_tasks.add_task(backfill_missing_page_counts)
    return result


@router.get("/books/{book_id}")
async def get_book_by_id_route(
    book_id: str,
    db: Session = Depends(get_db),
    current_user: Profile = Depends(get_current_user),
):
    return get_book_by_id_service(db, book_id, current_user.id)


@router.patch("/books/{book_id}")
async def patch_book_by_id_route(
    book_id: str,
    body: PatchBookById,
    db: Session = Depends(get_db),
    current_user: Profile = Depends(get_current_user),
):
    return patch_book_by_id_service(db, book_id, body, current_user.id)


@router.patch("/books/{book_id}/progress")
async def update_book_progress(
    book_id: str,
    body: BookProgressPatch,
    db: Session = Depends(get_db),
    current_user: Profile = Depends(get_current_user),
):
    return update_book_progress_by_id_service(db, book_id, body, current_user.id)


@router.delete("/books/{book_id}")
async def delete_book_by_id_route(
    book_id: str,
    db: Session = Depends(get_db),
    current_user: Profile = Depends(get_current_user),
):
    return delete_book_by_id_service(db, book_id, current_user.id)
