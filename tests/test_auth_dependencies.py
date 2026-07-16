import logging
import time
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import patch

import pytest
from fastapi import HTTPException
from fastapi.security import HTTPAuthorizationCredentials
from starlette.requests import Request

from backend.auth.dependencies import _user_from_token, get_current_user
from backend.db.database import Base
from tests.test_api import TEST_USER_ID, TestingSessionLocal, _seed_profile, engine


class FakeResponse:
    def __init__(self, status_code, payload=None):
        self.status_code = status_code
        self._payload = payload or {}

    def json(self):
        return self._payload


def _request() -> Request:
    return Request(
        {
            "type": "http",
            "method": "GET",
            "path": "/books",
            "headers": [(b"authorization", b"Bearer user-token")],
        }
    )


def _credentials() -> HTTPAuthorizationCredentials:
    return HTTPAuthorizationCredentials(scheme="Bearer", credentials="user-token")


@pytest.fixture(autouse=True)
def reset_db():
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    _seed_profile()


def test_user_token_validation_uses_anon_key_as_apikey():
    db = TestingSessionLocal()
    env = {
        "SUPABASE_URL": "https://project.supabase.co",
        "SUPABASE_ANON_KEY": "anon-key",
        "SUPABASE_SERVICE_ROLE_KEY": "service-role-key",
    }
    with patch.dict("os.environ", env, clear=False), patch(
        "backend.auth.dependencies.httpx.get",
        return_value=FakeResponse(200, {"id": str(TEST_USER_ID)}),
    ) as mock_get:
        try:
            profile = get_current_user(_request(), _credentials(), db)
        finally:
            db.close()

    assert profile.id == TEST_USER_ID
    headers = mock_get.call_args.kwargs["headers"]
    assert headers["Authorization"] == "Bearer user-token"
    assert headers["apikey"] == "anon-key"
    assert headers["apikey"] != "service-role-key"


def test_service_role_key_is_not_used_as_user_validation_apikey():
    db = TestingSessionLocal()
    env = {
        "SUPABASE_URL": "https://project.supabase.co",
        "SUPABASE_ANON_KEY": "anon-key",
        "SUPABASE_SERVICE_ROLE_KEY": "service-role-key",
    }
    with patch.dict("os.environ", env, clear=False), patch(
        "backend.auth.dependencies.httpx.get",
        return_value=FakeResponse(200, {"id": str(TEST_USER_ID)}),
    ) as mock_get:
        try:
            get_current_user(_request(), _credentials(), db)
        finally:
            db.close()

    assert mock_get.call_args.kwargs["headers"]["apikey"] == "anon-key"


def test_token_validation_is_cached_briefly():
    env = {
        "SUPABASE_URL": "https://project.supabase.co",
        "SUPABASE_ANON_KEY": "anon-key",
    }
    with patch.dict("os.environ", env, clear=False), patch(
        "backend.auth.dependencies.httpx.get",
        return_value=FakeResponse(200, {"id": str(TEST_USER_ID), "email": "reader@example.com"}),
    ) as mock_get:
        assert _user_from_token("cached-token") == (str(TEST_USER_ID), "reader@example.com", 200)
        assert _user_from_token("cached-token") == (str(TEST_USER_ID), "reader@example.com", 200)

    assert mock_get.call_count == 1


def test_concurrent_token_validation_is_deduplicated():
    env = {
        "SUPABASE_URL": "https://project.supabase.co",
        "SUPABASE_ANON_KEY": "anon-key",
    }

    def slow_response(*_args, **_kwargs):
        time.sleep(0.05)
        return FakeResponse(200, {"id": str(TEST_USER_ID), "email": "reader@example.com"})

    with patch.dict("os.environ", env, clear=False), patch(
        "backend.auth.dependencies.httpx.get",
        side_effect=slow_response,
    ) as mock_get:
        with ThreadPoolExecutor(max_workers=4) as executor:
            results = list(executor.map(_user_from_token, ["shared-token"] * 4))

    assert results == [(str(TEST_USER_ID), "reader@example.com", 200)] * 4
    assert mock_get.call_count == 1


def test_supabase_403_becomes_401_with_safe_local_debug_log(caplog):
    db = TestingSessionLocal()
    env = {
        "SUPABASE_URL": "https://project.supabase.co",
        "SUPABASE_ANON_KEY": "anon-key",
        "SUPABASE_SERVICE_ROLE_KEY": "service-role-key",
    }
    with patch.dict("os.environ", env, clear=False), patch(
        "backend.auth.dependencies.is_local_env",
        return_value=True,
    ), patch(
        "backend.auth.dependencies.httpx.get",
        return_value=FakeResponse(403, {"message": "forbidden"}),
    ):
        caplog.set_level(logging.WARNING, logger="backend.auth.dependencies")
        with pytest.raises(HTTPException) as exc_info:
            try:
                get_current_user(_request(), _credentials(), db)
            finally:
                db.close()

    assert exc_info.value.status_code == 401
    log_text = caplog.text
    assert "auth_header_present=True" in log_text
    assert "supabase_url_present=True" in log_text
    assert "supabase_anon_key_present=True" in log_text
    assert "supabase_service_role_key_present=True" in log_text
    assert "supabase_user_status=403" in log_text
    assert "user-token" not in log_text
    assert "anon-key" not in log_text
    assert "service-role-key" not in log_text
