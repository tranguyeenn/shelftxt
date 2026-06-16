import pandas as pd

def _resolve_column(df, candidates):
    for col in candidates:
        if col in df.columns:
            return col
    return None


def _min_max(series, reverse=False, neutral_value=1.0):
    min_value = series.min()
    max_value = series.max()
    if pd.isna(min_value) or pd.isna(max_value) or max_value == min_value:
        return pd.Series([neutral_value] * len(series), index=series.index)

    normalized = (series - min_value) / (max_value - min_value)
    if reverse:
        normalized = 1 - normalized
    return normalized


def normalize_rating(df):
    rating_col = _resolve_column(df, ["rating", "Star Rating"])
    if rating_col is None:
        df["rating_norm"] = 0.5
        return df

    ratings = pd.to_numeric(df[rating_col], errors="coerce").fillna(pd.to_numeric(df[rating_col], errors="coerce").mean())
    if ratings.isna().all():
        df["rating_norm"] = 0.5
    else:
        ratings = ratings.fillna(3.0)
        df["rating_norm"] = _min_max(ratings)

    return df


def compute_recency(df):
    today = pd.Timestamp.today().normalize()
    status_col = _resolve_column(df, ["read_status", "Read Status"])
    end_col = _resolve_column(df, ["end_date", "End Date"])
    start_col = _resolve_column(df, ["start_date", "Start Date"])
    legacy_col = _resolve_column(df, ["last_date_read", "Last Date Read"])
    if end_col is None and start_col is None and legacy_col is None:
        df["days_since_read"] = 0
        df["recency_norm"] = 0.5
        return df

    status = (
        df[status_col].astype(str).str.strip().str.lower()
        if status_col is not None
        else pd.Series([""] * len(df), index=df.index)
    )
    dates = pd.Series(pd.NaT, index=df.index)
    if end_col is not None:
        dates = dates.fillna(pd.to_datetime(df[end_col], errors="coerce"))
    if start_col is not None:
        active_start = pd.to_datetime(df[start_col], errors="coerce")
        dates = dates.where(~status.isin({"to-read", "reading"}), dates.fillna(active_start))
        dates = dates.fillna(active_start)
    if legacy_col is not None:
        dates = dates.fillna(pd.to_datetime(df[legacy_col], errors="coerce"))

    df["days_since_read"] = (
        today - dates.fillna(today)
    ).dt.days

    df["recency_norm"] = _min_max(df["days_since_read"], reverse=True)

    return df


def compute_score(df, rating_weight=0.7, recency_weight=0.3):
    if "rating_norm" not in df.columns:
        df["rating_norm"] = 0.5
    if "recency_norm" not in df.columns:
        df["recency_norm"] = 0.5

    df["score"] = (
        rating_weight * df["rating_norm"] +
        recency_weight * df["recency_norm"]
    )

    return df
