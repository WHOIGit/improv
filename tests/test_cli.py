"""`improv schema sync` — the single-process owner of the columnar schema.

Service startup declares tables but never creates them, so this command is the
only thing that does. If it stops working, or stops covering plugin index
tables, the failure surfaces as a 500 on the first write rather than at boot.
"""

from __future__ import annotations

import pytest
from click.testing import CliRunner

from improv.cli import cli


@pytest.fixture
def env(tmp_path, monkeypatch):
    """A minimal duckdb-backed environment, as .env would supply."""
    root = tmp_path / "store"
    monkeypatch.setenv("IMPROV_DB_BACKEND", "duckdb")
    monkeypatch.setenv("IMPROV_DB_ROOT", str(root))
    monkeypatch.setenv("IMPROV_PLUGINS", "geolocation,sample_context,blob")
    monkeypatch.delenv("IMPROV_PARSERS", raising=False)
    monkeypatch.delenv("IMPROV_OBJECT_BUCKET", raising=False)
    monkeypatch.delenv("IMPROV_STORAGE_PATH", raising=False)
    return root


def _sync() -> object:
    return CliRunner().invoke(cli, ["schema", "sync"])


def test_sync_creates_core_and_plugin_index_tables(env):
    result = _sync()

    assert result.exit_code == 0, result.output
    for table in ("images", "provenance", "geolocation_index", "sample_index"):
        assert table in result.output

    registry = (env / "_registry" / "tables.json").read_text()
    for table in ("images", "provenance", "geolocation_index", "sample_index"):
        assert f'"{table}"' in registry


def test_sync_skips_a_plugin_with_no_index_table(env):
    """BlobPlugin has index_table = None and must contribute nothing."""
    result = _sync()

    assert result.exit_code == 0, result.output
    assert "blob" not in result.output


def test_sync_is_idempotent(env):
    first = _sync()
    second = _sync()

    assert first.exit_code == 0, first.output
    assert second.exit_code == 0, second.output
    assert first.output == second.output


def test_sync_reports_a_config_error_without_a_traceback(env, monkeypatch):
    """A missing required variable is an operator error, not a crash."""
    monkeypatch.delenv("IMPROV_DB_ROOT")

    result = _sync()

    assert result.exit_code != 0
    assert "IMPROV_DB_ROOT" in result.output
    assert "Traceback" not in result.output


def test_sync_rejects_an_unknown_plugin_name(env, monkeypatch):
    """Matches load_config's contract: an unknown plugin fails loudly."""
    monkeypatch.setenv("IMPROV_PLUGINS", "geolocation,nonexistent")

    result = _sync()

    assert result.exit_code != 0
    assert "nonexistent" in result.output


def test_sync_needs_no_oltp_database(env, monkeypatch):
    """The columnar command must not depend on Postgres being reachable."""
    monkeypatch.delenv("IMPROV_DATABASE_URL", raising=False)

    assert _sync().exit_code == 0
