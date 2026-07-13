import logging

from backend.logging_config import DevelopmentExtraFormatter


def test_development_formatter_renders_provider_diagnostic_extra_fields():
    formatter = DevelopmentExtraFormatter("%(levelname)s %(message)s")
    record = logging.LogRecord(
        "backend.services.book_search",
        logging.WARNING,
        __file__,
        1,
        "metadata_provider_http_request_failed",
        (),
        None,
    )
    record.provider = "open_library"
    record.http_status = 403
    record.request_url = "https://www.googleapis.com/books/v1/volumes?q=Dune"
    record.response_body = '{"error":"forbidden"}'
    record.exception_type = "HTTPStatusError"
    record.elapsed_ms = 123.45
    record.outcome = "http_failure"

    output = formatter.format(record)

    assert "metadata_provider_http_request_failed" in output
    assert "provider='open_library'" in output
    assert "http_status=403" in output
    assert "request_url='https://www.googleapis.com/books/v1/volumes?q=Dune'" in output
    assert 'response_body=\'{"error":"forbidden"}\'' in output
    assert "exception_type='HTTPStatusError'" in output
    assert "elapsed_ms=123.45" in output
    assert "outcome='http_failure'" in output
