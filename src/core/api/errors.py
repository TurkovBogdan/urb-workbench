"""Standard API errors.

A single error body format for any non-2xx response: ``{error, code?, params?, fields?}``.
Success stays "the body as is" — only errors are standardised (the status code is the
source of truth on success/failure).

Modules raise ``ApiError`` (through the convenience constructors); the shared handler
(``register_exception_handlers``) turns it into ``ErrorBody`` + an HTTP status.

The response language is not the backend's concern: a reason it understands it names by a code
(``<module>.<entity>.<reason>`` or a general one, without a module), and the text in the interface
language comes from the frontend's dictionary, filling in ``params``. ``error`` is an English
fallback text for a code the frontend doesn't know, and for refusals without a code.
"""

from __future__ import annotations

from pydantic import BaseModel

ErrorParams = dict[str, str | int]


class ErrorBody(BaseModel):
    """The body of any non-2xx API response."""

    error: str                                # English fallback text
    code: str | None = None                   # machine code — the frontend looks up its text by it
    params: ErrorParams | None = None         # values to substitute into the code's text
    fields: dict[str, str] | None = None      # per-field errors (form validation)


class ApiError(Exception):
    """An API business error. Caught by the shared handler → ErrorBody + status_code.

    Use the per-status constructors (``ApiError.not_found(...)`` etc.) rather than
    assembling it by hand — that way the status and the semantics don't drift apart.
    """

    def __init__(
        self,
        status_code: int,
        message: str,
        *,
        code: str | None = None,
        params: ErrorParams | None = None,
        fields: dict[str, str] | None = None,
    ) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.message = message
        self.code = code
        self.params = params
        self.fields = fields

    def body(self) -> ErrorBody:
        return ErrorBody(error=self.message, code=self.code, params=self.params, fields=self.fields)

    # ── per-status constructors ──────────────────────────────────────────
    @classmethod
    def bad_request(cls, message: str = "Bad request", *, code: str | None = None,
                    params: ErrorParams | None = None,
                    fields: dict[str, str] | None = None) -> "ApiError":
        return cls(400, message, code=code, params=params, fields=fields)

    @classmethod
    def unauthorized(cls, message: str = "Authorization required", *, code: str | None = None,
                     params: ErrorParams | None = None) -> "ApiError":
        return cls(401, message, code=code, params=params)

    @classmethod
    def forbidden(cls, message: str = "Forbidden", *, code: str | None = None,
                  params: ErrorParams | None = None) -> "ApiError":
        return cls(403, message, code=code, params=params)

    @classmethod
    def not_found(cls, message: str = "Not found", *, code: str | None = None,
                  params: ErrorParams | None = None) -> "ApiError":
        return cls(404, message, code=code, params=params)

    @classmethod
    def conflict(cls, message: str = "Conflict", *, code: str | None = None,
                 params: ErrorParams | None = None,
                 fields: dict[str, str] | None = None) -> "ApiError":
        return cls(409, message, code=code, params=params, fields=fields)

    @classmethod
    def validation(cls, message: str = "Validation failed", *, fields: dict[str, str] | None = None,
                   code: str | None = "validation_error",
                   params: ErrorParams | None = None) -> "ApiError":
        return cls(422, message, code=code, params=params, fields=fields)

    @classmethod
    def too_many_requests(cls, message: str = "Too many requests", *, code: str | None = None,
                          params: ErrorParams | None = None) -> "ApiError":
        return cls(429, message, code=code, params=params)


__all__ = ["ApiError", "ErrorBody", "ErrorParams"]
