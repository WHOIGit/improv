"""Construct a ColumnarStore from an ImprovConfig.

Shared by the API lifespan and the ``improv schema`` CLI so the two cannot
drift apart — the CLI must provision exactly the store the workers will open.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from amplify_db_utils import ColumnarStore

    from improv.config import ImprovConfig


def build_store(config: "ImprovConfig") -> "ColumnarStore":
    """Build the columnar store described by ``config.db_config``.

    Creates no tables. Raises RuntimeError if the config is of an unrecognized
    type, or names the VAST backend without the ``vastdb`` extra installed.
    """
    from amplify_db_utils import DuckDBParquetConfig, DuckDBParquetStore

    # DuckDB checked first so non-VAST deployments never import vastdb.
    if isinstance(config.db_config, DuckDBParquetConfig):
        return DuckDBParquetStore(config.db_config)

    try:
        from amplify_db_utils.vastdb_store import VastDBConfig, VastDBStore
    except ImportError:
        # vastdb not installed, so db_config cannot be a VastDBConfig —
        # report the config error rather than the missing driver.
        raise RuntimeError(
            f"Unsupported db_config type: {type(config.db_config).__name__}"
        ) from None

    if isinstance(config.db_config, VastDBConfig):
        return VastDBStore(config.db_config)

    raise RuntimeError(
        f"Unsupported db_config type: {type(config.db_config).__name__}"
    )
