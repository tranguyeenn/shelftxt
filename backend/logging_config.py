"""Logging setup for local development visibility."""

from __future__ import annotations

import logging

from backend.env import is_local_env


DIAGNOSTIC_LOG_FIELDS = (
    "provider",
    "source",
    "attempt",
    "outcome",
    "http_status",
    "request_url",
    "response_body",
    "exception_type",
    "error_type",
    "elapsed_ms",
    "latency_ms",
    "result_count",
    "transient",
)


class DevelopmentExtraFormatter(logging.Formatter):
    """Append selected structured fields to console logs in development."""

    def format(self, record: logging.LogRecord) -> str:
        message = super().format(record)
        extras = []
        for field_name in DIAGNOSTIC_LOG_FIELDS:
            if not hasattr(record, field_name):
                continue
            value = getattr(record, field_name)
            if value is None:
                continue
            extras.append(f"{field_name}={value!r}")
        return f"{message} {' '.join(extras)}" if extras else message


def configure_development_logging() -> None:
    """Make structured provider diagnostics visible in local console logs."""
    if not is_local_env():
        return

    formatter = DevelopmentExtraFormatter(
        "%(asctime)s %(levelname)s [%(name)s] %(message)s"
    )
    root_logger = logging.getLogger()
    if not root_logger.handlers:
        logging.basicConfig(level=logging.INFO)

    for handler in root_logger.handlers:
        handler.setFormatter(formatter)

    root_logger.setLevel(logging.INFO)
