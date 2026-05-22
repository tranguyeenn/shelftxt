import numpy as np
from book_data import load_data
from preprocess.normalize import normalize_rating, compute_recency
from ranking.score import score_tbr_books, recommend_one

def clean_for_json(df):
    return df.replace({np.nan: None})

def get_recommendation():
    df = load_data()
    df = normalize_rating(df)
    df = compute_recency(df)
    tbr_ranked = score_tbr_books(df)
    rec = recommend_one(tbr_ranked)

    if rec is None or len(rec) == 0:
        return []

    return clean_for_json(rec).to_dict(orient="records")