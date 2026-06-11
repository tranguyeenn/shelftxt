from backend.book_data import load_data, save_data


def get_all_books():
    return load_data()


def save_books(df):
    save_data(df)


def book_exists(title: str) -> bool:
    df = load_data()
    return title in df["Title"].values


def get_book_row(df, title: str):
    return df["Title"] == title