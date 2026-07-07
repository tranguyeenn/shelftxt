import logging
import os

logger = logging.getLogger(__name__)


def debug_recommendations_enabled() -> bool:
    return os.getenv("DEBUG_RECOMMENDATIONS", "").strip().lower() in {"1", "true", "yes"}


def rec_debug(message: str, *args) -> None:
    if not debug_recommendations_enabled():
        return
    logger.warning("recommendation_debug " + message, *args)
