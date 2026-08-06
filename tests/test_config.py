"""load_config() and the plugin/parser registries.

A plugin that is configured but never instantiated fails silently — its index
table is not registered and its provenance kind is not indexed, which surfaces
much later as empty query results. These tests pin the loud-failure behaviour.
"""

from __future__ import annotations

import pytest
from amplify_db_utils import DuckDBParquetConfig

from improv.config import (
    PARSER_REGISTRY,
    PLUGIN_REGISTRY,
    build_parsers,
    build_plugins,
    load_config,
)


@pytest.fixture(autouse=True)
def clean_env(monkeypatch):
    """Drop every IMPROV_* var so tests don't inherit a developer's shell."""
    import os

    for key in list(os.environ):
        if key.startswith("IMPROV_"):
            monkeypatch.delenv(key, raising=False)


# --- registries ------------------------------------------------------------

def test_every_registered_plugin_instantiates():
    """Each registry entry must import and construct with no arguments."""
    for name in PLUGIN_REGISTRY:
        plugin = build_plugins([name])[0]
        assert isinstance(plugin.kind, str) and plugin.kind


def test_every_registered_parser_instantiates():
    for name in PARSER_REGISTRY:
        parser = build_parsers([name])[0]
        assert hasattr(parser, "parse")


def test_registered_plugin_kinds_are_unique():
    """Two plugins claiming one kind means the service silently routes to one."""
    kinds = [build_plugins([name])[0].kind for name in PLUGIN_REGISTRY]
    assert len(kinds) == len(set(kinds))


def test_unknown_plugin_name_raises():
    with pytest.raises(RuntimeError, match="IMPROV_PLUGINS"):
        build_plugins(["no_such_plugin"])


def test_unknown_parser_name_raises():
    with pytest.raises(RuntimeError, match="IMPROV_PARSERS"):
        build_parsers(["no_such_parser"])


def test_duplicate_plugin_name_raises():
    with pytest.raises(RuntimeError, match="Duplicate"):
        build_plugins(["geolocation", "geolocation"])


def test_plugin_order_is_preserved():
    names = ["sample_context", "geolocation", "blob"]
    assert [p.kind for p in build_plugins(names)] == names


# --- load_config -----------------------------------------------------------

def test_duckdb_backend_requires_db_root(monkeypatch):
    monkeypatch.setenv("IMPROV_API_TOKEN", "t")
    with pytest.raises(RuntimeError, match="IMPROV_DB_ROOT"):
        load_config()


def test_unknown_backend_raises(monkeypatch):
    """Previously an UnboundLocalError from the unassigned db_cfg."""
    monkeypatch.setenv("IMPROV_DB_BACKEND", "postgres")
    with pytest.raises(RuntimeError, match="Unknown IMPROV_DB_BACKEND"):
        load_config()


def test_loads_duckdb_config(monkeypatch, tmp_path):
    monkeypatch.setenv("IMPROV_DB_ROOT", str(tmp_path / "store"))
    monkeypatch.setenv("IMPROV_DATABASE_URL", "sqlite:///:memory:")
    monkeypatch.setenv("IMPROV_API_TOKEN", "secret")
    monkeypatch.setenv("IMPROV_PLUGINS", "geolocation,sample_context")
    monkeypatch.setenv("IMPROV_PARSERS", "ifcb")

    config = load_config()

    assert isinstance(config.db_config, DuckDBParquetConfig)
    assert config.database_url == "sqlite:///:memory:"
    assert config.api_token == "secret"
    assert [p.kind for p in config.plugins] == ["geolocation", "sample_context"]
    assert len(config.parsers) == 1
    assert config.storage is None


def test_backend_name_is_case_and_space_insensitive(monkeypatch, tmp_path):
    monkeypatch.setenv("IMPROV_DB_BACKEND", "  DuckDB ")
    monkeypatch.setenv("IMPROV_DB_ROOT", str(tmp_path / "store"))
    assert isinstance(load_config().db_config, DuckDBParquetConfig)


def test_blank_plugin_list_yields_no_plugins(monkeypatch, tmp_path):
    monkeypatch.setenv("IMPROV_DB_ROOT", str(tmp_path / "store"))
    monkeypatch.setenv("IMPROV_PLUGINS", " , ")
    assert load_config().plugins == []


