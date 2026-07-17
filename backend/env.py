import os
import logging
from pathlib import Path

from dotenv import load_dotenv

ROOT_DIR = Path(__file__).resolve().parents[1]
ENV_PATH = ROOT_DIR / ".env"
BACKEND_ENV_PATH = ROOT_DIR / "backend" / ".env"

logger = logging.getLogger(__name__)

OLLAMA_ENABLED = False
OLLAMA_BASE_URL = "http://localhost:11434"
OLLAMA_EMBEDDING_MODEL = "embeddinggemma"
OLLAMA_TIMEOUT_SECONDS = 10
OLLAMA_EMBEDDING_DIMENSION = 768


def _env_bool(name: str, default: bool = False) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().casefold() in {"1", "true", "yes", "on"}


def ollama_enabled() -> bool:
    return _env_bool("OLLAMA_ENABLED", OLLAMA_ENABLED)


def embeddings_debug_enabled() -> bool:
    return _env_bool("EMBEDDINGS_DEBUG_ENABLED", False)


def ollama_base_url() -> str:
    return os.getenv("OLLAMA_BASE_URL", OLLAMA_BASE_URL).rstrip("/")


def ollama_embedding_model() -> str:
    return os.getenv("OLLAMA_EMBEDDING_MODEL", OLLAMA_EMBEDDING_MODEL).strip() or OLLAMA_EMBEDDING_MODEL


def ollama_timeout_seconds() -> float:
    try:
        return float(os.getenv("OLLAMA_TIMEOUT_SECONDS", str(OLLAMA_TIMEOUT_SECONDS)))
    except (TypeError, ValueError):
        return float(OLLAMA_TIMEOUT_SECONDS)


def load_backend_env() -> None:
    load_dotenv(dotenv_path=ENV_PATH, override=False)
    load_dotenv(dotenv_path=BACKEND_ENV_PATH, override=False)
    if (
        is_local_env()
        and not os.getenv("SUPABASE_ANON_KEY")
        and os.getenv("VITE_SUPABASE_ANON_KEY")
    ):
        os.environ["SUPABASE_ANON_KEY"] = os.getenv("VITE_SUPABASE_ANON_KEY", "")


def is_local_env() -> bool:
    environment = (os.getenv("ENVIRONMENT") or "").strip().lower()
    return not os.getenv("RENDER") and not os.getenv("VERCEL") and environment not in {
        "production",
        "prod",
    }


def log_local_env_presence() -> None:
    if not is_local_env():
        return

    logger.info(
        "Local backend env: supabase_url_present=%s supabase_anon_key_present=%s "
        "supabase_service_role_key_present=%s database_url_present=%s",
        bool(os.getenv("SUPABASE_URL")),
        bool(os.getenv("SUPABASE_ANON_KEY")),
        bool(os.getenv("SUPABASE_SERVICE_ROLE_KEY")),
        bool(os.getenv("DATABASE_URL")),
    )
