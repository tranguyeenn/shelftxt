COMPLETED_STATUSES = {"read", "completed", "complete", "finished", "finish", "done"}
READING_STATUSES = {"reading", "in progress", "in-progress", "started"}
NOT_STARTED_STATUSES = {
    "",
    "to read",
    "to-read",
    "unread",
    "not started",
    "not_started",
    "want",
    "want to read",
}


def normalize_status(value: str | None, *, progress_percent: float = 0, pages_read: int = 0) -> str:
    status = str(value or "").strip().lower()

    if status in COMPLETED_STATUSES:
        return "completed"
    if status in READING_STATUSES:
        return "reading"
    if status == "dnf":
        return "dnf"
    if status in NOT_STARTED_STATUSES:
        return "reading" if progress_percent > 0 or pages_read > 0 else "not_started"

    return "not_started"


def database_status_from_normalized(status: str) -> str:
    """
    Convert normalized app status to legacy database read_status.

    Legacy DB statuses:
    - read
    - to-read
    - dnf

    Note:
    Currently-reading books are stored as `to-read` plus progress/pages_read > 0.
    """
    if status == "completed":
        return "read"
    if status == "dnf":
        return "dnf"
    return "to-read"
