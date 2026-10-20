"""One error format for every non-2xx response:

    {"error": {"code": "not_found", "message": "...", "details": ..., "request_id": "..."}}

`code` is stable and machine-readable (the frontend switches on it); `message` is English
for developers; the UI shows its own translated text per code.
"""

from typing import Any

import structlog
from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

log = structlog.get_logger()

_HTTP_CODES = {
    400: "bad_request",
    401: "not_authenticated",
    403: "forbidden",
    404: "not_found",
    405: "method_not_allowed",
    409: "conflict",
    429: "rate_limited",
}


class AppError(Exception):
    def __init__(
        self, status: int, code: str, message: str, details: Any = None, headers: dict[str, str] | None = None
    ) -> None:
        super().__init__(message)
        self.status = status
        self.code = code
        self.message = message
        self.details = details
        self.headers = headers


def error_response(
    request: Request, status: int, code: str, message: str, details: Any = None, headers: dict[str, str] | None = None
) -> JSONResponse:
    request_id = getattr(request.state, "request_id", None)
    body = {"error": {"code": code, "message": message, "details": details, "request_id": request_id}}
    all_headers = {**(headers or {}), **({"X-Request-ID": request_id} if request_id else {})}
    return JSONResponse(body, status_code=status, headers=all_headers or None)


async def _app_error(request: Request, exc: AppError) -> JSONResponse:
    return error_response(request, exc.status, exc.code, exc.message, exc.details, exc.headers)


async def _validation_error(request: Request, exc: RequestValidationError) -> JSONResponse:
    # Keep only JSON-safe fields; `ctx` can hold exception objects, `input` can hold passwords.
    details = [{"loc": list(e["loc"]), "msg": e["msg"], "type": e["type"]} for e in exc.errors()]
    return error_response(request, 422, "validation_error", "Request validation failed.", details)


async def _http_error(request: Request, exc: StarletteHTTPException) -> JSONResponse:
    code = _HTTP_CODES.get(exc.status_code, "http_error")
    return error_response(request, exc.status_code, code, str(exc.detail))


async def _unhandled(request: Request, exc: Exception) -> JSONResponse:
    log.exception("unhandled_exception")
    return error_response(request, 500, "internal_error", "Internal server error.")


def install_error_handlers(app: FastAPI) -> None:
    app.add_exception_handler(AppError, _app_error)
    app.add_exception_handler(RequestValidationError, _validation_error)
    app.add_exception_handler(StarletteHTTPException, _http_error)
    app.add_exception_handler(Exception, _unhandled)
