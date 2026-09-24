"""Стандартные ошибки API.

Единый формат тела ошибки для любого не-2xx ответа: ``{error, code?, params?, fields?}``.
Успех остаётся «телом как есть» — стандартизируем только ошибки (статус-код —
источник истины об успехе/неуспехе).

Модули кидают ``ApiError`` (через удобные конструкторы), общий handler
(``register_exception_handlers``) превращает её в ``ErrorBody`` + HTTP-статус.

Язык ответа — не забота бэкенда: причину, которую он понимает, он называет кодом
(``<модуль>.<сущность>.<причина>`` или общим, без модуля), а текст на языке интерфейса даёт
словарь фронта, подставляя ``params``. ``error`` — английский запасной текст для кода, которого
фронт не знает, и для отказов без кода.
"""

from __future__ import annotations

from pydantic import BaseModel

ErrorParams = dict[str, str | int]


class ErrorBody(BaseModel):
    """Тело любого не-2xx ответа API."""

    error: str                                # английский запасной текст
    code: str | None = None                   # машинный код — по нему фронт берёт текст из словаря
    params: ErrorParams | None = None         # значения для подстановки в текст кода
    fields: dict[str, str] | None = None      # ошибки по полям (валидация форм)


class ApiError(Exception):
    """Бизнес-ошибка API. Перехватывается общим handler'ом → ErrorBody + status_code.

    Использовать конструкторы по статусам (``ApiError.not_found(...)`` и т.п.),
    а не собирать вручную — так статус и семантика не разъезжаются.
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

    # ── конструкторы по статусам ─────────────────────────────────────────
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
