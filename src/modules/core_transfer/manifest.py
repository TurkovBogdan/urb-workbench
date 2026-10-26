"""The manifest — the contract between two installations, read first and trusted last.

The import reads it before anything else and decides three things by it before touching the base:
is this format ours, did the file arrive whole, what will land if the person presses «Import».
"""

from __future__ import annotations

import json

from pydantic import BaseModel, Field, ValidationError

from src.modules.core_transfer.errors import (
    FOREIGN_FORMAT,
    MANIFEST_INVALID,
    NEWER_FORMAT,
    TransferError,
)


class ManifestSource(BaseModel):
    """Where the archive was taken: for the «this installation» hint and for incidents."""

    install_id: str = ""
    app_version: str = ""
    extra: dict[str, str] = Field(default_factory=dict)


class ManifestRoot(BaseModel):
    """The entity the archive was taken for."""

    code: str
    title: str = ""
    extra: dict[str, str] = Field(default_factory=dict)


class ManifestFile(BaseModel):
    """An inventory line: the entry, its unpacked size and its sha256."""

    path: str
    bytes: int
    sha256: str


class Manifest(BaseModel):
    format: str
    format_version: int
    archive_id: str
    created_at: str
    source: ManifestSource = Field(default_factory=ManifestSource)
    root: ManifestRoot
    counts: dict[str, int] = Field(default_factory=dict)
    files: list[ManifestFile] = Field(default_factory=list)
    dangling_refs: list[str] = Field(default_factory=list)


def manifest_bytes(manifest: Manifest) -> bytes:
    return manifest.model_dump_json(indent=2).encode("utf-8")


def parse_manifest(raw: bytes, *, format_name: str, supported_version: int) -> Manifest:
    """Read the manifest and refuse whatever this build cannot take."""
    try:
        manifest = Manifest.model_validate(json.loads(raw.decode("utf-8")))
    except (UnicodeDecodeError, json.JSONDecodeError, ValidationError) as error:
        raise TransferError(MANIFEST_INVALID, "The archive manifest is damaged or unreadable") from error

    if manifest.format != format_name:
        raise TransferError(
            FOREIGN_FORMAT,
            f"The archive is {manifest.format!r}, not {format_name!r}",
            params={"format": manifest.format},
        )
    if manifest.format_version > supported_version:
        raise TransferError(
            NEWER_FORMAT,
            f"The archive is of format version {manifest.format_version}, this build reads up to "
            f"{supported_version} — update the application",
            params={"version": manifest.format_version, "supported": supported_version},
        )
    if not manifest.archive_id or not manifest.root.code:
        raise TransferError(MANIFEST_INVALID, "The manifest names no export or no root entity")
    return manifest


__all__ = [
    "Manifest",
    "ManifestFile",
    "ManifestRoot",
    "ManifestSource",
    "manifest_bytes",
    "parse_manifest",
]
