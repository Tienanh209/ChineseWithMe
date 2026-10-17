"""Structured logs: one JSON object per line, with request_id bound for the whole request.

No personal data: log ids, never emails, passwords, tokens or query strings.
"""

import logging
import re
import time
import uuid

import structlog
from fastapi import FastAPI, Request
from starlette.responses import Response

from app.errors import error_response

_REQUEST_ID_RE = re.compile(r"^[A-Za-z0-9._-]{1,64}$")


def configure_logging(level: str, json: bool) -> None:
    renderer = structlog.processors.JSONRenderer() if json else structlog.dev.ConsoleRenderer()
    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso", utc=True),
            structlog.processors.format_exc_info,
            renderer,
        ],
        wrapper_class=structlog.make_filtering_bound_logger(logging.getLevelNamesMapping()[level]),
        cache_logger_on_first_use=True,
    )


def install_request_logging(app: FastAPI) -> None:
    log = structlog.get_logger()

    @app.middleware("http")
    async def request_context(request: Request, call_next) -> Response:
        incoming = request.headers.get("x-request-id", "")
        request_id = incoming if _REQUEST_ID_RE.match(incoming) else uuid.uuid4().hex
        request.state.request_id = request_id
        structlog.contextvars.clear_contextvars()
        structlog.contextvars.bind_contextvars(request_id=request_id)

        start = time.perf_counter()
        try:
            response = await call_next(request)
        except Exception:
            log.exception("unhandled_exception", method=request.method, path=request.url.path)
            response = error_response(request, 500, "internal_error", "Internal server error.")
        duration_ms = round((time.perf_counter() - start) * 1000, 1)

        response.headers["X-Request-ID"] = request_id
        level = log.debug if request.url.path == "/api/health" else log.info
        level(
            "request",
            method=request.method,
            path=request.url.path,
            status=response.status_code,
            duration_ms=duration_ms,
        )
        return response
