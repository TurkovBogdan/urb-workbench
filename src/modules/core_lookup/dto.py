"""The wire form of a preview: one record per requested code, the error inside the record.

A record is either a preview or an error, never both: a code that has no preview carries empty
``title``, ``description`` and ``link`` and a filled ``error``. One shape for both outcomes keeps
the interface's cache a plain map from code to record.
"""

from __future__ import annotations

from typing import Annotated

from pydantic import BaseModel, Field, StringConstraints

# The batch a body can fairly need at once. The interface splits a longer one itself; a request
# over it is a client bug, refused whole (422) rather than half-answered.
MAX_CODES = 200
# A code is a type word and a short hash; anything longer is not a code and never reaches SQL.
CODE_MAX = 64


class PreviewRequest(BaseModel):
    codes: list[Annotated[str, StringConstraints(max_length=CODE_MAX)]] = Field(max_length=MAX_CODES)
    # The workspace the person works in (``WORKSPACE@…``); passed to the handlers as a filter.
    workspace: str | None = None
    # The entity whose page shows the codes (``TASK@…``, ``CODEX@…``); a filter as well.
    holder: Annotated[str, StringConstraints(max_length=CODE_MAX)] | None = None


class PreviewErrorOut(BaseModel):
    code: str
    message: str


class PreviewOut(BaseModel):
    code: str
    title: str = ""
    description: str = ""
    link: str = ""
    # A stored file's type (``application/pdf``); empty for every other code.
    mime: str = ""
    # The request's holder holds the file: its title and description are the page's to edit.
    held: bool = False
    error: PreviewErrorOut | None = None


__all__ = ["CODE_MAX", "MAX_CODES","PreviewErrorOut", "PreviewOut", "PreviewRequest"]
