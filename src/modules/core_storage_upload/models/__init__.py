"""Upload models — the import registers the table in ``Base.metadata``."""

from src.modules.core_storage_upload.models.request import CoreStorageUploadRequest

__all__ = ["CoreStorageUploadRequest"]
