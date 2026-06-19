import logging
from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy.orm import Session

from backend.db.database import get_session_local
from backend.db.models import Book, MetadataJob
from backend.scripts.backfill_book_metadata import _apply_metadata
from backend.services import page_lookup

logger = logging.getLogger(__name__)

ACTIVE_JOB_STATUSES = ("pending", "processing")


def _has_genres(book: Book) -> bool:
    return bool(book.genres)


def _metadata_counts(db: Session, user_id: UUID) -> tuple[int, int]:
    books = db.query(Book.genres).filter(Book.user_id == user_id).all()
    total = len(books)
    with_genres = sum(1 for (genres,) in books if genres)
    return with_genres, total


def _latest_job(db: Session, user_id: UUID) -> MetadataJob | None:
    return (
        db.query(MetadataJob)
        .filter(MetadataJob.user_id == user_id)
        .order_by(MetadataJob.id.desc())
        .first()
    )


def _active_job(db: Session, user_id: UUID) -> MetadataJob | None:
    return (
        db.query(MetadataJob)
        .filter(MetadataJob.user_id == user_id)
        .filter(MetadataJob.status.in_(ACTIVE_JOB_STATUSES))
        .order_by(MetadataJob.id.desc())
        .first()
    )


def _job_to_dict(job: MetadataJob | None) -> dict:
    if job is None:
        return {
            "status": "completed",
            "processed_count": 0,
            "total_count": 0,
            "error_message": None,
        }

    return {
        "status": job.status,
        "processed_count": job.processed_count,
        "total_count": job.total_count,
        "error_message": job.error_message,
    }


def _reset_metadata_jobs_for_empty_library(db: Session, user_id: UUID) -> None:
    now = datetime.now(timezone.utc)
    active_jobs = (
        db.query(MetadataJob)
        .filter(MetadataJob.user_id == user_id)
        .filter(MetadataJob.status.in_(ACTIVE_JOB_STATUSES))
        .all()
    )
    for job in active_jobs:
        job.status = "completed"
        job.processed_count = 0
        job.total_count = 0
        job.error_message = None
        job.completed_at = now
        job.updated_at = now
    if active_jobs:
        db.commit()


def get_metadata_status(db: Session, user_id: UUID) -> dict:
    books_with_genres, total_books = _metadata_counts(db, user_id)
    if total_books == 0:
        _reset_metadata_jobs_for_empty_library(db, user_id)
        return {
            "books_with_genres": 0,
            "total_books": 0,
            "job": _job_to_dict(None),
        }

    job = _latest_job(db, user_id)
    return {
        "books_with_genres": books_with_genres,
        "total_books": total_books,
        "job": _job_to_dict(job),
    }


def create_metadata_job(db: Session, user_id: UUID) -> MetadataJob:
    _, total_books = _metadata_counts(db, user_id)
    if total_books == 0:
        _reset_metadata_jobs_for_empty_library(db, user_id)
        job = MetadataJob(
            user_id=user_id,
            status="completed",
            processed_count=0,
            total_count=0,
            completed_at=datetime.now(timezone.utc),
        )
        db.add(job)
        db.commit()
        db.refresh(job)
        return job

    active = _active_job(db, user_id)
    if active is not None:
        return active

    total_missing = sum(
        1
        for book in db.query(Book).filter(Book.user_id == user_id).all()
        if not _has_genres(book)
    )
    job = MetadataJob(
        user_id=user_id,
        status="pending" if total_missing else "completed",
        processed_count=0,
        total_count=total_missing,
        completed_at=datetime.now(timezone.utc) if total_missing == 0 else None,
    )
    db.add(job)
    db.commit()
    db.refresh(job)
    return job


def reset_metadata_progress_if_library_empty(db: Session, user_id: UUID) -> None:
    _, total_books = _metadata_counts(db, user_id)
    if total_books == 0:
        _reset_metadata_jobs_for_empty_library(db, user_id)


def process_metadata_job(job_id: int) -> None:
    session_factory = get_session_local()
    with session_factory() as db:
        job = db.get(MetadataJob, job_id)
        if job is None or job.status == "completed":
            return

        try:
            job.status = "processing"
            job.updated_at = datetime.now(timezone.utc)
            db.commit()

            books = (
                db.query(Book)
                .filter(Book.user_id == job.user_id)
                .order_by(Book.id.asc())
                .all()
            )
            books = [book for book in books if not _has_genres(book)]
            job.total_count = len(books)
            db.commit()

            for book in books:
                try:
                    metadata = page_lookup.lookup_book_metadata(book.title, book.authors, book.isbn_uid)
                    _apply_metadata(book, metadata)
                except Exception:
                    logger.exception("Metadata generation failed for book id=%s", book.id)
                finally:
                    job.processed_count += 1
                    job.updated_at = datetime.now(timezone.utc)
                    db.commit()

            job.status = "completed"
            job.completed_at = datetime.now(timezone.utc)
            job.updated_at = job.completed_at
            db.commit()
        except Exception as exc:
            db.rollback()
            job = db.get(MetadataJob, job_id)
            if job is not None:
                job.status = "failed"
                job.error_message = str(exc)[:500]
                job.completed_at = datetime.now(timezone.utc)
                job.updated_at = job.completed_at
                db.commit()
            logger.exception("Metadata job failed job_id=%s", job_id)
