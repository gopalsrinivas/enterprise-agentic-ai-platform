"""Structured logging tests."""

import json
import logging

from app.core.logging import JsonFormatter, correlation_id_context


def test_json_formatter_emits_correlation_and_structured_fields() -> None:
    request_id = "d9428888-122b-11e1-b85c-61cd3cbb3210"
    token = correlation_id_context.set(request_id)
    try:
        record = logging.LogRecord(
            name="test.logger",
            level=logging.INFO,
            pathname=__file__,
            lineno=1,
            msg="request_completed",
            args=(),
            exc_info=None,
        )
        record.status_code = 200
        payload = json.loads(JsonFormatter().format(record))
    finally:
        correlation_id_context.reset(token)

    assert payload["message"] == "request_completed"
    assert payload["level"] == "INFO"
    assert payload["request_id"] == request_id
    assert payload["status_code"] == 200
