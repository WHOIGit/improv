"""Service-owned table declarations.

The set of tables improv owns is described once, by ``service_tables()``, and
consumed by three callers with different privileges:

- ``declare_service_tables()`` runs in every API worker at startup. It only
  teaches the store instance each table's shape. No DDL, no network, no file
  writes — so the four uvicorn workers cannot race one another.
- ``verify_service_tables()`` also runs in every worker, straight after, and
  refuses to start if a table is missing. A read, so it cannot race either.
- ``create_service_tables()`` runs once, from ``improv schema sync``, and
  actually creates the tables. It is the only caller that mutates shared
  storage state.

That split exists because no columnar backend here offers an atomic
create-if-absent. VastDB's SDK takes a ``fail_if_exists`` argument, but it
gates a client-side existence check before an unconditional create RPC — the
flag never reaches the server — so two workers can both observe an absent
table and both try to create it. DuckDB+Parquet has the same shape of problem
with its unlocked schema-registry file. Creating from one process sidesteps
both, and mirrors how Alembic already owns the OLTP schema.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Iterator, NamedTuple

from improv.models.image import ImageRecord
from improv.models.provenance import ProvenanceEnvelope

if TYPE_CHECKING:
    import pyarrow as pa
    from amplify_db_utils import ColumnarStore
    from improv.plugins import ProvenancePlugin

_PARTITION_BY = ["instrument", "year", "month"]


class TableSpec(NamedTuple):
    """One table improv owns: its name, row schema, and partition keys."""

    name: str
    schema: "type | pa.Schema"
    partition_by: list[str]


def service_tables(
    plugins: "list[ProvenancePlugin] | None" = None,
) -> Iterator[TableSpec]:
    """Yield every table the service owns, core tables first.

    Plugin index tables are read straight off the ``ProvenancePlugin``
    protocol attributes rather than by calling into each plugin, so the
    declare and create paths cannot drift apart. A plugin with no index
    (``index_table = None``, e.g. BlobPlugin) contributes nothing.
    """
    yield TableSpec("images", ImageRecord, _PARTITION_BY)
    yield TableSpec("provenance", ProvenanceEnvelope, _PARTITION_BY)

    for plugin in plugins or []:
        if plugin.index_table and plugin.index_schema is not None:
            yield TableSpec(
                plugin.index_table,
                plugin.index_schema,
                list(plugin.partition_by or []),
            )


def declare_service_tables(
    store: "ColumnarStore",
    plugins: "list[ProvenancePlugin] | None" = None,
) -> None:
    """Teach *store* the shape of every service-owned table.

    Must be called before any read or write on a freshly constructed store —
    schema and partition keys live in the store instance, not in the backend.
    Creates nothing: the tables must already exist, via ``improv schema sync``.
    Safe to call concurrently from any number of processes.
    """
    for spec in service_tables(plugins):
        store.register_table(spec.name, spec.schema, partition_by=spec.partition_by)


def verify_service_tables(
    store: "ColumnarStore",
    plugins: "list[ProvenancePlugin] | None" = None,
) -> None:
    """Raise unless every service-owned table exists in the backing store.

    Restores fail-fast at startup, which was lost when creation moved out of
    the lifespan: without this, a deployment that skipped ``improv schema
    sync`` serves happily and then fails on the first write, with a
    backend-level "table not found" that points nowhere near the cause.

    One read per process and no writes, so unlike creation this cannot race.
    The cost is that startup now needs the columnar store reachable — a
    deliberate trade, since a worker that cannot see its tables cannot serve
    a write anyway.

    Raises:
        RuntimeError: If any expected table is missing.
    """
    existing = set(store.list_tables())
    missing = [spec.name for spec in service_tables(plugins) if spec.name not in existing]
    if missing:
        raise RuntimeError(
            f"Columnar tables missing from the store: {', '.join(missing)}. "
            f"Run `improv schema sync` before serving. "
            f"(Adding a plugin to IMPROV_PLUGINS needs a re-run — note that "
            f"`docker compose restart api` does not re-run it, `up -d` does.)"
        )


def create_service_tables(
    store: "ColumnarStore",
    plugins: "list[ProvenancePlugin] | None" = None,
) -> list[str]:
    """Create every service-owned table, and register it on *store*.

    Idempotent for a sequential caller: an existing table is validated for
    schema compatibility rather than recreated. Call from one process only.

    Returns:
        The table names processed, in creation order.
    """
    names = []
    for spec in service_tables(plugins):
        store.create_table(spec.name, spec.schema, partition_by=spec.partition_by)
        names.append(spec.name)
    return names
