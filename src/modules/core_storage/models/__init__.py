"""Storage models — the import registers both tables in ``Base.metadata``."""

from src.modules.core_storage.models.file import CoreStorageFile
from src.modules.core_storage.models.file_owner import CoreStorageFileOwner

__all__ = ["CoreStorageFile", "CoreStorageFileOwner"]
