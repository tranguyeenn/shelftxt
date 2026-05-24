import httpx
import asyncio
import pandas as pd
import numpy as np
from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException, Query, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from apscheduler.schedulers.asyncio import AsyncIOScheduler

# Local modules
from backend.book_data import load_data, save_data
from backend.services.recommendation import get_recommendation


# -----------------------------
# ASYNC UTILITIES
# -----------------------------

async def self_ping():
    async with httpx.AsyncClient() as client:
        try:
            await client.get(
                "https://shelftxt.onrender.com/health",
                timeout=5.0
            )
        except Exception as e:
            print(f"Self-ping failed: {e}")


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
# APP INITIALIZATION
# -----------------------------

app = FastAPI(
    title="LibroRank API",
    lifespan=lifespan
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",
        "http://127.0.0.1:3000",
        "https://shelftxt.onrender.com"
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# -----------------------------
# HELPERS
# -----------------------------

def clean_for_json(df):
    return df.replace({np.nan: None})


def parse_date_or_today(date_str):
    try:
        return (
            pd.to_datetime(date_str)
            if date_str
            else pd.Timestamp.today().normalize()
        )
    except Exception:
        return pd.Timestamp.today().normalize()


# -----------------------------
# SCHEMAS
# -----------------------------

class AddBook(BaseModel):
    title: str
    author: str
    total_pages: int | None = None


class UpdateProgress(BaseModel):
    title: str
    pages_read: int
    total_pages: int | None = None


class FinishBook(BaseModel):
    title: str
    rating: float
    date: str | None = None


class DNFBook(BaseModel):
    title: str
    date: str | None = None


class PatchBook(BaseModel):
    title: str
    new_title: str | None = None
    author: str | None = None
    total_pages: int | None = None
    pages_read: int | None = None
    move_to: str | None = None
    rating: float | None = None
    date_read: str | None = None


class ImportRow(BaseModel):
    title: str
    author: str | None = None
    total_pages: int | None = None


class ImportBooks(BaseModel):
    books: list[ImportRow]


class RemoveBook(BaseModel):
    title: str


# -----------------------------
# CORE LOGIC
# -----------------------------

def _delete_book_by_title(title: str):

    df = load_data()

    if title not in df["Title"].values:
        raise HTTPException(
            status_code=404,
            detail="Book not found"
        )

    df = df.loc[df["Title"] != title].copy()

    save_data(df)

    return {
        "message": "Book deleted"
    }


# -----------------------------
# ROUTES
# -----------------------------

@app.api_route(
    "/health",
    methods=["GET", "HEAD"]
)
async def health():

    return {
        "status": "healthy",
        "service": "LibroRank"
    }


@app.get("/books")
async def get_books():

    df = load_data()
    df = clean_for_json(df)

    return df.to_dict(
        orient="records"
    )


@app.post("/books")
async def add_book(book: AddBook):

    df = load_data()

    new_row = {

        "Title":
            book.title,

        "Authors":
            book.author,

        "ISBN/UID":
            str(pd.Timestamp.now().timestamp()),

        "Read Status":
            "to-read",

        "Star Rating":
            np.nan,

        "Last Date Read":
            None,

        "Progress (%)":
            0,

        "Pages Read":
            0,

        "Total Pages":
            book.total_pages
    }

    df = pd.concat(
        [df, pd.DataFrame([new_row])],
        ignore_index=True
    )

    save_data(df)

    return {
        "message": "Book added"
    }


@app.delete("/books")
async def delete_book(
    title: str = Query(..., min_length=1)
):
    return _delete_book_by_title(title)


@app.post("/books/remove")
async def remove_book(
    body: RemoveBook
):

    t = body.title.strip()

    if not t:
        raise HTTPException(
            status_code=400,
            detail="title is required"
        )

    return _delete_book_by_title(t)


@app.patch("/books")
async def patch_book(
    p: PatchBook
):

    df = load_data()

    if p.title not in df["Title"].values:
        raise HTTPException(
            status_code=404,
            detail="Book not found"
        )

    if (
        p.new_title
        and p.new_title != p.title
    ):

        if p.new_title in df["Title"].values:

            raise HTTPException(
                status_code=400,
                detail="Title already exists"
            )

        df.loc[
            df["Title"] == p.title,
            "Title"
        ] = p.new_title

    key = p.new_title if p.new_title else p.title

    row = df["Title"] == key

    if p.author is not None:
        df.loc[row, "Authors"] = p.author

    if p.total_pages is not None:
        df.loc[row, "Total Pages"] = p.total_pages


    if p.move_to:

        m = p.move_to.strip().lower()

        if m == "want":

            df.loc[
                row,
                ["Read Status",
                 "Progress (%)",
                 "Pages Read"]
            ] = [
                "to-read",
                0,
                0
            ]


        elif m == "reading":

            tp = df.loc[
                row,
                "Total Pages"
            ].values[0]

            if pd.isna(tp) or tp <= 0:

                raise HTTPException(
                    status_code=400,
                    detail="Set total pages first"
                )

            pr = max(
                1,
                min(
                    int(p.pages_read or 1),
                    int(tp)
                )
            )

            df.loc[
                row,
                [
                    "Read Status",
                    "Pages Read",
                    "Progress (%)"
                ]
            ] = [
                "to-read",
                pr,
                round((pr/tp)*100,2)
            ]


        elif m == "read":

            rating = (
                p.rating
                or (
                    df.loc[row,"Star Rating"].values[0]
                    if pd.notna(
                        df.loc[row,"Star Rating"].values[0]
                    )
                    else None
                )
            )

            if (
                rating is None
                or not (1 <= rating <= 5)
            ):
                raise HTTPException(
                    status_code=400,
                    detail="Rating 1-5 required"
                )

            tp = df.loc[
                row,
                "Total Pages"
            ].values[0]

            df.loc[
                row,
                "Read Status"
            ] = "read"

            df.loc[
                row,
                "Star Rating"
            ] = rating

            df.loc[
                row,
                "Progress (%)"
            ] = 100

            if pd.notna(tp):
                df.loc[
                    row,
                    "Pages Read"
                ] = int(tp)

            df.loc[
                row,
                "Last Date Read"
            ] = parse_date_or_today(
                p.date_read
            )


        elif m == "dnf":

            df.loc[
                row,
                [
                    "Read Status",
                    "Star Rating",
                    "Progress (%)",
                    "Pages Read"
                ]
            ] = [
                "dnf",
                1,
                0,
                0
            ]

            df.loc[
                row,
                "Last Date Read"
            ] = parse_date_or_today(
                p.date_read
            )

    save_data(df)

    return {
        "message":
        "Book updated"
    }


@app.post("/books/import")
async def import_books(
    data: ImportBooks
):

    df = load_data()

    imported = 0
    skipped = 0

    for book in data.books:

        t = (
            book.title or ""
        ).strip()

        if (
            not t
            or t in df["Title"].values
        ):
            skipped += 1
            continue

        new_row = {
            "Title": t,
            "Authors": (
                book.author or "Unknown"
            ).strip(),

            "ISBN/UID":
                f"{pd.Timestamp.now().timestamp()}_{imported}",

            "Read Status":
                "to-read",

            "Star Rating":
                np.nan,

            "Last Date Read":
                None,

            "Progress (%)":
                0,

            "Pages Read":
                0,

            "Total Pages":
                book.total_pages
        }

        df = pd.concat(
            [df, pd.DataFrame([new_row])],
            ignore_index=True
        )

        imported += 1

    save_data(df)

    return {
        "imported": imported,
        "skipped": skipped
    }


# -----------------------------
# RECOMMEND ROUTE
# now delegated to service layer
# -----------------------------

@app.get("/recommend")
async def recommend():
    return get_recommendation()