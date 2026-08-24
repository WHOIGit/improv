"""ImprovConfig and load_config().

Base config (no service extras required) covers the columnar store and
registered parsers/plugins. Service config adds the PostgreSQL URL and
optional object store.

Environment variables (for load_config):

Columnar store
  IMPROV_DB_BACKEND       — "duckdb" (default) or "vastdb"
  IMPROV_DB_ROOT          — root path or s3:// URL          [duckdb, required]
  IMPROV_S3_ENDPOINT      — S3 endpoint as bare host:port    [duckdb, optional]
  IMPROV_S3_ACCESS_KEY    — S3 access key                    [duckdb, optional]
  IMPROV_S3_SECRET_KEY    — S3 secret key                    [duckdb, optional]
  IMPROV_S3_USE_SSL       — "false" for an http-only endpoint [duckdb, optional]
  IMPROV_DUCKDB_THREADS   — DuckDB thread count              [duckdb, optional]
  IMPROV_VASTDB_ENDPOINT  — VAST DB endpoint                 [vastdb, required]
  IMPROV_VASTDB_ACCESS_KEY, IMPROV_VASTDB_SECRET_KEY         [vastdb, required]
  IMPROV_VASTDB_BUCKET, IMPROV_VASTDB_SCHEMA                 [vastdb, required]

OLTP database
  IMPROV_DATABASE_URL     — SQLAlchemy URL (PostgreSQL or SQLite); required to
                            serve the REST surface

Plugins and parsers
  IMPROV_PLUGINS          — comma-separated provenance plugin names
  IMPROV_PARSERS          — comma-separated image ID parser names
                            (see PLUGIN_REGISTRY / PARSER_REGISTRY below)

Object store (at most one; S3 wins if both are set)
  IMPROV_OBJECT_BUCKET    — S3 bucket for image bytes and blobs
  IMPROV_OBJECT_S3_ENDPOINT   — full URL *with scheme*
  IMPROV_OBJECT_S3_ACCESS_KEY, IMPROV_OBJECT_S3_SECRET_KEY
  IMPROV_OBJECT_S3_CA_BUNDLE  — CA bundle path for an internal CA (optional)
  IMPROV_STORAGE_PATH     — local/NFS path for HashdirStore object storage

Auth
  IMPROV_API_TOKEN        — shared bearer token for the REST surface (required
                            for service mode; protects every write endpoint plus
                            ingest-task read and classifier decode)
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Callable

from amplify_db_utils import DuckDBParquetConfig

if TYPE_CHECKING:
    from amplify_db_utils.vastdb_store import VastDBConfig
    from improv.ids import ImageIdParser
    from improv.plugins import ProvenancePlugin
    from storage.object import ObjectStore


@dataclass
class ImprovConfig:
    # Columnar store — required
    db_config: "DuckDBParquetConfig | VastDBConfig"

    # OLTP database — required for service mode; omit for batch-producer use
    database_url: str | None = None

    # Registered parsers and plugins — set at startup by the application
    parsers: "list[ImageIdParser]" = field(default_factory=list)
    plugins: "list[ProvenancePlugin]" = field(default_factory=list)

    # Object store for binary product retrieval — optional
    storage: "ObjectStore | None" = None

    # Shared bearer token for the REST surface — required for service mode
    api_token: str | None = None


# ---------------------------------------------------------------------------
# Plugin and parser registries
#
# Deployments select plugins and parsers by name via IMPROV_PLUGINS and
# IMPROV_PARSERS. Values are zero-argument factories, and instrument-specific
# ones import inside the factory so that core stays importable without their
# dependencies — the same discipline improv.plugins.__init__ follows.
#
# A plugin that is configured but absent means its index table is never
# registered and its provenance kind is never indexed. That failure is silent
# at the data layer, so an unknown name raises here instead.
# ---------------------------------------------------------------------------


def _geolocation() -> "ProvenancePlugin":
    from improv.plugins.geolocation import GeoLocationPlugin

    return GeoLocationPlugin()


def _sample_context() -> "ProvenancePlugin":
    from improv.plugins.sample_context import SampleContextPlugin

    return SampleContextPlugin()


def _blob() -> "ProvenancePlugin":
    from improv.plugins.blob import BlobPlugin

    return BlobPlugin()


def _machine_classification() -> "ProvenancePlugin":
    from improv.plugins.classification import MachineClassificationPlugin

    return MachineClassificationPlugin()


def _ifcb_features() -> "ProvenancePlugin":
    from improv.plugins.ifcb import IFCBFeaturesPlugin

    return IFCBFeaturesPlugin()


def _ifcb_cnn_classification() -> "ProvenancePlugin":
    from improv.plugins.ifcb import IFCBCNNClassificationPlugin

    return IFCBCNNClassificationPlugin()


def _ifcb_parser() -> "ImageIdParser":
    from improv.plugins.ifcb import IFCBImageIdParser

    return IFCBImageIdParser()


#: Name → factory for provenance plugins selectable via IMPROV_PLUGINS.
PLUGIN_REGISTRY: dict[str, Callable[[], "ProvenancePlugin"]] = {
    "geolocation": _geolocation,
    "sample_context": _sample_context,
    "blob": _blob,
    "machine_classification": _machine_classification,
    "ifcb_features": _ifcb_features,
    "ifcb_cnn_classification": _ifcb_cnn_classification,
}

#: Name → factory for image ID parsers selectable via IMPROV_PARSERS.
PARSER_REGISTRY: dict[str, Callable[[], "ImageIdParser"]] = {
    "ifcb": _ifcb_parser,
}


def _parse_names(value: str | None) -> list[str]:
    """Split a comma-separated env value, dropping blanks and whitespace."""
    if not value:
        return []
    return [name.strip() for name in value.split(",") if name.strip()]


def _build_from_registry(
    names: list[str],
    registry: dict[str, Callable[[], object]],
    env_var: str,
) -> list:
    """Instantiate registry entries for *names*, preserving order.

    Raises RuntimeError on an unknown or duplicated name rather than silently
    skipping it — a missing plugin is invisible until queries come back empty.
    """
    built = []
    seen: set[str] = set()
    for name in names:
        if name not in registry:
            raise RuntimeError(
                f"Unknown name {name!r} in {env_var}. "
                f"Available: {', '.join(sorted(registry))}."
            )
        if name in seen:
            raise RuntimeError(f"Duplicate name {name!r} in {env_var}.")
        seen.add(name)
        built.append(registry[name]())
    return built


def build_plugins(names: list[str]) -> "list[ProvenancePlugin]":
    """Instantiate the named provenance plugins."""
    return _build_from_registry(names, PLUGIN_REGISTRY, "IMPROV_PLUGINS")


def build_parsers(names: list[str]) -> "list[ImageIdParser]":
    """Instantiate the named image ID parsers.

    Order matters: parsers are tried in sequence and first match wins
    (see improv.ids.make_partition_keys).
    """
    return _build_from_registry(names, PARSER_REGISTRY, "IMPROV_PARSERS")


# ---------------------------------------------------------------------------
# Environment loading
# ---------------------------------------------------------------------------


def _env_bool(name: str, default: bool) -> bool:
    raw = os.environ.get(name)
    if raw is None:
        return default
    lowered = raw.strip().lower()
    if lowered in ("1", "true", "yes", "on"):
        return True
    if lowered in ("0", "false", "no", "off"):
        return False
    raise RuntimeError(f"{name} must be a boolean, got {raw!r}.")


def _env_int(name: str) -> int | None:
    raw = os.environ.get(name)
    if raw is None or not raw.strip():
        return None
    try:
        return int(raw)
    except ValueError:
        raise RuntimeError(f"{name} must be an integer, got {raw!r}.") from None


def _require(name: str) -> str:
    """Read a required env var, reporting the variable name on failure."""
    value = os.environ.get(name)
    if not value:
        raise RuntimeError(f"{name} is required.")
    return value


def _load_db_config() -> "DuckDBParquetConfig | VastDBConfig":
    backend = os.environ.get("IMPROV_DB_BACKEND", "duckdb").strip().lower()

    if backend == "vastdb":
        # Imported lazily so non-VAST installs (local/CI) never load vastdb.
        from amplify_db_utils.vastdb_store import VastDBConfig

        return VastDBConfig(
            endpoint=_require("IMPROV_VASTDB_ENDPOINT"),
            access_key=_require("IMPROV_VASTDB_ACCESS_KEY"),
            secret_key=_require("IMPROV_VASTDB_SECRET_KEY"),
            bucket=_require("IMPROV_VASTDB_BUCKET"),
            schema=_require("IMPROV_VASTDB_SCHEMA"),
            add_written_at=True,
        )

    if backend == "duckdb":
        return DuckDBParquetConfig(
            root=_require("IMPROV_DB_ROOT"),
            s3_endpoint=os.environ.get("IMPROV_S3_ENDPOINT"),
            s3_access_key=os.environ.get("IMPROV_S3_ACCESS_KEY"),
            s3_secret_key=os.environ.get("IMPROV_S3_SECRET_KEY"),
            s3_use_ssl=_env_bool("IMPROV_S3_USE_SSL", True),
            threads=_env_int("IMPROV_DUCKDB_THREADS"),
        )

    raise RuntimeError(
        f"Unknown IMPROV_DB_BACKEND {backend!r}. Expected 'duckdb' or 'vastdb'."
    )


def _load_storage() -> "ObjectStore | None":
    """Build the object store from the environment, or None if unconfigured."""
    bucket = os.environ.get("IMPROV_OBJECT_BUCKET")
    if bucket:
        # Imported lazily: pulls boto3, which only the [s3] extra installs.
        from improv.objectstore import build_s3_object_store

        return build_s3_object_store(
            bucket=bucket,
            endpoint_url=_require("IMPROV_OBJECT_S3_ENDPOINT"),
            access_key=_require("IMPROV_OBJECT_S3_ACCESS_KEY"),
            secret_key=_require("IMPROV_OBJECT_S3_SECRET_KEY"),
            verify=os.environ.get("IMPROV_OBJECT_S3_CA_BUNDLE") or True,
        )

    storage_path = os.environ.get("IMPROV_STORAGE_PATH")
    if storage_path:
        from storage.fs import HashdirStore

        return HashdirStore(storage_path)

    return None


def load_config() -> ImprovConfig:
    """Build ImprovConfig from environment variables.

    Raises RuntimeError on a missing required variable or an unrecognized
    backend, plugin, or parser name.
    """
    return ImprovConfig(
        db_config=_load_db_config(),
        database_url=os.environ.get("IMPROV_DATABASE_URL"),
        parsers=build_parsers(_parse_names(os.environ.get("IMPROV_PARSERS"))),
        plugins=build_plugins(_parse_names(os.environ.get("IMPROV_PLUGINS"))),
        storage=_load_storage(),
        api_token=os.environ.get("IMPROV_API_TOKEN"),
    )
