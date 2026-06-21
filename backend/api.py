from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
from apscheduler.schedulers.asyncio import AsyncIOScheduler
import asyncio
import httpx
import logging
import time
from contextlib import suppress
from sqlalchemy.exc import OperationalError, TimeoutError as SQLAlchemyTimeoutError
from starlette.responses import JSONResponse

from backend.demo_mode import is_demo_read_only
from backend.env import load_backend_env, log_local_env_presence
from backend.routes.books import router as books_router
from backend.routes.health import router as health_router
from backend.routes.metadata import router as metadata_router
from backend.routes.profile import router as profile_router
from backend.routes.recommendation import router as recommendations_router

load_backend_env()

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
            logger.warning("self_ping_failed error=%s", e)


async def event_loop_heartbeat(interval_seconds: float = 60.0):
    expected = time.perf_counter() + interval_seconds
    while True:
        try:
            await asyncio.sleep(interval_seconds)
            now = time.perf_counter()
            lag_ms = max(0.0, (now - expected) * 1000)
            logger.info("process_heartbeat alive=true event_loop_lag_ms=%.2f", lag_ms)
            expected = now + interval_seconds
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("process_heartbeat_failed")
            expected = time.perf_counter() + interval_seconds


@asynccontextmanager
async def lifespan(app: FastAPI):
    log_local_env_presence()

    scheduler = AsyncIOScheduler()
    heartbeat_task = asyncio.create_task(event_loop_heartbeat())

    scheduler.add_job(
        self_ping,
        "interval",
        minutes=14
    )

    scheduler.start()

    yield

    heartbeat_task.cancel()
    with suppress(asyncio.CancelledError):
        await heartbeat_task
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
        "db_pool_timeout method=%s path=%s",
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
    logger.info(
        "request_start method=%s path=%s",
        request.method,
        request.url.path,
    )
    try:
        response = await call_next(request)
    except Exception:
        duration_ms = round((time.perf_counter() - started) * 1000, 2)
        logger.exception(
            "request_exception method=%s path=%s duration_ms=%.2f",
            request.method,
            request.url.path,
            duration_ms,
        )
        raise

    duration_ms = round((time.perf_counter() - started) * 1000, 2)
    logger.info(
        "request_end method=%s path=%s status_code=%s duration_ms=%.2f",
        request.method,
        request.url.path,
        response.status_code,
        duration_ms,
    )
    if duration_ms >= 2000:
        logger.warning(
            "slow_request method=%s path=%s status_code=%s duration_ms=%.2f",
            request.method,
            request.url.path,
            response.status_code,
            duration_ms,
        )
    return response


# -----------------------------
# ROUTERS
# -----------------------------

app.include_router(health_router)

app.include_router(books_router)

app.include_router(metadata_router)

app.include_router(profile_router)

app.include_router(recommendations_router)
