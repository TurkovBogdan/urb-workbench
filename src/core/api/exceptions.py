"""Unified exception handlers: FastAPI's whole native "zoo" → ``ErrorBody``.

Reduces everything to one format ``{error, code?, params?, fields?}``:
- ``ApiError``               — our business class (carries status/code/fields);
- ``HTTPException``          — a bare ``raise HTTPException(404, "...")`` across modules
                               (detail string → ``error``; detail object → message/code);
- ``RequestValidationError`` — Pydantic's 422 (list → ``fields``);
- ``Exception``              — unhandled → 500 (logged; a neutral text goes out).
"""

from __future__ import annotations

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from src.core.api.errors import ApiError, ErrorBody
from src.core.loggers import get_logger

_LOG = get_logger()


def _json(status_code: int, body: ErrorBody) -> JSONResponse:
    return JSONResponse(status_code=status_code, content=body.model_dump())


def register_exception_handlers(app: FastAPI) -> None:
    """Attach the shared error handlers to the app (call in create_app)."""

    @app.exception_handler(ApiError)
    async def _on_api_error(_: Request, exc: ApiError) -> JSONResponse:
        return _json(exc.status_code, exc.body())

    @app.exception_handler(StarletteHTTPException)
    async def _on_http_exception(_: Request, exc: StarletteHTTPException) -> JSONResponse:
        detail = exc.detail
        if isinstance(detail, dict):
            message = str(detail.get("error") or detail.get("message") or detail)
            code = detail.get("code")
            params = detail.get("params") if isinstance(detail.get("params"), dict) else None
            fields = detail.get("fields") if isinstance(detail.get("fields"), dict) else None
            body = ErrorBody(error=message, code=code, params=params, fields=fields)
        else:
            body = ErrorBody(error=str(detail))
        return _json(exc.status_code, body)

    @app.exception_handler(RequestValidationError)
    async def _on_validation(_: Request, exc: RequestValidationError) -> JSONResponse:
        fields: dict[str, str] = {}
        for err in exc.errors():
            # loc = ("body"/"query"/"path", <field>, ...) — drop the source, and only the source:
            # a field may itself be called ``body`` or ``path``, and its name is the whole point.
            loc = tuple(err.get("loc", ()))
            if loc and loc[0] in ("body", "query", "path"):
                loc = loc[1:]
            parts = [str(p) for p in loc]
            key = ".".join(parts) or "_"
            fields.setdefault(key, err.get("msg", "invalid"))
        body = ErrorBody(error="Validation failed", code="validation_error", fields=fields)
        return _json(422, body)

    @app.exception_handler(Exception)
    async def _on_unhandled(request: Request, exc: Exception) -> JSONResponse:
        _LOG.exception(
            "unhandled error on %s %s: %s", request.method, request.url.path, exc
        )
        return _json(500, ErrorBody(error="Internal server error", code="internal_error"))


__all__ = ["register_exception_handlers"]
