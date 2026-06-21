import logging
import os
import time
from datetime import datetime, timedelta, timezone
from uuid import UUID

from sqlalchemy.orm import Session

from backend.db.database import get_session_local
from backend.db.models import Book, MetadataJob
from backend.scripts.backfill_book_metadata import _apply_metadata
from backend.services import page_lookup

logger = logging.getLogger(__name__)

ACTIVE_JOB_STATUSES = ("pending", "processing")
DEFAULT_STALE_JOB_MINUTES = 30


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _stale_job_cutoff() -> datetime:
    minutes = int(os.getenv("METADATA_JOB_STALE_MINUTES", str(DEFAULT_STALE_JOB_MINUTES)))
    return _utcnow() - timedelta(minutes=minutes)


def _as_aware(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value


def _mark_stale_processing_jobs(db: Session, user_id: UUID) -> int:
    cutoff = _stale_job_cutoff()
    jobs = (
        db.query(MetadataJob)
        .filter(MetadataJob.user_id == user_id)
        .filter(MetadataJob.status == "processing")
        .all()
    )
    stale_count = 0
    now = _utcnow()
    for job in jobs:
        updated_at = _as_aware(job.updated_at)
        if updated_at is not None and updated_at > cutoff:
            continue
        job.status = "failed"
        job.error_message = "Metadata job marked failed after stale processing timeout."
        job.completed_at = now
        job.updated_at = now
        stale_count += 1
    if stale_count:
        db.commit()
        logger.warning(
            "metadata_job_stale_marked user_id=%s stale_count=%s cutoff=%s",
            user_id,
            stale_count,
            cutoff.isoformat(),
        )
    return stale_count


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
    now = _utcnow()
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
    _mark_stale_processing_jobs(db, user_id)
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
    _mark_stale_processing_jobs(db, user_id)
    _, total_books = _metadata_counts(db, user_id)
    if total_books == 0:
        _reset_metadata_jobs_for_empty_library(db, user_id)
        job = MetadataJob(
            user_id=user_id,
            status="completed",
            processed_count=0,
            total_count=0,
            completed_at=_utcnow(),
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
        completed_at=_utcnow() if total_missing == 0 else None,
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
    started = time.perf_counter()
    session_factory = get_session_local()
    with session_factory() as db:
        job = db.get(MetadataJob, job_id)
        if job is None or job.status == "completed":
            return
        user_id = job.user_id

        try:
            job.status = "processing"
            job.updated_at = _utcnow()
            db.commit()

            book_rows = (
                db.query(Book)
                .filter(Book.user_id == job.user_id)
                .order_by(Book.id.asc())
                .all()
            )
            books_to_process = [
                (book.id, book.title, book.authors, book.isbn_uid)
                for book in book_rows
                if not _has_genres(book)
            ]
            job.total_count = len(books_to_process)
            db.commit()
            logger.info(
                "metadata_job_start job_id=%s user_id=%s total_count=%s",
                job_id,
                user_id,
                len(books_to_process),
            )
        except Exception as exc:
            db.rollback()
            job = db.get(MetadataJob, job_id)
            if job is not None:
                job.status = "failed"
                job.error_message = str(exc)[:500]
                job.completed_at = _utcnow()
                job.updated_at = job.completed_at
                db.commit()
            logger.exception("metadata_job_failed job_id=%s", job_id)
            return

    for book_id, title, authors, isbn_uid in books_to_process:
        metadata = None
        lookup_error: Exception | None = None
        try:
            metadata = page_lookup.lookup_book_metadata(title, authors, isbn_uid)
        except Exception as exc:
            lookup_error = exc
            logger.exception("metadata_job_book_lookup_failed job_id=%s book_id=%s", job_id, book_id)

        with session_factory() as db:
            try:
                book = db.get(Book, book_id)
                job = db.get(MetadataJob, job_id)
                if job is None:
                    logger.warning("metadata_job_missing job_id=%s book_id=%s", job_id, book_id)
                    return
                if book is not None and lookup_error is None:
                    _apply_metadata(book, metadata)
                job.processed_count += 1
                job.updated_at = _utcnow()
                db.commit()
            except Exception:
                db.rollback()
                logger.exception("metadata_job_book_commit_failed job_id=%s book_id=%s", job_id, book_id)

    with session_factory() as db:
        job = db.get(MetadataJob, job_id)
        if job is None:
            return
        job.status = "completed"
        job.completed_at = _utcnow()
        job.updated_at = job.completed_at
        db.commit()
        logger.info(
            "metadata_job_end job_id=%s user_id=%s status=%s processed_count=%s total_count=%s duration_ms=%.2f",
            job_id,
            user_id,
            job.status,
            job.processed_count,
            job.total_count,
            (time.perf_counter() - started) * 1000,
        )
