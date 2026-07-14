import unittest
from contextlib import ExitStack
from unittest.mock import ANY, AsyncMock, patch
from uuid import UUID
from datetime import date, datetime, timedelta, timezone

import httpx
from fastapi.testclient import TestClient
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from backend import api
from backend.auth.dependencies import get_current_user
from backend.db.database import Base, get_db
from backend.db.models import Book, MetadataJob, Profile
from backend.services.page_lookup import BookMetadata, GoogleBooksRateLimited, OpenLibraryTimeout
from backend.services.page_count_lookup import PageCountResult
from backend.services.recommendation import get_recommendation


TEST_USER_ID = UUID("00000000-0000-0000-0000-000000000001")
OTHER_USER_ID = UUID("00000000-0000-0000-0000-000000000002")

SQLALCHEMY_DATABASE_URL = "sqlite://"

engine = create_engine(
    SQLALCHEMY_DATABASE_URL,
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)

TestingSessionLocal = sessionmaker(
    autocommit=False,
    autoflush=False,
    bind=engine,
)


def override_get_db():
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()


def override_get_current_user():
    db = TestingSessionLocal()
    try:
        return db.query(Profile).filter(Profile.id == TEST_USER_ID).first()
    finally:
        db.close()


api.app.dependency_overrides[get_db] = override_get_db
api.app.dependency_overrides[get_current_user] = override_get_current_user


def _seed_profile(
    *,
    user_id=TEST_USER_ID,
    email="test@shelftxt.local",
    username="test",
):
    db = TestingSessionLocal()
    profile = Profile(
        id=user_id,
        email=email,
        username=username,
    )
    db.add(profile)
    db.commit()
    db.close()


def _seed_book(
    *,
    title="Book",
    authors="Author",
    isbn_uid="book-1",
    user_id=TEST_USER_ID,
    read_status="to-read",
    star_rating=None,
    last_date_read=None,
    start_date=None,
    end_date=None,
    progress_percent=0,
    pages_read=0,
    total_pages=None,
    tracking_mode=None,
    description=None,
    subjects=None,
    genres=None,
    first_publish_year=None,
    metadata_source=None,
):
    def _date(value):
        if value is None or isinstance(value, date):
            return value
        return date.fromisoformat(value)

    db = TestingSessionLocal()
    book = Book(
        title=title,
        authors=authors,
        isbn_uid=isbn_uid,
        user_id=user_id,
        read_status=read_status,
        star_rating=star_rating,
        last_date_read=_date(last_date_read),
        start_date=_date(start_date),
        end_date=_date(end_date),
        progress_percent=progress_percent,
        pages_read=pages_read,
        total_pages=total_pages,
        tracking_mode=tracking_mode,
        description=description,
        subjects=subjects,
        genres=genres,
        first_publish_year=first_publish_year,
        metadata_source=metadata_source,
    )
    db.add(book)
    db.commit()
    db.refresh(book)
    db.close()
    return book


