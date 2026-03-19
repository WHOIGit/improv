"""ImprovConfig and load_config().

Base config (no service extras required) covers the columnar store and
registered parsers/plugins. Service config adds the PostgreSQL URL and
optional object store.

Environment variables (for load_config):
  IMPROV_DB_ROOT          — root path or s3:// URL for the columnar store
  IMPROV_DATABASE_URL     — SQLAlchemy database URL (PostgreSQL or SQLite)
  IMPROV_S3_ENDPOINT      — S3 endpoint override (optional)
  IMPROV_S3_ACCESS_KEY    — S3 access key (optional)
  IMPROV_S3_SECRET_KEY    — S3 secret key (optional)
  IMPROV_STORAGE_PATH     — local path for HashdirStore object storage (optional)
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from amplify_db_utils import DuckDBParquetConfig

if TYPE_CHECKING:
    from improv.ids import ImageIdParser
    from improv.plugins import ProvenancePlugin
    from storage.object import ObjectStore


@dataclass
class ImprovConfig:
    # Columnar store — required
    db_config: DuckDBParquetConfig

    # OLTP database — required for service mode; omit for batch-producer use
    database_url: str | None = None

    # Registered parsers and plugins — set at startup by the application
    parsers: "list[ImageIdParser]" = field(default_factory=list)
    plugins: "list[ProvenancePlugin]" = field(default_factory=list)

    # Object store for binary product retrieval — optional
    storage: "ObjectStore | None" = None


def load_config() -> ImprovConfig:
    """Build ImprovConfig from environment variables."""
    db_root = os.environ.get("IMPROV_DB_ROOT")
    if not db_root:
        raise RuntimeError(
            "IMPROV_DB_ROOT environment variable is required. "
            "Set it to a local path or s3:// URL."
        )

    db_cfg = DuckDBParquetConfig(
        root=db_root,
        s3_endpoint=os.environ.get("IMPROV_S3_ENDPOINT"),
        s3_access_key=os.environ.get("IMPROV_S3_ACCESS_KEY"),
        s3_secret_key=os.environ.get("IMPROV_S3_SECRET_KEY"),
    )

    storage = None
    storage_path = os.environ.get("IMPROV_STORAGE_PATH")
    if storage_path:
        from storage.fs import HashdirStore
        storage = HashdirStore(storage_path)

    return ImprovConfig(
        db_config=db_cfg,
        database_url=os.environ.get("IMPROV_DATABASE_URL"),
        storage=storage,
    )
