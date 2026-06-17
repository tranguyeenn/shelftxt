import os
import logging
from pathlib import Path

from dotenv import load_dotenv

ROOT_DIR = Path(__file__).resolve().parents[1]
ENV_PATH = ROOT_DIR / ".env"

logger = logging.getLogger(__name__)


def load_backend_env() -> None:
    load_dotenv(dotenv_path=ENV_PATH, override=False)
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
