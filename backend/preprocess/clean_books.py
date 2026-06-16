import pandas as pd
import random


def clean_books(df):
    """
    Clean canonical ShelfTxt columns while gracefully handling missing fields.
    """
    df = df.copy()

    for col, fallback in (
        ("title", ""),
        ("author", "unknown"),
        ("genre", "unknown"),
        ("read_status", "to-read"),
        ("book_id", None),
        ("rating", None),
        ("last_date_read", None),
        ("start_date", None),
        ("end_date", None),
    ):
        if col not in df.columns:
            df[col] = fallback

    df["read_status"] = df["read_status"].astype(str).str.strip().str.lower()
    df["rating"] = pd.to_numeric(df["rating"], errors="coerce")

    mean_rating = df["rating"].dropna().mean()
    if pd.notna(mean_rating):
        df["rating"] = df["rating"].fillna(mean_rating)
    else:
        # If no ratings exist yet, keep a neutral default.
        df["rating"] = df["rating"].fillna(3.0)

    missing_mask = df["book_id"].isna() | (df["book_id"].astype(str).str.strip() == "")
    df.loc[missing_mask, "book_id"] = [
        str(random.randint(10**12, 10**13 - 1))
        for _ in range(missing_mask.sum())
    ]

    df["last_date_read"] = pd.to_datetime(df["last_date_read"], errors="coerce")
    df["start_date"] = pd.to_datetime(df["start_date"], errors="coerce")
    df["end_date"] = pd.to_datetime(df["end_date"], errors="coerce")
    today = pd.Timestamp.today().normalize()
    df["last_date_read"] = df["last_date_read"].fillna(today)

    return df
