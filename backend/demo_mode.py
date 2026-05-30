import os

READ_ONLY_ENV = "DEMO_READ_ONLY"


def is_demo_read_only() -> bool:
    return os.getenv(READ_ONLY_ENV, "").strip().lower() in ("1", "true", "yes")
