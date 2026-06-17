from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
from apscheduler.schedulers.asyncio import AsyncIOScheduler
import httpx
import logging
import time
from sqlalchemy.exc import OperationalError, TimeoutError as SQLAlchemyTimeoutError
from starlette.responses import JSONResponse

from backend.demo_mode import is_demo_read_only
from backend.routes.books import router as books_router
from backend.routes.health import router as health_router
from backend.routes.recommendation import router as recommendations_router
from backend.services.page_count_lookup import backfill_missing_page_counts

logger = logging.getLogger(__name__)


# -----------------------------
# SELF PING (optional)
# keep Render awake
# -----------------------------

async def self_ping():
    async with httpx.AsyncClient() as client:
        try:
            await client.get(
                "https://shelftxt.onrender.com/health",
                timeout=5.0
            )
        except httpx.RequestError as e:
            print(f"Self ping failed: {e}")


@asynccontextmanager
async def lifespan(app: FastAPI):

    scheduler = AsyncIOScheduler()

    scheduler.add_job(
        self_ping,
        "interval",
        minutes=14
    )

    scheduler.add_job(backfill_missing_page_counts, "date")

    scheduler.start()

    yield

    scheduler.shutdown()


# -----------------------------
# APP
# -----------------------------

app = FastAPI(
    title="ShelfTxt API",
    lifespan=lifespan
)


@app.exception_handler(SQLAlchemyTimeoutError)
async def sqlalchemy_timeout_handler(request, exc):
    logger.exception(
        "Database connection timed out during %s %s",
        request.method,
        request.url.path,
    )
    return JSONResponse(
        status_code=503,
        content={"detail": "Database unavailable. Please try again shortly."},
    )


@app.exception_handler(OperationalError)
async def sqlalchemy_operational_error_handler(request, exc):
    logger.exception(
        "Database operational error during %s %s",
        request.method,
        request.url.path,
    )
    return JSONResponse(
        status_code=503,
        content={"detail": "Database unavailable. Please try again shortly."},
    )


# -----------------------------
# CORS
# -----------------------------

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",
        "http://127.0.0.1:3000",
        "https://shelftxt.vercel.app",
        "https://shelftxt.onrender.com",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def demo_read_only_guard(request, call_next):
    if is_demo_read_only() and request.method in {"POST", "PUT", "PATCH", "DELETE"}:
        return JSONResponse(
            status_code=403,
            content={"detail": "This API is in read-only demo mode."},
        )
    return await call_next(request)


@app.middleware("http")
async def endpoint_timing_logger(request, call_next):
    started = time.perf_counter()
    if request.url.path == "/books" and request.method == "GET":
        logger.info("GET /books request start")
    response = await call_next(request)
    duration_ms = round((time.perf_counter() - started) * 1000, 2)
    if duration_ms >= 250:
        logger.info(
            "Slow endpoint %s %s completed in %.2fms",
            request.method,
            request.url.path,
            duration_ms,
        )
    return response


# -----------------------------
# ROUTERS
# -----------------------------

app.include_router(health_router)

app.include_router(books_router)

app.include_router(recommendations_router)