def test_s3_use_ssl_and_threads_are_wired(monkeypatch):
    monkeypatch.setenv("IMPROV_DB_ROOT", "s3://bucket/prefix")
    monkeypatch.setenv("IMPROV_S3_ENDPOINT", "vast-s3.example:9000")
    monkeypatch.setenv("IMPROV_S3_USE_SSL", "false")
    monkeypatch.setenv("IMPROV_DUCKDB_THREADS", "4")

    db_config = load_config().db_config

    assert db_config.s3_use_ssl is False
    assert db_config.threads == 4


def test_bad_boolean_raises(monkeypatch, tmp_path):
    monkeypatch.setenv("IMPROV_DB_ROOT", str(tmp_path / "store"))
    monkeypatch.setenv("IMPROV_S3_USE_SSL", "maybe")
    with pytest.raises(RuntimeError, match="IMPROV_S3_USE_SSL"):
        load_config()


def test_bad_thread_count_raises(monkeypatch, tmp_path):
    monkeypatch.setenv("IMPROV_DB_ROOT", str(tmp_path / "store"))
    monkeypatch.setenv("IMPROV_DUCKDB_THREADS", "lots")
    with pytest.raises(RuntimeError, match="IMPROV_DUCKDB_THREADS"):
        load_config()


def test_vastdb_backend_reports_missing_var_by_name(monkeypatch):
    """A missing VAST var must name itself, not surface as a bare KeyError."""
    pytest.importorskip("vastdb")
    monkeypatch.setenv("IMPROV_DB_BACKEND", "vastdb")
    monkeypatch.setenv("IMPROV_VASTDB_ENDPOINT", "https://vast.example")
    with pytest.raises(RuntimeError, match="IMPROV_VASTDB_ACCESS_KEY"):
        load_config()


# --- object store selection ------------------------------------------------

def test_storage_path_builds_hashdir_store(monkeypatch, tmp_path):
    from storage.fs import HashdirStore

    monkeypatch.setenv("IMPROV_DB_ROOT", str(tmp_path / "store"))
    monkeypatch.setenv("IMPROV_STORAGE_PATH", str(tmp_path / "objects"))
    assert isinstance(load_config().storage, HashdirStore)


def test_object_bucket_requires_endpoint(monkeypatch, tmp_path):
    pytest.importorskip("boto3")
    monkeypatch.setenv("IMPROV_DB_ROOT", str(tmp_path / "store"))
    monkeypatch.setenv("IMPROV_OBJECT_BUCKET", "images")
    with pytest.raises(RuntimeError, match="IMPROV_OBJECT_S3_ENDPOINT"):
        load_config()


def test_object_bucket_builds_s3_store(monkeypatch, tmp_path):
    pytest.importorskip("boto3")
    from improv.objectstore import S3ObjectStore

    monkeypatch.setenv("IMPROV_DB_ROOT", str(tmp_path / "store"))
    monkeypatch.setenv("IMPROV_OBJECT_BUCKET", "images")
    monkeypatch.setenv("IMPROV_OBJECT_S3_ENDPOINT", "https://vast-s3.example")
    monkeypatch.setenv("IMPROV_OBJECT_S3_ACCESS_KEY", "ak")
    monkeypatch.setenv("IMPROV_OBJECT_S3_SECRET_KEY", "sk")

    storage = load_config().storage

    assert isinstance(storage, S3ObjectStore)
    assert storage.bucket_name == "images"


def test_s3_object_store_wins_over_storage_path(monkeypatch, tmp_path):
    pytest.importorskip("boto3")
    from improv.objectstore import S3ObjectStore

    monkeypatch.setenv("IMPROV_DB_ROOT", str(tmp_path / "store"))
    monkeypatch.setenv("IMPROV_STORAGE_PATH", str(tmp_path / "objects"))
    monkeypatch.setenv("IMPROV_OBJECT_BUCKET", "images")
    monkeypatch.setenv("IMPROV_OBJECT_S3_ENDPOINT", "https://vast-s3.example")
    monkeypatch.setenv("IMPROV_OBJECT_S3_ACCESS_KEY", "ak")
    monkeypatch.setenv("IMPROV_OBJECT_S3_SECRET_KEY", "sk")

    assert isinstance(load_config().storage, S3ObjectStore)
