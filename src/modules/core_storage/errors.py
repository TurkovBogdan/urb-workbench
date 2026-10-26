"""Refusals of the file storage.

Exceptions rather than return values: "nothing was stored" must be visible at the call site,
and a ``None`` in the place of a stored file is checked by not every caller.
"""

from __future__ import annotations


class StorageError(Exception):
    """Base of every refusal of the storage."""


class InvalidStores(StorageError):
    """The store list given to the module cannot be used — the application does not start."""


class UnknownStore(StorageError):
    """Registration into a store that is not in the module's list."""

    def __init__(self, store: str, stores: tuple[str, ...]) -> None:
        super().__init__(f"Store {store!r} is not one of {', '.join(stores)}")
        self.store = store


class FileTooLarge(StorageError):
    """The file is over the size ceiling from the module settings; nothing was stored."""

    def __init__(self, limit: int, size: int) -> None:
        super().__init__(f"File of {size} bytes is over the {limit}-byte ceiling")
        self.limit = limit
        self.size = size


class FileNotFound(StorageError):
    """No file under this code; a soft-deleted one counts as absent unless asked for."""

    def __init__(self, code: str) -> None:
        super().__init__(f"No stored file {code}")
        self.code = code


class SourceNotFound(StorageError):
    """Registration from a path where there is no file."""

    def __init__(self, path: object) -> None:
        super().__init__(f"No file to register at {path}")
        self.path = path


class SourceInsideStorage(StorageError):
    """``move=True`` of a path inside the storage root: the module would delete its own bytes."""

    def __init__(self, path: object) -> None:
        super().__init__(f"{path} lies inside the storage root; register it without move")
        self.path = path


class CodeCollision(StorageError):
    """A generated code is taken. Internal: the caller picks another, and only when every try
    collided does this reach outside."""


__all__ = [
    "CodeCollision",
    "FileNotFound",
    "FileTooLarge",
    "InvalidStores",
    "SourceInsideStorage",
    "SourceNotFound",
    "StorageError",
    "UnknownStore",
]
