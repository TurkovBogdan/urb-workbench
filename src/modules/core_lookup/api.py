"""``/internal/core/lookup`` — previews of entities by their codes.

``POST`` only, with a JSON body: the app listens on localhost, and a plain ``GET`` can be fired by
any page open in the same browser.
"""

from __future__ import annotations

from fastapi import APIRouter

from src.modules.core_lookup import engine
from src.modules.core_lookup.dto import PreviewOut, PreviewRequest
from src.modules.core_lookup.registry import WORKSPACE_FILTER

router = APIRouter(tags=["lookup"])


@router.post("/preview", response_model=list[PreviewOut])
async def preview_codes(body: PreviewRequest) -> list[PreviewOut]:
    """A record for every distinct requested code: title, description and link, or the error."""
    filters = {WORKSPACE_FILTER: body.workspace} if body.workspace else {}
    return await engine.preview(body.codes, filters)


__all__ = ["router"]
