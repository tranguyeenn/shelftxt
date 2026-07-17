import logging
from unittest.mock import patch

from backend.env import BACKEND_ENV_PATH, ENV_PATH, load_backend_env, log_local_env_presence


def test_backend_env_loader_reads_root_then_backend_env_without_override():
    with patch.dict("os.environ", {}, clear=True), patch("backend.env.load_dotenv") as load_dotenv:
        load_backend_env()

    assert load_dotenv.call_args_list[0].kwargs == {"dotenv_path": ENV_PATH, "override": False}
    assert load_dotenv.call_args_list[1].kwargs == {"dotenv_path": BACKEND_ENV_PATH, "override": False}


def test_env_example_documents_nyt_books_configuration():
    text = (ENV_PATH.parent / ".env.example").read_text()

    assert "NYT_BOOKS_ENABLED=" in text
    assert "NYT_BOOKS_API_URL=" in text
    assert "NYT_BOOKS_API_KEY=" in text
    assert "NYT_BOOKS_TIMEOUT_SECONDS=" in text
    assert "NYT_BOOKS_CACHE_SECONDS=" in text


def test_local_backend_env_aliases_root_vite_supabase_anon_key():
    env = {
        "SUPABASE_URL": "https://project.supabase.co",
        "VITE_SUPABASE_ANON_KEY": "anon-key",
        "SUPABASE_SERVICE_ROLE_KEY": "service-role-key",
        "DATABASE_URL": "postgresql://example",
    }
    with patch.dict("os.environ", env, clear=True), patch("backend.env.load_dotenv"):
        load_backend_env()

        import os

        assert os.environ["SUPABASE_ANON_KEY"] == "anon-key"


def test_production_backend_env_does_not_alias_vite_supabase_anon_key():
    env = {
        "ENVIRONMENT": "production",
        "VITE_SUPABASE_ANON_KEY": "anon-key",
    }
    with patch.dict("os.environ", env, clear=True), patch("backend.env.load_dotenv"):
        load_backend_env()

        import os

        assert "SUPABASE_ANON_KEY" not in os.environ


def test_local_env_presence_log_does_not_include_secret_values(caplog):
    env = {
        "SUPABASE_URL": "https://project.supabase.co",
        "SUPABASE_ANON_KEY": "anon-key",
        "SUPABASE_SERVICE_ROLE_KEY": "service-role-key",
        "DATABASE_URL": "postgresql://example",
    }
    with patch.dict("os.environ", env, clear=True):
        caplog.set_level(logging.INFO, logger="backend.env")
        log_local_env_presence()

    text = caplog.text
    assert "supabase_url_present=True" in text
    assert "supabase_anon_key_present=True" in text
    assert "supabase_service_role_key_present=True" in text
    assert "database_url_present=True" in text
    assert "anon-key" not in text
    assert "service-role-key" not in text
    assert "postgresql://example" not in text
