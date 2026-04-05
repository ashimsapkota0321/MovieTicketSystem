"""Logging helpers for request correlation."""

from __future__ import annotations

import logging
from contextvars import ContextVar, Token

_REQUEST_ID_CONTEXT: ContextVar[str] = ContextVar("request_id", default="-")


def set_request_id(value: str) -> Token:
    return _REQUEST_ID_CONTEXT.set(str(value or "-"))


def reset_request_id(token: Token) -> None:
    _REQUEST_ID_CONTEXT.reset(token)


def get_request_id() -> str:
    value = _REQUEST_ID_CONTEXT.get()
    return str(value or "-")


class RequestContextFilter(logging.Filter):
    """Inject default request context fields so formatters remain stable."""

    _default_fields = {
        "request_id": "-",
        "method": "-",
        "path": "-",
        "status_code": "-",
        "duration_ms": "-",
        "user_id": "-",
        "client_ip": "-",
    }

    def filter(self, record: logging.LogRecord) -> bool:
        if not getattr(record, "request_id", None):
            record.request_id = get_request_id()

        for field, default_value in self._default_fields.items():
            if not hasattr(record, field):
                setattr(record, field, default_value)

        return True