class ApiTests(unittest.TestCase):
    def setUp(self):
        Base.metadata.drop_all(bind=engine)
        Base.metadata.create_all(bind=engine)
        _seed_profile()
        self.page_count_http_patcher = patch(
            "backend.services.page_count_lookup.httpx.get",
            side_effect=AssertionError("real HTTP call in API test"),
        )
        self.mock_page_count_http_get = self.page_count_http_patcher.start()
        self.addCleanup(self.page_count_http_patcher.stop)
        self.page_lookup_http_patcher = patch(
            "backend.services.page_lookup.httpx.get",
            side_effect=httpx.TimeoutException("real HTTP call in API test"),
        )
        self.mock_page_lookup_http_get = self.page_lookup_http_patcher.start()
        self.addCleanup(self.page_lookup_http_patcher.stop)
        self.client = TestClient(api.app)

    def external_work_guard(self):
        stack = ExitStack()
        for target in (
            "backend.services.page_lookup.lookup_book_metadata",
            "backend.services.page_lookup.lookup_google_books_by_isbn",
            "backend.services.page_lookup.lookup_open_library_by_isbn",
            "backend.services.page_lookup.lookup_open_library_by_title",
            "backend.services.page_lookup.httpx.get",
            "backend.services.page_count_lookup.lookup_page_count",
            "backend.services.page_count_lookup.lookup_page_count_by_title",
            "backend.services.page_count_lookup.lookup_page_count_result",
            "backend.services.page_count_lookup.backfill_missing_page_counts",
            "backend.services.page_count_lookup.httpx.get",
            "app.integrations.librarything.fetch_related_isbns",
            "app.integrations.librarything.fetch_work_by_title",
            "backend.services.book_search._open_library_results",
            "backend.services.book_resolver.resolve_book",
            "backend.services.book_resolver.librarything.fetch_related_isbns",
        ):
            stack.enter_context(
                patch(
                    target,
                    side_effect=AssertionError(
                        f"user-facing endpoint attempted external/background work via {target}"
                    ),
                )
            )
        return stack

    def test_health_is_static_and_does_not_require_db_or_auth(self):
        def broken_dependency():
            raise AssertionError("health should not resolve dependencies")

        original_overrides = dict(api.app.dependency_overrides)
        api.app.dependency_overrides[get_db] = broken_dependency
        api.app.dependency_overrides[get_current_user] = broken_dependency
        try:
            response = self.client.get("/health")
        finally:
            api.app.dependency_overrides.clear()
            api.app.dependency_overrides.update(original_overrides)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["status"], "healthy")

    def test_ready_returns_success_when_database_responds(self):
        response = self.client.get("/ready")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["status"], "ready")

    def test_ready_returns_503_when_database_check_fails(self):
        class BrokenSession:
            def execute(self, _statement):
                raise SQLAlchemyError("database unavailable")

        def broken_db():
            yield BrokenSession()

        original_overrides = dict(api.app.dependency_overrides)
        api.app.dependency_overrides[get_db] = broken_db
        try:
            response = self.client.get("/ready")
        finally:
            api.app.dependency_overrides.clear()
            api.app.dependency_overrides.update(original_overrides)

        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.json()["detail"], "Database unavailable")

    def test_ready_returns_503_when_required_table_is_missing(self):
        with engine.begin() as connection:
            connection.exec_driver_sql("DROP TABLE reading_activity")

        response = self.client.get("/ready")

        self.assertEqual(response.status_code, 503)
        self.assertIn("reading_activity", response.json()["detail"])

    def test_get_books_default_pagination(self):
        for i in range(25):
            _seed_book(
                title=f"Book {i}",
                authors=f"Author {i}",
                isbn_uid=f"id-{i}",
            )

        response = self.client.get("/books")

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["page"], 1)
        self.assertEqual(payload["limit"], 20)
        self.assertEqual(payload["total"], 25)
        self.assertEqual(len(payload["results"]), 20)
        self.assertEqual(payload["results"][0]["Title"], "Book 0")
        self.assertEqual(payload["results"][-1]["Title"], "Book 19")

    def test_import_schema_includes_csv_progress_fields(self):
        schema = api.app.openapi()["components"]["schemas"]
        import_row_properties = schema["ImportRow"]["properties"]

        self.assertIn("title", import_row_properties)
        self.assertIn("isbn_uid", import_row_properties)
        self.assertIn("author", import_row_properties)
        self.assertIn("total_pages", import_row_properties)
        self.assertIn("read_status", import_row_properties)
        self.assertIn("Star Rating", import_row_properties)
        self.assertIn("pages_read", import_row_properties)
        self.assertIn("progress_percent", import_row_properties)

        example_row = schema["ImportBooks"]["examples"][0]["books"][0]
        self.assertEqual(example_row["read_status"], "reading")
        self.assertEqual(example_row["star_rating"], 4.75)
        self.assertEqual(example_row["pages_read"], 120)
        self.assertEqual(example_row["progress_percent"], 39.47)

    def test_get_books_explicit_page_and_limit(self):
        for i in range(12):
            _seed_book(
                title=f"Book {i}",
                authors=f"Author {i}",
                isbn_uid=f"id-{i}",
            )

        response = self.client.get("/books?page=2&limit=5")

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["page"], 2)
        self.assertEqual(payload["limit"], 5)
        self.assertEqual(payload["total"], 12)
        self.assertEqual(len(payload["results"]), 5)
        self.assertEqual(
            [row["Title"] for row in payload["results"]],
            ["Book 5", "Book 6", "Book 7", "Book 8", "Book 9"],
        )

    def test_get_books_page_past_end_returns_empty_results(self):
        for i in range(3):
            _seed_book(
                title=f"Book {i}",
                authors=f"Author {i}",
                isbn_uid=f"id-{i}",
            )

        response = self.client.get("/books?page=10&limit=5")

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["total"], 3)
        self.assertEqual(payload["results"], [])

    def test_get_books_rejects_invalid_query_params(self):
        for query in (
            "page=0",
            "limit=0",
            "page=-1",
            "limit=-5",
            "page=abc",
            "limit=xyz",
            "limit=101",
        ):
            with self.subTest(query=query):
                response = self.client.get(f"/books?{query}")
                self.assertEqual(response.status_code, 422)

    def test_get_books_only_returns_current_user_books(self):
        _seed_profile(
            user_id=OTHER_USER_ID,
            email="other@shelftxt.local",
            username="other",
        )

        _seed_book(title="Mine", authors="A", isbn_uid="mine")
        _seed_book(
            title="Not Mine",
            authors="B",
            isbn_uid="not-mine",
            user_id=OTHER_USER_ID,
        )

        response = self.client.get("/books")

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["total"], 1)
        self.assertEqual(payload["results"][0]["Title"], "Mine")

    def test_get_books_does_not_trigger_external_or_background_work(self):
        _seed_book(title="Mine", authors="A", isbn_uid="mine")

        with self.external_work_guard():
            response = self.client.get("/books")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["total"], 1)

    def test_get_book_by_id(self):
        _seed_book(title="Existing", authors="Author A", isbn_uid="book-1")

        response = self.client.get("/books/book-1")

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["Title"], "Existing")
        self.assertEqual(payload["Authors"], "Author A")
        self.assertEqual(payload["ISBN/UID"], "book-1")

    def test_get_book_by_id_does_not_trigger_metadata_providers(self):
        _seed_book(title="Stored", authors="Author", isbn_uid="stored-1")

        with self.external_work_guard():
            response = self.client.get("/books/stored-1")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["Title"], "Stored")

    def test_export_does_not_trigger_metadata_providers(self):
        _seed_book(title="Stored", authors="Author", isbn_uid="stored-1")

        with self.external_work_guard():
            response = self.client.get("/books/export")

        self.assertEqual(response.status_code, 200)
        self.assertIn("Stored", response.text)

    def test_profile_load_does_not_trigger_metadata_providers(self):
        with self.external_work_guard():
            response = self.client.get("/profile/me")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["username"], "test")

    @patch("backend.services.book_resolver.librarything.fetch_related_isbns")
    @patch("backend.services.book_search._open_library_results", return_value=[])
    def test_add_book_search_is_allowed_to_call_metadata_providers(
        self,
        mock_open_library,
        mock_librarything,
    ):
        response = self.client.get("/books/search?q=space%20politics")

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertIn(body["status"], {"empty", "ok"})
        self.assertEqual(body["results"], [])
        self.assertIsInstance(body["diagnostics"], list)
        mock_open_library.assert_called_once_with("space politics")
        mock_librarything.assert_not_called()

    @patch("backend.services.book_search._open_library_results", side_effect=TimeoutError("down"))
    @patch("app.integrations.librarything.fetch_work_by_title", side_effect=TimeoutError("down"))
    def test_add_book_search_returns_degraded_state_when_providers_fail(
        self,
        _mock_librarything,
        _mock_open_library,
    ):
        response = self.client.get("/books/search?q=Dune")

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["status"], "degraded")
        self.assertEqual(body["results"], [])
        self.assertIn("providers failed", body["message"])
        self.assertIsInstance(body["diagnostics"], list)

    @patch("backend.routes.books.scrape_book_metadata", new_callable=AsyncMock)
    def test_metadata_from_url_returns_scraped_metadata(self, mock_scrape):
        from backend.services.book_scraping.models import ScrapeDiagnostic, ScrapeResult, ScrapedBookMetadata

        mock_scrape.return_value = ScrapeResult(
            status="success",
            metadata=ScrapedBookMetadata(
                title="Dune",
                authors=["Frank Herbert"],
                isbn_uid="9780441172719",
                source_url="https://www.penguinrandomhouse.com/books/352036/dune/",
                source_domain="penguinrandomhouse.com",
                confidence_score=0.95,
            ),
            diagnostics=ScrapeDiagnostic(domain="penguinrandomhouse.com", outcome="success"),
        )

        response = self.client.post(
            "/books/metadata/from-url",
            json={"url": "https://www.penguinrandomhouse.com/books/352036/dune/"},
        )

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["status"], "success")
        self.assertEqual(body["metadata"]["title"], "Dune")
        self.assertIsInstance(body["diagnostics"], dict)

    def test_core_routes_work_while_metadata_providers_are_down(self):
        _seed_book(
            title="Stored",
            authors="Author",
            isbn_uid="stored-1",
            read_status="to-read",
        )

        with self.external_work_guard():
            books_response = self.client.get("/books")
            book_response = self.client.get("/books/stored-1")
            recommendation_response = self.client.get("/recommend")

        self.assertEqual(books_response.status_code, 200)
        self.assertEqual(book_response.status_code, 200)
        self.assertEqual(recommendation_response.status_code, 200)

    def test_get_book_by_id_not_found(self):
        response = self.client.get("/books/missing-id")

        self.assertEqual(response.status_code, 404)

    def test_get_book_by_id_cannot_access_other_user_book(self):
        _seed_profile(
            user_id=OTHER_USER_ID,
            email="other@shelftxt.local",
            username="other",
        )

        _seed_book(
            title="Not Mine",
            authors="B",
            isbn_uid="not-mine",
            user_id=OTHER_USER_ID,
        )

        response = self.client.get("/books/not-mine")

        self.assertEqual(response.status_code, 404)

    def test_add_book_appends_new_tbr_row(self):
        response = self.client.post(
            "/books",
            json={"title": "New Book", "author": "New Author"},
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"message": "Book added"})

        books_response = self.client.get("/books")
        payload = books_response.json()

        self.assertEqual(payload["total"], 1)
        book = payload["results"][0]
        self.assertEqual(book["Title"], "New Book")
        self.assertEqual(book["Authors"], "New Author")
        self.assertEqual(book["Read Status"], "to-read")
        self.assertEqual(book["Progress (%)"], 0)
        self.assertEqual(book["Pages Read"], 0)
        self.assertTrue(book["ISBN/UID"].startswith("uid-"))

    def test_add_searched_book_persists_metadata_and_completed_state(self):
        response = self.client.post(
            "/books",
            json={
                "title": "Kindred",
                "author": "Octavia E. Butler",
                "isbn_uid": "9780807083697",
                "total_pages": 264,
                "status": "completed",
                "star_rating": 4.75,
                "end_date": "2026-07-05",
                "description": "A modern classic.",
                "subjects": ["time travel"],
                "genres": ["science fiction"],
                "first_publish_year": 1979,
                "metadata_source": "open_library",
                "work_key": "/works/OL123W",
                "edition_key": "OL123M",
                "related_isbns": ["0807083690"],
            },
        )

        self.assertEqual(response.status_code, 200)
        book = self.client.get("/books").json()["results"][0]
        self.assertEqual(book["ISBN/UID"], "9780807083697")
        self.assertEqual(book["Read Status"], "read")
        self.assertEqual(book["Star Rating"], 4.75)
        self.assertEqual(book["Description"], "A modern classic.")
        self.assertEqual(
            book["metadata"]["librarything"]["related_isbns"],
            ["0807083690"],
        )

    def test_add_book_does_not_trigger_external_or_background_work(self):
        with self.external_work_guard():
            response = self.client.post(
                "/books",
                json={"title": "Fast Add", "author": "Author"},
            )

        self.assertEqual(response.status_code, 200)
        book = self.client.get("/books").json()["results"][0]
        self.assertEqual(book["Title"], "Fast Add")

    @patch("backend.services.page_lookup.lookup_book_metadata")
    def test_add_book_does_not_lookup_metadata(self, mock_lookup):
        response = self.client.post(
            "/books",
            json={"title": "Kindred", "author": "Octavia E. Butler"},
        )

        self.assertEqual(response.status_code, 200)
        book = self.client.get("/books").json()["results"][0]
        self.assertIsNone(book["Description"])
        self.assertIsNone(book["Subjects"])
        self.assertIsNone(book["Genres"])
        self.assertIsNone(book["First Publish Year"])
        self.assertIsNone(book["metadata_source"])
        self.assertIsNone(book["metadata_enriched_at"])
        mock_lookup.assert_not_called()

    def test_delete_book_removes_row(self):
        _seed_book(title="Keep", authors="Author A", isbn_uid="keep-id")
        _seed_book(title="Remove", authors="Author B", isbn_uid="remove-id")

        response = self.client.delete("/books?title=Remove")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"message": "Book deleted"})

        payload = self.client.get("/books").json()
        self.assertEqual(payload["total"], 1)
        self.assertEqual(payload["results"][0]["Title"], "Keep")

    def test_delete_book_by_id(self):
        _seed_book(title="Keep", authors="A", isbn_uid="keep-id")
        _seed_book(title="Remove", authors="B", isbn_uid="remove-id")

        response = self.client.delete("/books/remove-id")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"message": "Book deleted"})

        payload = self.client.get("/books").json()
        self.assertEqual(payload["total"], 1)
        self.assertEqual(payload["results"][0]["ISBN/UID"], "keep-id")

    def test_delete_book_by_id_does_not_trigger_external_or_background_work(self):
        _seed_book(title="Remove", authors="B", isbn_uid="remove-id")

        with self.external_work_guard():
            response = self.client.delete("/books/remove-id")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"message": "Book deleted"})

    def test_delete_book_by_id_cannot_delete_other_user_book(self):
        _seed_profile(
            user_id=OTHER_USER_ID,
            email="other@shelftxt.local",
            username="other",
        )

        _seed_book(title="Mine", authors="A", isbn_uid="mine")
        _seed_book(
            title="Not Mine",
            authors="B",
            isbn_uid="not-mine",
            user_id=OTHER_USER_ID,
        )

        response = self.client.delete("/books/not-mine")

        self.assertEqual(response.status_code, 404)

        payload = self.client.get("/books").json()
        self.assertEqual(payload["total"], 1)
        self.assertEqual(payload["results"][0]["ISBN/UID"], "mine")

        db = TestingSessionLocal()
        try:
            other_book = (
                db.query(Book)
                .filter(Book.user_id == OTHER_USER_ID)
                .filter(Book.isbn_uid == "not-mine")
                .first()
            )
        finally:
            db.close()

        self.assertIsNotNone(other_book)

    def test_patch_move_to_dnf(self):
        _seed_book(
            title="T",
            authors="A",
            isbn_uid="1",
            total_pages=100,
        )

        response = self.client.patch(
            "/books",
            json={"title": "T", "move_to": "dnf"},
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"message": "Book updated"})

        payload = self.client.get("/books/1").json()
        self.assertEqual(payload["Read Status"], "dnf")
        self.assertEqual(payload["Star Rating"], 1)

    def test_patch_book_by_id_updates_editable_metadata(self):
        _seed_book(
            title="Old",
            authors="A",
            isbn_uid="old-id",
            total_pages=100,
            pages_read=20,
            progress_percent=20,
        )

        response = self.client.patch(
            "/books/old-id",
            json={
                "title": "New",
                "author": "",
                "isbn_uid": "new-id",
                "total_pages": 120,
                "status": "completed",
                "pages_read": 10,
            },
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["Title"], "New")
        self.assertEqual(payload["Authors"], "Unknown")
        self.assertEqual(payload["ISBN/UID"], "new-id")
        self.assertEqual(payload["Total Pages"], 120)
        self.assertEqual(payload["Pages Read"], 120)
        self.assertEqual(payload["Read Status"], "read")

    def test_patch_book_by_id_updates_and_clears_star_rating(self):
        _seed_book(
            title="Rated",
            authors="A",
            isbn_uid="rated-id",
            star_rating=4,
        )

        response = self.client.patch(
            "/books/rated-id",
            json={"star_rating": 4.75},
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["Star Rating"], 4.75)

        response = self.client.patch(
            "/books/rated-id",
            json={"star_rating": None},
        )

        self.assertEqual(response.status_code, 200)
        self.assertIsNone(response.json()["Star Rating"])

    def test_patch_pages_read_at_total_auto_completes(self):
        _seed_book(
            title="Almost",
            authors="A",
            isbn_uid="almost-id",
            total_pages=120,
            pages_read=40,
            progress_percent=33.33,
        )

        response = self.client.patch(
            "/books/almost-id",
            json={"pages_read": 120},
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["Read Status"], "read")
        self.assertEqual(payload["Pages Read"], 120)
        self.assertEqual(payload["Progress (%)"], 100)

    def test_patch_book_by_id_does_not_trigger_external_or_background_work(self):
        _seed_book(
            title="Old",
            authors="A",
            isbn_uid="old-id",
            total_pages=100,
        )

        with self.external_work_guard():
            response = self.client.patch(
                "/books/old-id",
                json={"title": "New", "author": "B"},
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["Title"], "New")

    def test_patch_cannot_update_other_user_book(self):
        _seed_profile(
            user_id=OTHER_USER_ID,
            email="other@shelftxt.local",
            username="other",
        )

        _seed_book(
            title="Not Mine",
            authors="B",
            isbn_uid="not-mine",
            user_id=OTHER_USER_ID,
            total_pages=100,
        )

        response = self.client.patch(
            "/books",
            json={"title": "Not Mine", "move_to": "dnf"},
        )

        self.assertEqual(response.status_code, 404)

    def test_update_book_progress_by_id(self):
        _seed_book(
            title="In Progress",
            authors="A",
            isbn_uid="book-1",
            progress_percent=10,
            pages_read=50,
            total_pages=500,
        )

        response = self.client.patch(
            "/books/book-1/progress",
            json={"status": "reading", "pages_read": 120},
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["Pages Read"], 120)
        self.assertEqual(payload["Read Status"], "to-read")
        self.assertEqual(payload["Progress (%)"], 24)

    def test_update_book_progress_accepts_percent_only_without_total_pages(self):
        _seed_book(
            title="Percent Progress",
            authors="A",
            isbn_uid="percent-only",
            total_pages=None,
        )

        response = self.client.patch(
            "/books/percent-only/progress",
            json={"progress_percent": 42},
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["Read Status"], "to-read")
        self.assertEqual(payload["Total Pages"], None)
        self.assertEqual(payload["Pages Read"], 0)
        self.assertEqual(payload["Progress (%)"], 42)

    def test_update_book_progress_calculates_percent_from_pages_and_total(self):
        _seed_book(
            title="Page Progress",
            authors="A",
            isbn_uid="page-progress",
            total_pages=None,
        )

        response = self.client.patch(
            "/books/page-progress/progress",
            json={"status": "reading", "pages_read": 50, "total_pages": 200},
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["Total Pages"], 200)
        self.assertEqual(payload["Pages Read"], 50)
        self.assertEqual(payload["Progress (%)"], 25)

    def test_inline_edit_total_pages(self):
        _seed_book(
            title="Inline Total",
            authors="A",
            isbn_uid="inline-total",
            pages_read=40,
            total_pages=None,
            progress_percent=20,
        )

        response = self.client.patch(
            "/books/inline-total/progress",
            json={"total_pages": 200},
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["Total Pages"], 200)
        self.assertEqual(payload["Pages Read"], 40)
        self.assertEqual(payload["Progress (%)"], 20)

    def test_inline_edit_pages_read(self):
        _seed_book(
            title="Inline Pages",
            authors="A",
            isbn_uid="inline-pages",
            pages_read=10,
            total_pages=300,
            progress_percent=3.33,
        )

        response = self.client.patch(
            "/books/inline-pages/progress",
            json={"pages_read": 120},
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["Pages Read"], 120)
        self.assertEqual(payload["Progress (%)"], 40)

    def test_inline_edit_progress_percent(self):
        _seed_book(
            title="Inline Percent",
            authors="A",
            isbn_uid="inline-percent",
        )

        response = self.client.patch(
            "/books/inline-percent/progress",
            json={"progress_percent": 45},
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["Progress (%)"], 45)
        self.assertEqual(payload["Pages Read"], 0)
        self.assertIsNone(payload["Total Pages"])

    def test_tracking_mode_persisted_after_patch(self):
        _seed_book(
            title="Mode Patch",
            authors="A",
            isbn_uid="mode-patch",
            total_pages=300,
            tracking_mode="pages",
        )

        response = self.client.patch(
            "/books/mode-patch/progress",
            json={"tracking_mode": "percentage", "progress_percent": 45},
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["tracking_mode"], "percentage")

    def test_tracking_mode_remains_after_api_fetch(self):
        _seed_book(
            title="Mode Reload",
            authors="A",
            isbn_uid="mode-reload",
            total_pages=300,
            tracking_mode="percentage",
        )

        response = self.client.get("/books/mode-reload")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["tracking_mode"], "percentage")
        self.assertEqual(response.json()["Tracking Mode"], "percentage")

    def test_switching_to_percentage_and_refreshing_keeps_percentage(self):
        _seed_book(
            title="Mode Percentage",
            authors="A",
            isbn_uid="mode-percentage",
            total_pages=300,
            tracking_mode="pages",
        )

        patch_response = self.client.patch(
            "/books/mode-percentage/progress",
            json={"tracking_mode": "percentage", "progress_percent": 25},
        )
        fetch_response = self.client.get("/books/mode-percentage")

        self.assertEqual(patch_response.status_code, 200)
        self.assertEqual(fetch_response.json()["tracking_mode"], "percentage")

    def test_switching_to_pages_and_refreshing_keeps_pages(self):
        _seed_book(
            title="Mode Pages",
            authors="A",
            isbn_uid="mode-pages",
            total_pages=None,
            tracking_mode="percentage",
        )

        patch_response = self.client.patch(
            "/books/mode-pages/progress",
            json={"tracking_mode": "pages", "pages_read": 20, "total_pages": 200},
        )
        fetch_response = self.client.get("/books/mode-pages")

        self.assertEqual(patch_response.status_code, 200)
        self.assertEqual(fetch_response.json()["tracking_mode"], "pages")

    def test_adding_total_pages_later_does_not_overwrite_tracking_mode(self):
        _seed_book(
            title="Mode With Pages Later",
            authors="A",
            isbn_uid="mode-with-pages-later",
            total_pages=None,
            tracking_mode="percentage",
        )

        response = self.client.patch(
            "/books/mode-with-pages-later/progress",
            json={"total_pages": 320},
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["Total Pages"], 320)
        self.assertEqual(response.json()["tracking_mode"], "percentage")

    def test_existing_book_with_total_pages_defaults_tracking_mode_to_pages(self):
        _seed_book(
            title="Legacy Pages",
            authors="A",
            isbn_uid="legacy-pages",
            total_pages=300,
            tracking_mode=None,
        )

        response = self.client.get("/books/legacy-pages")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["tracking_mode"], "pages")

    def test_existing_book_without_total_pages_defaults_tracking_mode_to_percentage(self):
        _seed_book(
            title="Legacy Percentage",
            authors="A",
            isbn_uid="legacy-percentage",
            total_pages=None,
            tracking_mode=None,
        )

        response = self.client.get("/books/legacy-percentage")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["tracking_mode"], "percentage")

    def test_update_book_progress_rejects_invalid_tracking_mode(self):
        _seed_book(title="Bad Mode", authors="A", isbn_uid="bad-mode")

        response = self.client.patch(
            "/books/bad-mode/progress",
            json={"tracking_mode": "chapters"},
        )

        self.assertEqual(response.status_code, 422)

    def test_inline_edit_start_date(self):
        _seed_book(title="Inline Start", authors="A", isbn_uid="inline-start")

        response = self.client.patch(
            "/books/inline-start/progress",
            json={"start_date": "2026-01-05"},
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["Start Date"], "2026-01-05")

    def test_inline_edit_end_date(self):
        _seed_book(title="Inline End", authors="A", isbn_uid="inline-end")

        response = self.client.patch(
            "/books/inline-end/progress",
            json={"end_date": "2026-01-12"},
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["End Date"], "2026-01-12")

    def test_update_book_progress_allows_missing_total_pages(self):
        _seed_book(
            title="No Total",
            authors="A",
            isbn_uid="no-total",
            total_pages=None,
        )

        response = self.client.patch(
            "/books/no-total/progress",
            json={"status": "reading", "progress_percent": 12.5},
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["Total Pages"], None)
        self.assertEqual(payload["Progress (%)"], 12.5)

    def test_completed_book_preserves_end_date_after_total_pages_update(self):
        _seed_book(
            title="Already Done",
            authors="A",
            isbn_uid="already-done",
            read_status="read",
            progress_percent=100,
            pages_read=0,
            total_pages=None,
            last_date_read="2025-02-03",
            end_date="2025-02-03",
        )

        response = self.client.patch(
            "/books/already-done",
            json={"total_pages": 320},
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["Read Status"], "read")
        self.assertEqual(payload["Total Pages"], 320)
        self.assertEqual(payload["End Date"], "2025-02-03")

    def test_non_completed_book_becoming_completed_sets_end_date(self):
        _seed_book(
            title="Now Done",
            authors="A",
            isbn_uid="now-done",
            progress_percent=80,
            pages_read=0,
            total_pages=None,
        )

        response = self.client.patch(
            "/books/now-done/progress",
            json={"status": "completed", "progress_percent": 100},
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["Read Status"], "read")
        self.assertEqual(payload["Progress (%)"], 100)
        self.assertIsNotNone(payload["End Date"])

    def test_non_completed_book_becoming_completed_respects_manual_end_date(self):
        _seed_book(
            title="Done With Date",
            authors="A",
            isbn_uid="done-with-date",
            progress_percent=80,
        )

        response = self.client.patch(
            "/books/done-with-date/progress",
            json={
                "status": "completed",
                "progress_percent": 100,
                "end_date": "2026-01-12",
            },
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["Read Status"], "read")
        self.assertEqual(payload["End Date"], "2026-01-12")

    def test_completed_book_keeps_end_date_when_metadata_fields_change(self):
        _seed_book(
            title="Metadata Done",
            authors="A",
            isbn_uid="metadata-done",
            read_status="read",
            progress_percent=100,
            end_date="2025-02-03",
        )

        response = self.client.patch(
            "/books/metadata-done",
            json={"title": "Metadata Done Updated", "author": "B"},
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["Title"], "Metadata Done Updated")
        self.assertEqual(payload["End Date"], "2025-02-03")

    def test_completed_book_keeps_end_date_when_status_is_still_completed(self):
        _seed_book(
            title="Still Done",
            authors="A",
            isbn_uid="still-done",
            read_status="read",
            progress_percent=100,
            end_date="2025-02-03",
        )

        response = self.client.patch(
            "/books/still-done/progress",
            json={"status": "completed", "progress_percent": 100},
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["End Date"], "2025-02-03")

    def test_update_book_progress_rejects_progress_percent_outside_range(self):
        _seed_book(title="Bad Percent", authors="A", isbn_uid="bad-percent")

        response = self.client.patch(
            "/books/bad-percent/progress",
            json={"progress_percent": 101},
        )

        self.assertEqual(response.status_code, 422)

    def test_update_book_progress_rejects_negative_pages_read(self):
        _seed_book(title="Bad Pages", authors="A", isbn_uid="bad-pages")

        response = self.client.patch(
            "/books/bad-pages/progress",
            json={"pages_read": -1},
        )

        self.assertEqual(response.status_code, 422)

    def test_update_book_progress_rejects_invalid_total_pages(self):
        _seed_book(title="Bad Total", authors="A", isbn_uid="bad-total")

        response = self.client.patch(
            "/books/bad-total/progress",
            json={"total_pages": 0},
        )

        self.assertEqual(response.status_code, 422)

    def test_update_book_progress_rejects_start_date_after_end_date(self):
        _seed_book(title="Bad Date Range", authors="A", isbn_uid="bad-date-range")

        response = self.client.patch(
            "/books/bad-date-range/progress",
            json={"start_date": "2026-02-01", "end_date": "2026-01-01"},
        )

        self.assertEqual(response.status_code, 400)

    def test_update_book_progress_auto_completes(self):
        _seed_book(
            title="Almost Done",
            authors="A",
            isbn_uid="book-2",
            progress_percent=90,
            pages_read=450,
            total_pages=500,
        )

        response = self.client.patch(
            "/books/book-2/progress",
            json={"status": "reading", "pages_read": 500},
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["Read Status"], "read")
        self.assertEqual(payload["Pages Read"], 500)
        self.assertEqual(payload["Progress (%)"], 100)

    def test_update_book_progress_rejects_pages_over_total(self):
        _seed_book(
            title="TBR",
            authors="A",
            isbn_uid="book-3",
            total_pages=500,
        )

        response = self.client.patch(
            "/books/book-3/progress",
            json={"status": "reading", "pages_read": 600},
        )

        self.assertEqual(response.status_code, 400)

    def test_update_book_progress_cannot_update_other_user_book(self):
        _seed_profile(
            user_id=OTHER_USER_ID,
            email="other@shelftxt.local",
            username="other",
        )

        _seed_book(
            title="Not Mine",
            authors="B",
            isbn_uid="not-mine",
            user_id=OTHER_USER_ID,
            total_pages=100,
        )

        response = self.client.patch(
            "/books/not-mine/progress",
            json={"status": "reading", "pages_read": 20},
        )

        self.assertEqual(response.status_code, 404)

    @patch(
        "backend.services.postgres_books.get_all_books",
        side_effect=AssertionError("clear should use direct scoped delete"),
    )
    def test_clear_library(self, mock_get_all_books):
        _seed_book(title="Gone", authors="A", isbn_uid="1")

        response = self.client.post("/books/clear", json={"confirm": True})

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"deleted": 1})
        mock_get_all_books.assert_not_called()

        payload = self.client.get("/books").json()
        self.assertEqual(payload["total"], 0)

    def test_clear_library_resets_metadata_progress(self):
        _seed_book(title="Gone", authors="A", isbn_uid="gone")
        db = TestingSessionLocal()
        try:
            db.add(
                MetadataJob(
                    user_id=TEST_USER_ID,
                    status="processing",
                    processed_count=70,
                    total_count=252,
                )
            )
            db.commit()
        finally:
            db.close()

        clear_response = self.client.post("/books/clear", json={"confirm": True})
        status_response = self.client.get("/metadata/status")

        self.assertEqual(clear_response.status_code, 200)
        self.assertEqual(status_response.status_code, 200)
        payload = status_response.json()
        self.assertEqual(payload["total_books"], 0)
        self.assertEqual(payload["books_with_genres"], 0)
        self.assertEqual(payload["job"]["status"], "completed")
        self.assertEqual(payload["job"]["processed_count"], 0)
        self.assertEqual(payload["job"]["total_count"], 0)

    def test_clear_library_requires_confirm(self):
        response = self.client.post("/books/clear", json={"confirm": False})

        self.assertEqual(response.status_code, 400)

    def test_clear_library_only_clears_current_user_books(self):
        _seed_profile(
            user_id=OTHER_USER_ID,
            email="other@shelftxt.local",
            username="other",
        )

        _seed_book(title="Mine", authors="A", isbn_uid="mine")
        _seed_book(
            title="Not Mine",
            authors="B",
            isbn_uid="not-mine",
            user_id=OTHER_USER_ID,
        )

        response = self.client.post("/books/clear", json={"confirm": True})

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["deleted"], 1)

        db = TestingSessionLocal()
        try:
            current_user_books = (
                db.query(Book)
                .filter(Book.user_id == TEST_USER_ID)
                .all()
            )
            other_book = (
                db.query(Book)
                .filter(Book.user_id == OTHER_USER_ID)
                .filter(Book.isbn_uid == "not-mine")
                .first()
            )
        finally:
            db.close()

        self.assertEqual(current_user_books, [])
        self.assertIsNotNone(other_book)

    def test_clear_library_does_not_trigger_external_or_background_work(self):
        _seed_book(title="Gone", authors="A", isbn_uid="gone")

        with self.external_work_guard():
            response = self.client.post("/books/clear", json={"confirm": True})

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"deleted": 1})

    def test_delete_all_books_individually_resets_metadata_progress(self):
        _seed_book(title="Gone 1", authors="A", isbn_uid="gone-1")
        _seed_book(title="Gone 2", authors="A", isbn_uid="gone-2")
        db = TestingSessionLocal()
        try:
            db.add(
                MetadataJob(
                    user_id=TEST_USER_ID,
                    status="pending",
                    processed_count=1,
                    total_count=2,
                )
            )
            db.commit()
        finally:
            db.close()

        first = self.client.delete("/books/gone-1")
        mid_status = self.client.get("/metadata/status").json()
        second = self.client.delete("/books/gone-2")
        final_status = self.client.get("/metadata/status").json()

        self.assertEqual(first.status_code, 200)
        self.assertEqual(second.status_code, 200)
        self.assertEqual(mid_status["total_books"], 1)
        self.assertEqual(mid_status["job"]["status"], "pending")
        self.assertEqual(final_status["total_books"], 0)
        self.assertEqual(final_status["job"]["status"], "completed")
        self.assertEqual(final_status["job"]["processed_count"], 0)
        self.assertEqual(final_status["job"]["total_count"], 0)

    def test_metadata_generation_interrupted_by_deletion_resets_progress(self):
        _seed_book(title="Gone", authors="A", isbn_uid="gone")
        db = TestingSessionLocal()
        try:
            job = MetadataJob(
                user_id=TEST_USER_ID,
                status="processing",
                processed_count=70,
                total_count=252,
            )
            db.add(job)
            db.commit()
        finally:
            db.close()

        delete_response = self.client.delete("/books/gone")
        status_response = self.client.get("/metadata/status")

        self.assertEqual(delete_response.status_code, 200)
        payload = status_response.json()
        self.assertEqual(payload["total_books"], 0)
        self.assertEqual(payload["job"]["status"], "completed")
        self.assertEqual(payload["job"]["processed_count"], 0)
        self.assertEqual(payload["job"]["total_count"], 0)

    @patch("backend.routes.metadata.process_metadata_job")
    def test_metadata_status_refresh_after_deletion_returns_zero_progress(self, mock_process_metadata_job):
        _seed_book(title="Gone", authors="A", isbn_uid="gone")
        self.client.post("/metadata/generate")

        self.client.delete("/books/gone")
        refreshed = self.client.get("/metadata/status")

        self.assertEqual(refreshed.status_code, 200)
        payload = refreshed.json()
        self.assertEqual(payload["total_books"], 0)
        self.assertEqual(payload["job"], {
            "status": "completed",
            "processed_count": 0,
            "total_count": 0,
            "error_message": None,
        })
        mock_process_metadata_job.assert_called_once()

    def test_import_skips_duplicate_title(self):
        _seed_book(
            title="Existing",
            authors="A",
            isbn_uid="1",
        )

        response = self.client.post(
            "/books/import",
            json={
                "books": [
                    {"title": "Existing", "author": "X"},
                    {"title": "New", "author": "Y"},
                ]
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["imported_count"], 1)
        self.assertEqual(response.json()["skipped_count"], 1)
        self.assertEqual(response.json()["duplicate_count"], 1)
        self.assertEqual(response.json()["skipped_duplicates"], 1)

        payload = self.client.get("/books").json()
        self.assertEqual(payload["total"], 2)

        titles = [book["Title"] for book in payload["results"]]
        self.assertIn("Existing", titles)
        self.assertIn("New", titles)

    def test_import_skips_if_no_books_added(self):
        _seed_book(
            title="Existing Book",
            authors="A",
            isbn_uid="existing-book",
        )

        response = self.client.post(
            "/books/import",
            json={"books": [{"title": "Existing Book", "author": "X"}]},
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["imported_count"], 0)
        self.assertEqual(response.json()["skipped_duplicates"], 1)

        payload = self.client.get("/books").json()
        self.assertEqual(payload["total"], 1)
        self.assertEqual(payload["results"][0]["Title"], "Existing Book")

    def test_import_adds_books_to_current_user(self):
        _seed_profile(
            user_id=OTHER_USER_ID,
            email="other@shelftxt.local",
            username="other",
        )

        response = self.client.post(
            "/books/import",
            json={"books": [{"title": "Imported Mine", "author": "A"}]},
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["imported_count"], 1)

        db = TestingSessionLocal()
        try:
            current_user_book = (
                db.query(Book)
                .filter(Book.user_id == TEST_USER_ID)
                .filter(Book.title == "Imported Mine")
                .first()
            )
            other_user_book = (
                db.query(Book)
                .filter(Book.user_id == OTHER_USER_ID)
                .filter(Book.title == "Imported Mine")
                .first()
            )
        finally:
            db.close()

        self.assertIsNotNone(current_user_book)
        self.assertIsNone(other_user_book)

    def test_import_does_not_trigger_external_or_background_work(self):
        with self.external_work_guard():
            response = self.client.post(
                "/books/import",
                json={"books": [{"title": "Imported", "author": "A"}]},
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["imported_count"], 1)

    @patch("backend.services.page_lookup.lookup_open_library_by_title", return_value=None)
    def test_import_star_rating_persists(self, mock_lookup_open_library_by_title):
        response = self.client.post(
            "/books/import",
            json={
                "books": [
                    {
                        "title": "The Great Gatsby",
                        "author": "F. Scott Fitzgerald",
                        "Star Rating": "4.00",
                    }
                ]
            },
        )

        self.assertEqual(response.status_code, 200)
        book = self.client.get("/books").json()["results"][0]
        self.assertEqual(book["Star Rating"], 4.0)
        mock_lookup_open_library_by_title.assert_not_called()

    @patch("backend.services.page_lookup.lookup_open_library_by_title", return_value=None)
    def test_import_rating_aliases_and_decimal_values_persist(self, mock_lookup_open_library_by_title):
        response = self.client.post(
            "/books/import",
            json={
                "books": [
                    {"title": "Rating A", "author": "A", "Star Rating": 5},
                    {"title": "Rating B", "author": "A", "star_rating": 5.0},
                    {"title": "Rating C", "author": "A", "rating": 4.75},
                    {"title": "Rating D", "author": "A", "Rating": "4.5"},
                    {"title": "Rating E", "author": "A", "Stars": "3.25"},
                    {"title": "Rating F", "author": "A", "My Rating": "2.5"},
                    {"title": "Rating G", "author": "A", "Star Rating": "0.25"},
                ]
            },
        )

        self.assertEqual(response.status_code, 200)
        books = {
            row["Title"]: row["Star Rating"]
            for row in self.client.get("/books?limit=100").json()["results"]
        }
        self.assertEqual(books["Rating A"], 5.0)
        self.assertEqual(books["Rating B"], 5.0)
        self.assertEqual(books["Rating C"], 4.75)
        self.assertEqual(books["Rating D"], 4.5)
        self.assertEqual(books["Rating E"], 3.25)
        self.assertEqual(books["Rating F"], 2.5)
        self.assertEqual(books["Rating G"], 0.25)
        mock_lookup_open_library_by_title.assert_not_called()

    @patch("backend.services.page_lookup.lookup_open_library_by_title", return_value=None)
    def test_import_empty_and_nan_ratings_become_none(self, mock_lookup_open_library_by_title):
        response = self.client.post(
            "/books/import",
            json={
                "books": [
                    {"title": "Empty Rating", "author": "A", "Star Rating": ""},
                    {"title": "Nan Rating", "author": "A", "Rating": "NaN"},
                ]
            },
        )

        self.assertEqual(response.status_code, 200)
        books = {
            row["Title"]: row["Star Rating"]
            for row in self.client.get("/books").json()["results"]
        }
        self.assertIsNone(books["Empty Rating"])
        self.assertIsNone(books["Nan Rating"])
        mock_lookup_open_library_by_title.assert_not_called()

    def test_import_rejects_negative_rating(self):
        response = self.client.post(
            "/books/import",
            json={"books": [{"title": "Negative Rating", "author": "A", "Star Rating": -0.25}]},
        )

        self.assertEqual(response.status_code, 422)

    def test_import_rejects_rating_above_five(self):
        response = self.client.post(
            "/books/import",
            json={"books": [{"title": "Too High Rating", "author": "A", "Star Rating": 5.25}]},
        )

        self.assertEqual(response.status_code, 422)

    @patch("backend.services.page_lookup.lookup_open_library_by_title")
    def test_import_accepts_authors_alias(self, mock_lookup_open_library_by_title):
        response = self.client.post(
            "/books/import",
            json={"books": [{"title": "Dune", "Authors": "Frank Herbert", "total_pages": 592}]},
        )

        self.assertEqual(response.status_code, 200)
        book = self.client.get("/books").json()["results"][0]
        self.assertEqual(book["Authors"], "Frank Herbert")
        self.assertEqual(book["Total Pages"], 592)
        mock_lookup_open_library_by_title.assert_not_called()

    @patch("backend.services.page_lookup.lookup_open_library_by_title")
    def test_import_title_only_uses_csv_fields(self, mock_lookup_open_library_by_title):
        response = self.client.post(
            "/books/import",
            json={"books": [{"title": "Dune"}]},
        )

        self.assertEqual(response.status_code, 200)
        book = self.client.get("/books").json()["results"][0]
        self.assertEqual(book["Authors"], "Unknown")
        self.assertIsNone(book["Total Pages"])
        mock_lookup_open_library_by_title.assert_not_called()

    @patch("backend.services.page_lookup.lookup_google_books_by_isbn")
    @patch("backend.services.page_lookup.lookup_open_library_by_isbn")
    def test_import_preserves_isbn_uid_without_metadata_lookup(
        self, mock_lookup_open_library_by_isbn, mock_lookup_google_books_by_isbn
    ):
        response = self.client.post(
            "/books/import",
            json={
                "books": [
                    {
                        "title": "Dune",
                        "author": "Frank Herbert",
                        "ISBN/UID": "9780441172719",
                        "total_pages": 592,
                    }
                ]
            },
        )

        self.assertEqual(response.status_code, 200)
        book = self.client.get("/books").json()["results"][0]
        self.assertEqual(book["ISBN/UID"], "9780441172719")
        self.assertEqual(book["Authors"], "Frank Herbert")
        self.assertEqual(book["Total Pages"], 592)
        self.assertIsNone(book["Description"])
        self.assertIsNone(book["Subjects"])
        self.assertIsNone(book["Genres"])
        self.assertIsNone(book["First Publish Year"])
        self.assertIsNone(book["metadata_source"])
        self.assertIsNone(book["metadata_enriched_at"])
        mock_lookup_open_library_by_isbn.assert_not_called()
        mock_lookup_google_books_by_isbn.assert_not_called()

    @patch(
        "backend.services.page_lookup.lookup_google_books_by_isbn",
        side_effect=GoogleBooksRateLimited("rate limited"),
    )
    @patch(
        "backend.services.page_lookup.lookup_open_library_by_isbn",
        side_effect=OpenLibraryTimeout("timeout"),
    )
    @patch(
        "backend.services.page_lookup.lookup_open_library_by_title",
        side_effect=RuntimeError("external API should not be called"),
    )
    def test_import_does_not_call_external_lookup_functions(
        self,
        mock_lookup_open_library_by_title,
        mock_lookup_open_library_by_isbn,
        mock_lookup_google_books_by_isbn,
    ):
        response = self.client.post(
            "/books/import",
            json={
                "books": [
                    {"title": "Fast Import", "author": "Author", "ISBN/UID": "9780000000001"}
                ]
            },
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["imported_count"], 1)
        self.assertEqual(payload["enriched_count"], 0)
        self.assertEqual(payload["enrichment_failed_count"], 0)
        self.assertEqual(payload["enrichment_skipped_count"], 0)
        mock_lookup_open_library_by_title.assert_not_called()
        mock_lookup_open_library_by_isbn.assert_not_called()
        mock_lookup_google_books_by_isbn.assert_not_called()

    @patch("backend.services.page_lookup.lookup_google_books_by_isbn")
    @patch("backend.services.page_lookup.lookup_open_library_by_isbn")
    def test_import_with_isbns_completes_without_enrichment(
        self, mock_lookup_open_library_by_isbn, mock_lookup_google_books_by_isbn
    ):
        response = self.client.post(
            "/books/import",
            json={
                "books": [
                    {"title": f"ISBN Book {i}", "ISBN/UID": f"978000000000{i}"}
                    for i in range(3)
                ]
            },
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["imported_count"], 3)
        self.assertEqual(payload["enriched_count"], 0)
        self.assertEqual(payload["enrichment_failed_count"], 0)
        mock_lookup_google_books_by_isbn.assert_not_called()
        mock_lookup_open_library_by_isbn.assert_not_called()

    @patch("backend.services.page_lookup.lookup_open_library_by_title")
    def test_import_unknown_author_does_not_lookup(
        self, mock_lookup_open_library_by_title
    ):
        response = self.client.post(
            "/books/import",
            json={"books": [{"title": "Dune", "author": "Unknown"}]},
        )

        self.assertEqual(response.status_code, 200)
        book = self.client.get("/books").json()["results"][0]
        self.assertEqual(book["Authors"], "Unknown")
        self.assertIsNone(book["Total Pages"])
        mock_lookup_open_library_by_title.assert_not_called()

    @patch("backend.services.page_lookup.lookup_open_library_by_title", side_effect=RuntimeError("boom"))
    def test_import_does_not_crash_when_external_api_is_down(
        self, mock_lookup_open_library_by_title
    ):
        response = self.client.post(
            "/books/import",
            json={"books": [{"title": "Dune", "read_status": "To Read"}]},
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["imported_count"], 1)
        self.assertEqual(response.json()["skipped_duplicates"], 0)
        self.assertEqual(response.json()["enrichment_failed_count"], 0)

        book = self.client.get("/books").json()["results"][0]
        self.assertEqual(book["Title"], "Dune")
        self.assertEqual(book["Authors"], "Unknown")
        self.assertIsNone(book["Total Pages"])
        mock_lookup_open_library_by_title.assert_not_called()

    @patch("backend.services.page_lookup.lookup_open_library_by_title")
    def test_bulk_import_does_not_lookup_metadata(
        self,
        mock_lookup_open_library_by_title,
    ):
        response = self.client.post(
            "/books/import",
            json={
                "books": [
                    {"title": f"Bulk Book {i}", "author": "Author"}
                    for i in range(100)
                ]
            },
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["imported_count"], 100)
        self.assertEqual(payload["enriched_count"], 0)
        self.assertEqual(payload["enrichment_skipped_count"], 0)
        self.assertEqual(payload["enrichment_failed_count"], 0)
        mock_lookup_open_library_by_title.assert_not_called()
        self.mock_page_count_http_get.assert_not_called()

    @patch("backend.services.page_lookup.lookup_open_library_by_title", return_value=None)
    def test_import_normalizes_read_to_completed(self, mock_lookup_open_library_by_title):
        response = self.client.post(
            "/books/import",
            json={"books": [{"title": "Read Book", "author": "A", "Read Status": "Read"}]},
        )

        self.assertEqual(response.status_code, 200)
        payload = self.client.get("/books").json()
        book = payload["results"][0]
        self.assertEqual(book["Read Status"], "read")
        self.assertEqual(book["Progress (%)"], 100)
        mock_lookup_open_library_by_title.assert_not_called()

    @patch("backend.services.page_lookup.lookup_open_library_by_title", return_value=None)
    def test_import_stores_last_date_read_from_slash_date(self, mock_lookup_open_library_by_title):
        response = self.client.post(
            "/books/import",
            json={
                "books": [
                    {
                        "title": "Dated Book",
                        "author": "A",
                        "Read Status": "Read",
                        "Last Date Read": "2025/02/02",
                    }
                ]
            },
        )

        self.assertEqual(response.status_code, 200)
        book = self.client.get("/books").json()["results"][0]
        self.assertEqual(book["Read Status"], "read")
        self.assertEqual(book["Last Date Read"], "2025-02-02")
        mock_lookup_open_library_by_title.assert_not_called()

    @patch("backend.services.page_lookup.lookup_open_library_by_title", return_value=None)
    def test_import_stores_last_date_read_from_us_date(self, mock_lookup_open_library_by_title):
        response = self.client.post(
            "/books/import",
            json={
                "books": [
                    {
                        "title": "US Dated Book",
                        "author": "A",
                        "read_status": "Finished",
                        "last_date_read": "02/03/2025",
                    }
                ]
            },
        )

        self.assertEqual(response.status_code, 200)
        book = self.client.get("/books").json()["results"][0]
        self.assertEqual(book["Read Status"], "read")
        self.assertEqual(book["Last Date Read"], "2025-02-03")
        self.assertEqual(book["End Date"], "2025-02-03")
        mock_lookup_open_library_by_title.assert_not_called()

    @patch("backend.services.page_lookup.lookup_open_library_by_title", return_value=None)
    def test_import_preserves_start_and_end_dates(self, mock_lookup_open_library_by_title):
        response = self.client.post(
            "/books/import",
            json={
                "books": [
                    {
                        "title": "Dated Range",
                        "author": "A",
                        "read_status": "Read",
                        "Start Date": "2026-01-05",
                        "End Date": "01/12/2026",
                    }
                ]
            },
        )

        self.assertEqual(response.status_code, 200)
        book = self.client.get("/books").json()["results"][0]
        self.assertEqual(book["Start Date"], "2026-01-05")
        self.assertEqual(book["End Date"], "2026-01-12")
        mock_lookup_open_library_by_title.assert_not_called()

    @patch("backend.services.page_lookup.lookup_open_library_by_title", return_value=None)
    def test_import_dates_read_range_parses_start_and_end_dates(self, mock_lookup_open_library_by_title):
        response = self.client.post(
            "/books/import",
            json={
                "books": [
                    {
                        "title": "StoryGraph Range",
                        "author": "A",
                        "read_status": "Read",
                        "Dates Read": "2025/01/28-2025/02/02",
                    }
                ]
            },
        )

        self.assertEqual(response.status_code, 200)
        book = self.client.get("/books").json()["results"][0]
        self.assertEqual(book["Start Date"], "2025-01-28")
        self.assertEqual(book["End Date"], "2025-02-02")
        mock_lookup_open_library_by_title.assert_not_called()

    @patch("backend.services.page_lookup.lookup_open_library_by_title", return_value=None)
    def test_import_last_date_read_overrides_dates_read_end(self, mock_lookup_open_library_by_title):
        response = self.client.post(
            "/books/import",
            json={
                "books": [
                    {
                        "title": "Last Date Wins",
                        "author": "A",
                        "read_status": "Read",
                        "Dates Read": "2025/01/28-2025/02/02",
                        "Last Date Read": "2025/02/03",
                    }
                ]
            },
        )

        self.assertEqual(response.status_code, 200)
        book = self.client.get("/books").json()["results"][0]
        self.assertEqual(book["Start Date"], "2025-01-28")
        self.assertEqual(book["End Date"], "2025-02-03")
        self.assertEqual(book["Last Date Read"], "2025-02-03")
        mock_lookup_open_library_by_title.assert_not_called()

    @patch("backend.services.page_lookup.lookup_open_library_by_title", return_value=None)
    def test_import_explicit_start_date_overrides_dates_read_start(self, mock_lookup_open_library_by_title):
        response = self.client.post(
            "/books/import",
            json={
                "books": [
                    {
                        "title": "Explicit Start Wins",
                        "author": "A",
                        "read_status": "Read",
                        "start_date": "2025-01-30",
                        "Dates Read": "2025/01/28-2025/02/02",
                    }
                ]
            },
        )

        self.assertEqual(response.status_code, 200)
        book = self.client.get("/books").json()["results"][0]
        self.assertEqual(book["Start Date"], "2025-01-30")
        self.assertEqual(book["End Date"], "2025-02-02")
        mock_lookup_open_library_by_title.assert_not_called()

    @patch("backend.services.page_lookup.lookup_open_library_by_title", return_value=None)
    def test_import_empty_dates_read_leaves_dates_null(self, mock_lookup_open_library_by_title):
        response = self.client.post(
            "/books/import",
            json={"books": [{"title": "Empty Dates Read", "author": "A", "read_status": "Read", "Dates Read": ""}]},
        )

        self.assertEqual(response.status_code, 200)
        book = self.client.get("/books").json()["results"][0]
        self.assertIsNone(book["Start Date"])
        self.assertIsNone(book["End Date"])
        mock_lookup_open_library_by_title.assert_not_called()

    @patch("backend.services.page_lookup.lookup_open_library_by_title", return_value=None)
    def test_import_to_read_empty_dates_read_leaves_dates_null(self, mock_lookup_open_library_by_title):
        response = self.client.post(
            "/books/import",
            json={"books": [{"title": "Unread Dates Read", "author": "A", "read_status": "To Read", "Dates Read": ""}]},
        )

        self.assertEqual(response.status_code, 200)
        book = self.client.get("/books").json()["results"][0]
        self.assertIsNone(book["Start Date"])
        self.assertIsNone(book["End Date"])
        mock_lookup_open_library_by_title.assert_not_called()

    @patch("backend.services.page_lookup.lookup_open_library_by_title", return_value=None)
    def test_import_dates_read_parses_dash_and_slash_formats(self, mock_lookup_open_library_by_title):
        response = self.client.post(
            "/books/import",
            json={
                "books": [
                    {
                        "title": "Dash Dates",
                        "author": "A",
                        "read_status": "Read",
                        "dates_read": "2025-10-01-2025-10-07",
                    },
                    {
                        "title": "Single Slash Date",
                        "author": "A",
                        "read_status": "Read",
                        "Dates read": "2025/10/07",
                    },
                ]
            },
        )

        self.assertEqual(response.status_code, 200)
        books = {row["Title"]: row for row in self.client.get("/books?limit=100").json()["results"]}
        self.assertEqual(books["Dash Dates"]["Start Date"], "2025-10-01")
        self.assertEqual(books["Dash Dates"]["End Date"], "2025-10-07")
        self.assertEqual(books["Single Slash Date"]["Start Date"], "2025-10-07")
        self.assertEqual(books["Single Slash Date"]["End Date"], "2025-10-07")
        mock_lookup_open_library_by_title.assert_not_called()

    @patch("backend.services.page_lookup.lookup_open_library_by_title", return_value=None)
    def test_import_accepts_blank_reading_dates(self, mock_lookup_open_library_by_title):
        response = self.client.post(
            "/books/import",
            json={
                "books": [
                    {
                        "title": "Blank Dates",
                        "author": "A",
                        "read_status": "To Read",
                        "Start Date": "",
                        "End Date": "",
                    }
                ]
            },
        )

        self.assertEqual(response.status_code, 200)
        book = self.client.get("/books").json()["results"][0]
        self.assertIsNone(book["Start Date"])
        self.assertIsNone(book["End Date"])
        mock_lookup_open_library_by_title.assert_not_called()

    @patch("backend.services.page_lookup.lookup_open_library_by_title", return_value=None)
    def test_import_accepts_date_started_alias(self, mock_lookup_open_library_by_title):
        response = self.client.post(
            "/books/import",
            json={"books": [{"title": "Started Alias", "author": "A", "date_started": "2026-01-05"}]},
        )

        self.assertEqual(response.status_code, 200)
        book = self.client.get("/books").json()["results"][0]
        self.assertEqual(book["Start Date"], "2026-01-05")
        mock_lookup_open_library_by_title.assert_not_called()

    @patch("backend.services.page_lookup.lookup_open_library_by_title", return_value=None)
    def test_import_accepts_finish_date_aliases(self, mock_lookup_open_library_by_title):
        response = self.client.post(
            "/books/import",
            json={
                "books": [
                    {"title": "Finish Alias", "author": "A", "status": "Completed", "finish_date": "2026-01-12"},
                    {
                        "title": "Date Finished Alias",
                        "author": "A",
                        "status": "Completed",
                        "date_finished": "2026-02-03",
                    },
                ]
            },
        )

        self.assertEqual(response.status_code, 200)
        books = {row["Title"]: row for row in self.client.get("/books?limit=100").json()["results"]}
        self.assertEqual(books["Finish Alias"]["End Date"], "2026-01-12")
        self.assertEqual(books["Date Finished Alias"]["End Date"], "2026-02-03")
        mock_lookup_open_library_by_title.assert_not_called()

    @patch("backend.services.page_lookup.lookup_open_library_by_title", return_value=None)
    def test_import_tracking_mode(self, mock_lookup_open_library_by_title):
        response = self.client.post(
            "/books/import",
            json={
                "books": [
                    {
                        "title": "Imported Mode",
                        "author": "A",
                        "total_pages": 300,
                        "tracking_mode": "percentage",
                    }
                ]
            },
        )

        self.assertEqual(response.status_code, 200)
        book = self.client.get("/books").json()["results"][0]
        self.assertEqual(book["tracking_mode"], "percentage")
        self.assertEqual(book["Tracking Mode"], "percentage")
        mock_lookup_open_library_by_title.assert_not_called()

    @patch("backend.services.page_lookup.lookup_open_library_by_title", return_value=None)
    def test_import_infers_tracking_mode_when_missing(self, mock_lookup_open_library_by_title):
        response = self.client.post(
            "/books/import",
            json={
                "books": [
                    {"title": "Imported Pages Mode", "author": "A", "total_pages": 300},
                    {"title": "Imported Percentage Mode", "author": "A"},
                ]
            },
        )

        self.assertEqual(response.status_code, 200)
        books = {row["Title"]: row for row in self.client.get("/books?limit=100").json()["results"]}
        self.assertEqual(books["Imported Pages Mode"]["tracking_mode"], "pages")
        self.assertEqual(books["Imported Percentage Mode"]["tracking_mode"], "percentage")
        mock_lookup_open_library_by_title.assert_not_called()

    @patch("backend.services.page_lookup.lookup_open_library_by_title", return_value=None)
    def test_import_rejects_start_date_after_end_date(self, mock_lookup_open_library_by_title):
        response = self.client.post(
            "/books/import",
            json={
                "books": [
                    {
                        "title": "Bad Dates",
                        "author": "A",
                        "read_status": "Read",
                        "start_date": "2026-02-01",
                        "end_date": "2026-01-01",
                    }
                ]
            },
        )

        self.assertEqual(response.status_code, 400)
        mock_lookup_open_library_by_title.assert_not_called()

    @patch("backend.services.page_lookup.lookup_open_library_by_title", return_value=None)
    def test_import_normalizes_completed_to_completed(self, mock_lookup_open_library_by_title):
        response = self.client.post(
            "/books/import",
            json={
                "books": [
                    {
                        "title": "Completed Book",
                        "author": "A",
                        "status": "Completed",
                        "total_pages": 321,
                    }
                ]
            },
        )

        self.assertEqual(response.status_code, 200)
        book = self.client.get("/books").json()["results"][0]
        self.assertEqual(book["Read Status"], "read")
        self.assertEqual(book["Pages Read"], 321)
        self.assertEqual(book["Progress (%)"], 100)
        mock_lookup_open_library_by_title.assert_not_called()

    def test_import_completed_without_total_pages_does_not_crash(self):
        response = self.client.post(
            "/books/import",
            json={"books": [{"title": "Completed No Pages", "author": "A", "status": "Completed"}]},
        )

        self.assertEqual(response.status_code, 200)
        book = self.client.get("/books").json()["results"][0]
        self.assertEqual(book["Read Status"], "read")
        self.assertEqual(book["Pages Read"], 0)
        self.assertEqual(book["Progress (%)"], 100)

    @patch("backend.services.page_lookup.lookup_open_library_by_title", return_value=None)
    def test_import_normalizes_finished_to_completed(self, mock_lookup_open_library_by_title):
        response = self.client.post(
            "/books/import",
            json={"books": [{"title": "Finished Book", "author": "A", "read_status": "Finished"}]},
        )

        self.assertEqual(response.status_code, 200)
        book = self.client.get("/books").json()["results"][0]
        self.assertEqual(book["Read Status"], "read")
        self.assertEqual(book["Progress (%)"], 100)
        mock_lookup_open_library_by_title.assert_not_called()

    @patch("backend.services.page_lookup.lookup_open_library_by_title")
    def test_import_normalizes_reading_to_reading(self, mock_lookup_open_library_by_title):
        response = self.client.post(
            "/books/import",
            json={
                "books": [
                    {
                        "title": "Reading Book",
                        "author": "A",
                        "read_status": "Reading",
                        "pages_read": 75,
                        "total_pages": 300,
                    }
                ]
            },
        )

        self.assertEqual(response.status_code, 200)
        book = self.client.get("/books").json()["results"][0]
        self.assertEqual(book["Read Status"], "to-read")
        self.assertEqual(book["Pages Read"], 75)
        self.assertEqual(book["Total Pages"], 300)
        self.assertEqual(book["Progress (%)"], 25)
        mock_lookup_open_library_by_title.assert_not_called()

    @patch("backend.services.page_lookup.lookup_open_library_by_title", return_value=None)
    def test_import_normalizes_to_read_to_not_started(self, mock_lookup_open_library_by_title):
        response = self.client.post(
            "/books/import",
            json={"books": [{"title": "Unread Book", "author": "A", "Read Status": "To Read"}]},
        )

        self.assertEqual(response.status_code, 200)
        book = self.client.get("/books").json()["results"][0]
        self.assertEqual(book["Read Status"], "to-read")
        self.assertEqual(book["Pages Read"], 0)
        self.assertEqual(book["Progress (%)"], 0)
        mock_lookup_open_library_by_title.assert_not_called()

    def test_import_to_read_defaults_to_zero_progress(self):
        response = self.client.post(
            "/books/import",
            json={"books": [{"title": "Default TBR", "author": "A", "read_status": "Unread", "total_pages": 250}]},
        )

        self.assertEqual(response.status_code, 200)
        book = self.client.get("/books").json()["results"][0]
        self.assertEqual(book["Read Status"], "to-read")
        self.assertEqual(book["Pages Read"], 0)
        self.assertEqual(book["Progress (%)"], 0)

    @patch("backend.services.page_lookup.lookup_open_library_by_title")
    def test_import_missing_page_count_stays_empty(self, mock_lookup_open_library_by_title):
        response = self.client.post(
            "/books/import",
            json={"books": [{"title": "Needs Pages", "author": "A"}]},
        )

        self.assertEqual(response.status_code, 200)
        book = self.client.get("/books").json()["results"][0]
        self.assertIsNone(book["Total Pages"])
        mock_lookup_open_library_by_title.assert_not_called()

    @patch("backend.services.page_lookup.lookup_open_library_by_title", return_value=None)
    def test_import_without_page_count_does_not_lookup(self, mock_lookup_open_library_by_title):
        response = self.client.post(
            "/books/import",
            json={"books": [{"title": "No Pages Found", "author": "A"}]},
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["imported_count"], 1)
        self.assertEqual(response.json()["skipped_duplicates"], 0)
        self.assertEqual(response.json()["enrichment_failed_count"], 0)
        book = self.client.get("/books").json()["results"][0]
        self.assertIsNone(book["Total Pages"])
        mock_lookup_open_library_by_title.assert_not_called()

    def test_metadata_status_counts_current_user_genres(self):
        _seed_profile(
            user_id=OTHER_USER_ID,
            email="other@shelftxt.local",
            username="other",
        )
        _seed_book(title="With Genre", authors="A", isbn_uid="with-genre", genres=["fiction"])
        _seed_book(title="Without Genre", authors="A", isbn_uid="without-genre")
        _seed_book(
            title="Other Genre",
            authors="B",
            isbn_uid="other-genre",
            user_id=OTHER_USER_ID,
            genres=["history"],
        )

        response = self.client.get("/metadata/status")

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["books_with_genres"], 1)
        self.assertEqual(payload["total_books"], 2)
        self.assertEqual(payload["job"]["status"], "completed")

    @patch("backend.routes.metadata.process_metadata_job")
    def test_metadata_generate_processes_job_before_returning(self, mock_process_metadata_job):
        _seed_book(title="Needs Genre", authors="A", isbn_uid="needs-genre")
        _seed_book(title="Has Genre", authors="A", isbn_uid="has-genre", genres=["fiction"])

        def complete_job(job_id):
            db = TestingSessionLocal()
            try:
                job = db.get(MetadataJob, job_id)
                job.status = "completed"
                job.processed_count = job.total_count
                job.completed_at = datetime.now(timezone.utc)
                db.commit()
            finally:
                db.close()

        mock_process_metadata_job.side_effect = complete_job

        response = self.client.post("/metadata/generate")

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["books_with_genres"], 1)
        self.assertEqual(payload["total_books"], 2)
        self.assertEqual(payload["job"]["status"], "completed")
        self.assertEqual(payload["job"]["processed_count"], 1)
        self.assertEqual(payload["job"]["total_count"], 1)
        mock_process_metadata_job.assert_called_once()

    def test_metadata_status_marks_stuck_processing_job_failed(self):
        _seed_book(title="Needs Genre", authors="A", isbn_uid="needs-genre")
        stale_time = datetime.now(timezone.utc) - timedelta(hours=2)

        db = TestingSessionLocal()
        try:
            job = MetadataJob(
                user_id=TEST_USER_ID,
                status="processing",
                processed_count=0,
                total_count=1,
                updated_at=stale_time,
            )
            db.add(job)
            db.commit()
            job_id = job.id
        finally:
            db.close()

        response = self.client.get("/metadata/status")

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["job"]["status"], "failed")

        db = TestingSessionLocal()
        try:
            job = db.get(MetadataJob, job_id)
            self.assertEqual(job.status, "failed")
            self.assertIn("stale", job.error_message)
        finally:
            db.close()

    @patch("backend.services.metadata_jobs.get_session_local", return_value=TestingSessionLocal)
    @patch("backend.services.metadata_jobs.resolve_book")
    def test_metadata_job_processes_only_current_user_missing_genres(self, mock_lookup, _mock_session):
        _seed_profile(
            user_id=OTHER_USER_ID,
            email="other@shelftxt.local",
            username="other",
        )
        current = _seed_book(title="Needs Genre", authors="A", isbn_uid="needs-genre")
        _seed_book(title="Already Done", authors="A", isbn_uid="has-genre", genres=["fiction"])
        other = _seed_book(
            title="Other Missing",
            authors="B",
            isbn_uid="other-missing",
            user_id=OTHER_USER_ID,
        )
        from backend.services.book_resolver import CanonicalBook

        mock_lookup.return_value = CanonicalBook(
            title="Needs Genre",
            genres=("science fiction",),
            source="open_library",
        )

        db = TestingSessionLocal()
        try:
            job = MetadataJob(user_id=TEST_USER_ID, status="pending", total_count=1)
            db.add(job)
            db.commit()
            job_id = job.id
        finally:
            db.close()

        from backend.services.metadata_jobs import process_metadata_job

        process_metadata_job(job_id)

        db = TestingSessionLocal()
        try:
            updated_current = db.get(Book, current.id)
            untouched_other = db.get(Book, other.id)
            completed_job = db.get(MetadataJob, job_id)
            self.assertEqual(updated_current.genres, ["science fiction"])
            self.assertIsNone(untouched_other.genres)
            self.assertEqual(completed_job.status, "completed")
            self.assertEqual(completed_job.processed_count, 1)
        finally:
            db.close()

    def test_export_library_csv(self):
        _seed_book(
            title="Export Me",
            authors="Author",
            isbn_uid="1",
            total_pages=100,
        )

        response = self.client.get("/books/export")

        self.assertEqual(response.status_code, 200)
        self.assertIn("text/csv", response.headers.get("content-type", ""))
        self.assertIn("Export Me", response.text)
        self.assertIn("Author", response.text)
        self.assertIn("ISBN/UID", response.text)
        self.assertIn("Start Date", response.text)
        self.assertIn("End Date", response.text)
        self.assertIn("start_date", response.text)
        self.assertIn("end_date", response.text)
        self.assertIn("tracking_mode", response.text)

    @patch("backend.services.page_lookup.lookup_open_library_by_title", return_value=None)
    def test_export_import_round_trip_preserves_reading_dates(self, mock_lookup_open_library_by_title):
        _seed_book(
            title="Round Trip",
            authors="Author",
            isbn_uid="round-trip",
            read_status="read",
            start_date="2026-01-05",
            end_date="2026-01-12",
            last_date_read="2026-01-12",
            total_pages=100,
        )

        exported = self.client.get("/books/export")
        self.assertEqual(exported.status_code, 200)
        self.client.post("/books/clear", json={"confirm": True})

        import csv
        from io import StringIO

        rows = list(csv.DictReader(StringIO(exported.text)))
        response = self.client.post("/books/import", json={"books": rows})

        self.assertEqual(response.status_code, 200)
        book = self.client.get("/books").json()["results"][0]
        self.assertEqual(book["Start Date"], "2026-01-05")
        self.assertEqual(book["End Date"], "2026-01-12")
        mock_lookup_open_library_by_title.assert_not_called()

    def test_export_only_exports_current_user_books(self):
        _seed_profile(
            user_id=OTHER_USER_ID,
            email="other@shelftxt.local",
            username="other",
        )

        _seed_book(title="Mine", authors="A", isbn_uid="mine")
        _seed_book(
            title="Not Mine",
            authors="B",
            isbn_uid="not-mine",
            user_id=OTHER_USER_ID,
        )

        response = self.client.get("/books/export")

        self.assertEqual(response.status_code, 200)
        self.assertIn("Mine", response.text)
        self.assertNotIn("Not Mine", response.text)

    @patch("backend.routes.recommendation.get_recommendation")
    def test_recommend_returns_structured_payload(self, mock_get_recommendation):
        mock_get_recommendation.return_value = [
            {
                "recommended_book": {
                    "id": "1",
                    "title": "Snow Crash",
                    "author": "Neal Stephenson",
                },
                "book": {
                    "id": "1",
                    "title": "Snow Crash",
                    "author": "Neal Stephenson",
                },
                "score": 0.93,
                "reason": "Shares cyberpunk with Neuromancer, which you rated 5★.",
                "explanation": "Recommended because you rated Neal Stephenson highly.",
                "matched_genres": ["cyberpunk"],
                "matched_subjects": [],
                "matched_authors": ["Neal Stephenson"],
                "matched_liked_books": [
                    {"id": "2", "title": "Cryptonomicon", "author": "Neal Stephenson", "rating": 5}
                ],
                "score_breakdown": {"overall": 0.93},
                "similar_books": [
                    {"id": "2", "title": "Cryptonomicon", "author": "Neal Stephenson"}
                ],
            }
        ]

        response = self.client.get("/recommend")

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertIsInstance(payload, list)
        self.assertEqual(payload[0]["book"]["title"], "Snow Crash")
        self.assertEqual(payload[0]["recommended_book"]["title"], "Snow Crash")
        self.assertIn("reason", payload[0])
        self.assertEqual(payload[0]["matched_genres"], ["cyberpunk"])
        self.assertEqual(payload[0]["matched_liked_books"][0]["title"], "Cryptonomicon")
        self.assertIn("explanation", payload[0])
        self.assertIn("similar_books", payload[0])

        self.assertEqual(mock_get_recommendation.call_count, 1)
        self.assertEqual(mock_get_recommendation.call_args.args[1], TEST_USER_ID)
        self.assertEqual(mock_get_recommendation.call_args.kwargs["style"], "balanced")
        self.assertEqual(mock_get_recommendation.call_args.kwargs["refresh"], False)
        self.assertEqual(mock_get_recommendation.call_args.kwargs["exclude_ids"], set())

    @patch("backend.routes.recommendation.get_recommendation")
    def test_recommend_refresh_passes_refresh_flag(self, mock_get_recommendation):
        mock_get_recommendation.return_value = []

        response = self.client.get("/recommend?style=balanced&refresh=true&exclude_ids=1,2,,3")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(mock_get_recommendation.call_count, 1)
        self.assertEqual(mock_get_recommendation.call_args.kwargs["refresh"], True)
        self.assertEqual(mock_get_recommendation.call_args.kwargs["exclude_ids"], {"1", "2", "3"})

    @patch("backend.routes.recommendation.get_recommendation")
    def test_recommend_returns_empty_when_no_pick(self, mock_get_recommendation):
        mock_get_recommendation.return_value = []

        response = self.client.get("/recommend")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), [])

        self.assertEqual(mock_get_recommendation.call_count, 1)
        self.assertEqual(mock_get_recommendation.call_args.args[1], TEST_USER_ID)
        self.assertEqual(mock_get_recommendation.call_args.kwargs["style"], "balanced")

    def test_recommendation_empty_state_returns_empty_list(self):
        db = TestingSessionLocal()
        try:
            result = get_recommendation(
                db,
                TEST_USER_ID,
                style="balanced",
            )
        finally:
            db.close()

        self.assertEqual(result, [])

    def test_recommendation_only_uses_current_user_books(self):
        _seed_profile(
            user_id=OTHER_USER_ID,
            email="other@shelftxt.local",
            username="other",
        )

        _seed_book(
            title="Other User Read Anchor",
            authors="Other Author",
            isbn_uid="other-read-anchor",
            user_id=OTHER_USER_ID,
            read_status="read",
            star_rating=5,
            genres=["science fiction"],
            subjects=["space"],
            total_pages=300,
        )
        _seed_book(
            title="Other User Candidate",
            authors="Other Author",
            isbn_uid="other-candidate",
            user_id=OTHER_USER_ID,
            read_status="to-read",
            genres=["science fiction"],
            subjects=["space"],
            total_pages=300,
        )
        _seed_book(
            title="My Candidate",
            authors="Mine",
            isbn_uid="my-candidate",
            read_status="to-read",
            genres=["science fiction"],
            subjects=["space"],
            total_pages=300,
        )

        db = TestingSessionLocal()
        try:
            result = get_recommendation(
                db,
                TEST_USER_ID,
                style="balanced",
            )
        finally:
            db.close()

        self.assertEqual([item["book"]["title"] for item in result], ["My Candidate"])
        self.assertEqual(result[0]["matched_liked_books"], [])

    def test_recommendation_falls_back_when_metadata_is_missing(self):
        _seed_book(
            title="Rated Book",
            authors="Author A",
            isbn_uid="rated-book",
            read_status="read",
            star_rating=4.5,
            total_pages=300,
        )
        _seed_book(
            title="Candidate Book",
            authors="Author B",
            isbn_uid="candidate-book",
            read_status="to-read",
            total_pages=250,
        )

        db = TestingSessionLocal()
        try:
            result = get_recommendation(db, TEST_USER_ID, style="balanced")
        finally:
            db.close()

        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["book"]["title"], "Candidate Book")
        self.assertEqual(result[0]["recommended_book"]["title"], "Candidate Book")
        self.assertIn("reason", result[0])
        self.assertEqual(
            result[0]["reason"],
            "Genre metadata has not been generated yet, so this uses rating and author signals only.",
        )

    def test_recommend_endpoint_does_not_trigger_external_or_background_work(self):
        _seed_book(
            title="Read Book",
            authors="Author",
            isbn_uid="read-book",
            read_status="read",
            star_rating=5,
            total_pages=300,
            subjects=["space"],
            genres=["science fiction"],
        )
        _seed_book(
            title="Unread Book",
            authors="Author",
            isbn_uid="unread-book",
            read_status="to-read",
            total_pages=250,
            subjects=["space"],
            genres=["science fiction"],
        )

        with self.external_work_guard():
            response = self.client.get("/recommend?refresh=true")

        self.assertEqual(response.status_code, 200)
        self.assertIsInstance(response.json(), list)

    @patch(
        "backend.services.page_lookup.httpx.get",
        side_effect=AssertionError("metadata HTTP call in recommendation test"),
    )
    @patch(
        "backend.services.page_count_lookup.httpx.get",
        side_effect=AssertionError("page-count HTTP call in recommendation test"),
    )
    @patch(
        "backend.services.page_count_lookup.backfill_missing_page_counts",
        side_effect=AssertionError("background backfill in recommendation test"),
    )
    def test_recommendation_provider_failure_does_not_trigger_backfill_or_break_library_results(
        self,
        mock_backfill,
        mock_page_count_http,
        mock_metadata_http,
    ):
        _seed_book(
            title="Read Book",
            authors="Author",
            isbn_uid="read-book",
            read_status="read",
            star_rating=5,
            total_pages=300,
            subjects=["space"],
            genres=["science fiction"],
        )
        _seed_book(
            title="Unread Book",
            authors="Author",
            isbn_uid="unread-book",
            read_status="to-read",
            total_pages=250,
            subjects=["space"],
            genres=["science fiction"],
        )

        db = TestingSessionLocal()
        try:
            result = get_recommendation(db, TEST_USER_ID, style="balanced")
        finally:
            db.close()

        self.assertGreaterEqual(len(result), 1)
        mock_backfill.assert_not_called()
        mock_page_count_http.assert_not_called()
        self.assertGreater(mock_metadata_http.call_count, 0)
        self.assertTrue(all(item["in_library"] for item in result))

    def test_recommendation_recomputes_after_book_status_and_rating_change(self):
        anna = _seed_book(
            title="Anna Karenina",
            authors="Leo Tolstoy",
            isbn_uid="9780345803924",
            read_status="to-read",
            star_rating=None,
            genres=["Drama", "Romance", "Classic"],
            subjects=["Adultery", "Married Women", "Russian Literature"],
            total_pages=864,
        )
        _seed_book(
            title="The Scarlet Letter",
            authors="Nathaniel Hawthorne",
            isbn_uid="scarlet-letter",
            read_status="to-read",
            genres=["Drama", "Romance", "Classic"],
            subjects=["Adultery", "Married Women"],
            total_pages=272,
        )

        db = TestingSessionLocal()
        try:
            before = get_recommendation(db, TEST_USER_ID, style="balanced")
            self.assertTrue(before)
            self.assertEqual(before[0]["matched_liked_books"], [])

            book = db.query(Book).filter(Book.id == anna.id).one()
            book.read_status = "read"
            book.star_rating = 4.75
            book.end_date = date(2026, 7, 1)
            book.pages_read = 864
            book.progress_percent = 100
            db.commit()

            after = get_recommendation(db, TEST_USER_ID, style="balanced", refresh=True)
        finally:
            db.close()

        scarlet = next(item for item in after if item["book"]["title"] == "The Scarlet Letter")
        self.assertIn(
            "Anna Karenina",
            [book["title"] for book in scarlet["matched_liked_books"]],
        )

    @patch("backend.services.postgres_books.lookup_page_count_result")
    def test_find_pages_updates_missing_total_without_overwriting(self, mock_lookup):
        _seed_book(title="Missing Pages", authors="A", isbn_uid="missing-pages")
        mock_lookup.return_value = PageCountResult(321, "median_title_author", 3)

        response = self.client.post("/books/missing-pages/pages/lookup")

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()["found"])
        self.assertEqual(response.json()["book"]["Total Pages"], 321)
        self.assertEqual(response.json()["source"], "median_title_author")

        db = TestingSessionLocal()
        try:
            book = db.query(Book).filter(Book.isbn_uid == "missing-pages").one()
            self.assertEqual(book.total_pages, 321)
            self.assertEqual(book.page_count_source, "median_title_author")
        finally:
            db.close()

    @patch("backend.services.postgres_books.lookup_page_count_result")
    def test_find_pages_preserves_existing_total(self, mock_lookup):
        _seed_book(
            title="User Pages",
            authors="A",
            isbn_uid="user-pages",
            total_pages=444,
        )

        response = self.client.post("/books/user-pages/pages/lookup")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["book"]["Total Pages"], 444)
        mock_lookup.assert_not_called()

    @patch("backend.services.postgres_books.backfill_missing_page_counts", return_value=1)
    def test_bulk_page_backfill_reports_results(self, mock_backfill):
        _seed_book(title="Missing One", authors="A", isbn_uid="missing-one")
        _seed_book(title="Missing Two", authors="A", isbn_uid="missing-two")

        response = self.client.post("/books/pages/backfill?limit=50")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.json(),
            {"processed": 2, "updated": 1, "unresolved": 1},
        )
        mock_backfill.assert_called_once_with(
            ANY,
            limit=50,
            user_id=TEST_USER_ID,
        )


if __name__ == "__main__":
    unittest.main()
