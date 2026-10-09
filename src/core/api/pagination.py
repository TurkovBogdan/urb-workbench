"""A paginated list envelope — the common response shape of list read endpoints.

``Paged[T]`` wraps a page of items (``items``) with pagination metadata
(``total`` — all rows under the filter, ``page``/``page_size`` — the current window). Modules
return lists in this shape, and the frontend client parses it uniformly.
"""

from __future__ import annotations

from typing import Generic, TypeVar

from pydantic import BaseModel

T = TypeVar("T")


class Paged(BaseModel, Generic[T]):
    items: list[T]
    total: int
    page: int
    page_size: int


__all__ = ["Paged"]
