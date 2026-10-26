"""The upload token stays out of the access log: uvicorn writes the request line with its query."""

from __future__ import annotations

import logging

import pytest

from src.modules.core_storage_upload.access_log import (
    ACCESS_LOGGER,
    RedactUploadTokens,
    redact_access_log,
)

pytestmark = pytest.mark.pure


def _line(path: str) -> logging.LogRecord:
    # The arguments uvicorn's access logger is called with.
    return logging.LogRecord(
        ACCESS_LOGGER,
        logging.INFO,
        __file__,
        1,
        '%s - "%s %s HTTP/%s" %d',
        ("127.0.0.1:5000", "PUT", path, "1.1", 200),
        None,
    )


def test_the_token_of_an_upload_line_is_blanked_and_the_rest_kept():
    record = _line("/storage/upload?token=eyJ2IjoxfQ.c2lnbmF0dXJl&filename=a.png")

    assert RedactUploadTokens().filter(record) is True

    assert record.getMessage() == (
        '127.0.0.1:5000 - "PUT /storage/upload?token=***&filename=a.png HTTP/1.1" 200'
    )


def test_a_line_of_another_route_is_left_as_it_is():
    record = _line("/internal/workbench/tasks?token=not-ours")

    RedactUploadTokens().filter(record)

    assert "token=not-ours" in record.getMessage()


def test_the_filter_is_put_on_the_access_logger_once(monkeypatch: pytest.MonkeyPatch):
    logger = logging.getLogger(ACCESS_LOGGER)
    monkeypatch.setattr(logger, "filters", [])

    redact_access_log()
    redact_access_log()

    assert [type(f) for f in logger.filters] == [RedactUploadTokens]
