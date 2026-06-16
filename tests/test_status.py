import pytest

from backend.services.status import normalize_status


@pytest.mark.parametrize("value", ["Read", "read", "Completed", "completed", "Finished", "finished"])
def test_normalize_status_completed_values(value):
    assert normalize_status(value) == "completed"


@pytest.mark.parametrize("value", ["To Read", "Unread"])
def test_normalize_status_not_started_values(value):
    assert normalize_status(value) == "not_started"


def test_normalize_status_reading_value():
    assert normalize_status("Reading") == "reading"
