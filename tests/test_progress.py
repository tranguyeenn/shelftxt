from backend.services.progress import (
    clamp_pages_read,
    clamp_progress_percent,
    estimated_pages_read,
)


def test_percentage_to_estimated_page_conversion():
    assert estimated_pages_read(25, 304) == 76
    assert estimated_pages_read(60, 450) == 270
    assert estimated_pages_read(80, 950) == 760


def test_progress_values_are_clamped():
    assert clamp_progress_percent(-20) == 0
    assert clamp_progress_percent(140) == 100
    assert estimated_pages_read(-10, 304) == 0
    assert estimated_pages_read(150, 304) == 304
    assert clamp_pages_read(-50, 304) == 0
    assert clamp_pages_read(900, 304) == 304
