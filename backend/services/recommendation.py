# backend/services/recommendation.py

import numpy as np

from backend.book_data import load_data
from backend.preprocess.normalize import normalize_rating, compute_recency
from backend.ranking.score import score_tbr_books, recommend_one


def clean_for_json(df):
    return df.replace({np.nan: None})


def get_recommendation():

    df = load_data()

    if df.empty:
        print("dataframe is empty")
        return []

    df = normalize_rating(df)

    df = compute_recency(df)

    tbr_ranked = score_tbr_books(df)

    rec = recommend_one(tbr_ranked)

    if rec is None:
        print("recommend_one returned None")
        return []

    if rec.empty:
        print("recommend_one returned empty DataFrame")
        return []

    result = clean_for_json(rec).to_dict(orient="records")

    return result