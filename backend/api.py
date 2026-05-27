from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
from apscheduler.schedulers.asyncio import AsyncIOScheduler
import httpx

from backend.routes.books import router as books_router
from backend.routes.health import router as health_router
from backend.routes.recommendation import router as recommendations_router


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


# -----------------------------
# ROUTERS
# -----------------------------

app.include_router(health_router)

app.include_router(books_router)

app.include_router(recommendations_router)