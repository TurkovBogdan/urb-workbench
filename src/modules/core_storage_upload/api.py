"""The module's one route in the ``/storage`` zone: ``POST|PUT /storage/upload``.

The body of the request is the file, as is, one file per request. Two kinds of client reach it,
and the request is let in only as one of them — before a byte of the body is read:

- **the person's page** — no ``token``; ``Origin`` present and the app's own (or a dev origin
  of ``Config.cors_origins``), so a page of another site cannot write. ``holder``, ``filename``,
  ``title``, ``description`` ride in the query; the answer (201) is the file as the holder's list
  shows it;
- **a client with an upload request** — ``?token=…`` from ``attach_file`` (``curl -T`` PUTs); the
  holder and what it is asked are the request's, ``filename`` may replace its name hint. The
  answer (200) is the opener's (``register_upload_answer``).

Neither — no ``Origin`` and no token, a script or ``curl`` on its own — is 401. A foreign
``Origin`` is 403 ``origin_refused``. The core's ``same_origin_only`` is not enough here: it lets a
request with no ``Origin`` through, and that request is exactly who must not write by itself.

Every refusal names its reason by code for the interface's dictionary: the module's own
(``errors.py``) or the holder's, with the status the holder's kind of refusal takes. The zone's
guard is ``allow_all``: the token or the ``Origin`` is the permission.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from src.core.api import ApiError
from src.core.router.origin import ORIGIN_REFUSED, connection_dev_origins, origin_allowed
from src.modules.core_storage.errors import FileTooLarge
from src.modules.core_storage_upload.constants import UPLOAD_ROUTE
from src.modules.core_storage_upload.errors import (
    FILE_TOO_LARGE,
    HOLDER_UNKNOWN,
    REQUEST_FOREIGN_HOLDER,
    REQUEST_NOT_FOUND,
    REQUEST_UNAUTHORIZED,
    FilenameRefused,
    HolderRefused,
    RefusalKind,
    RequestForeignHolder,
    RequestNotFound,
    UnknownHolder,
)
from src.modules.core_storage_upload.services.intake import upload_stream
from src.modules.core_storage_upload.services.requests import upload_with_request

router = APIRouter()

_UNAUTHORIZED = 401
_REQUEST_ENTITY_TOO_LARGE = 413
# The ceiling is set in whole megabytes (``max_file_size_mb``); the page words it that way.
_BYTES_PER_MB = 1024 * 1024


@router.api_route(UPLOAD_ROUTE, methods=["POST", "PUT"])
async def upload_file(
    request: Request,
    holder: str | None = None,
    token: str | None = None,
    filename: str | None = None,
    title: str = "",
    description: str = "",
) -> JSONResponse:
    try:
        if token is not None:
            answer = await upload_with_request(
                token,
                request.stream(),
                holder=holder,
                filename=filename,
                declared_size=_declared_size(request),
            )
            return JSONResponse(dict(answer))
        _admit_the_persons_page(request)
        answer = await _the_persons_upload(request, holder, filename or "", title, description)
        return JSONResponse(dict(answer), status_code=201)
    except RequestNotFound as error:
        raise ApiError.not_found(str(error), code=REQUEST_NOT_FOUND) from None
    except RequestForeignHolder as error:
        raise ApiError.bad_request(str(error), code=REQUEST_FOREIGN_HOLDER) from None
    except UnknownHolder as error:
        raise ApiError.bad_request(
            str(error), code=HOLDER_UNKNOWN, params={"holder": error.holder}
        ) from None
    except FilenameRefused as error:
        raise ApiError.bad_request(str(error), code=error.code) from None
    except FileTooLarge as error:
        # ``ApiError`` has no constructor for 413; the status is the meaning here. ``curl`` reads
        # the text, the page the code.
        raise ApiError(
            _REQUEST_ENTITY_TOO_LARGE,
            f"The file is over the {error.limit}-byte ceiling",
            code=FILE_TOO_LARGE,
            params={"limit": error.limit, "limit_mb": error.limit // _BYTES_PER_MB},
        ) from None
    except HolderRefused as error:
        raise _holder_refusal(error) from None


def _admit_the_persons_page(request: Request) -> None:
    origin = request.headers.get("origin")
    if origin is None:
        raise ApiError(
            _UNAUTHORIZED,
            "An upload comes from the app's own page or to an upload address attach_file opened",
            code=REQUEST_UNAUTHORIZED,
        )
    if not origin_allowed(origin, request.headers.get("host"), connection_dev_origins(request)):
        raise ApiError.forbidden("The request came from a page of another site", code=ORIGIN_REFUSED)


async def _the_persons_upload(
    request: Request, holder: str | None, filename: str, title: str, description: str
) -> Mapping[str, Any]:
    return await upload_stream(
        holder or "",
        request.stream(),
        payload={"title": title, "description": description},
        filename=filename,
        declared_size=_declared_size(request),
    )


def _holder_refusal(error: HolderRefused) -> ApiError:
    params = error.params or None
    if error.kind is RefusalKind.MISSING:
        return ApiError.not_found(str(error), code=error.code, params=params)
    if error.kind is RefusalKind.CONFLICT:
        return ApiError.conflict(str(error), code=error.code, params=params)
    if error.kind is RefusalKind.FORBIDDEN:
        return ApiError.forbidden(str(error), code=error.code, params=params)
    return ApiError.bad_request(str(error), code=error.code, params=params)


def _declared_size(request: Request) -> int | None:
    value = request.headers.get("content-length")
    return int(value) if value is not None and value.isdigit() else None


__all__ = ["router"]
