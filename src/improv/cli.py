"""improv CLI — entry point for schema management commands.

improv has two schemas, owned by two commands. Neither is created at service
startup: the OLTP schema because Alembic must own the migration history, the
columnar schema because creating it from four uvicorn workers at once races.

Usage:
    improv db upgrade --database-url postgresql://...
    improv db upgrade      # reads IMPROV_DATABASE_URL from environment
    improv schema sync     # columnar store; reads IMPROV_* from environment

Run both before serving. Both are idempotent and exit non-zero on failure, so
a deployment can gate the API on them completing.
"""

from __future__ import annotations

from pathlib import Path

import click


@click.group()
def cli() -> None:
    """improv — image provenance management tools."""


@cli.group()
def db() -> None:
    """Database management commands."""


@db.command()
@click.option(
    "--database-url",
    envvar="IMPROV_DATABASE_URL",
    required=True,
    help="SQLAlchemy database URL. Also read from IMPROV_DATABASE_URL env var.",
)
def upgrade(database_url: str) -> None:
    """Run database migrations to the latest version."""
    try:
        import alembic.command
        import alembic.config
    except ImportError:
        raise click.ClickException(
            "alembic is required for database migrations. "
            "Install with: pip install 'improv[service]'"
        )

    migrations_dir = str(Path(__file__).parent / "oltp" / "migrations")
    cfg = alembic.config.Config()
    cfg.set_main_option("script_location", migrations_dir)
    cfg.set_main_option("sqlalchemy.url", database_url)
    alembic.command.upgrade(cfg, "head")
    click.echo("Database upgraded to latest version.")


@cli.group()
def schema() -> None:
    """Columnar store schema management commands."""


@schema.command()
def sync() -> None:
    """Create the columnar tables the service needs.

    Reads the same IMPROV_* environment variables the service does, so it
    provisions exactly the store the workers will open — including the index
    table for every plugin named in IMPROV_PLUGINS.

    Idempotent: an existing table is checked for schema compatibility rather
    than recreated, and re-running at head does nothing. Run it again after
    adding a plugin to IMPROV_PLUGINS, or the new index table will not exist.

    This is the only thing that creates columnar tables. Service startup
    declares them but never creates them, because with WEB_CONCURRENCY > 1
    that would run once per worker concurrently and no backend offers an
    atomic create-if-absent.
    """
    from improv.config import load_config
    from improv.store.build import build_store
    from improv.store.tables import create_service_tables

    try:
        # include_storage=False: schema creation never touches the object
        # store, and building it would open an S3 client or a storage path
        # this container has no reason to have mounted.
        config = load_config(include_storage=False)
    except RuntimeError as exc:
        # Missing or malformed IMPROV_* variables — report the config problem
        # rather than a traceback from deep in a store constructor.
        raise click.ClickException(str(exc)) from None

    try:
        store = build_store(config)
        names = create_service_tables(store, config.plugins)
    except (RuntimeError, ValueError) as exc:
        # ValueError is the incompatible-schema-change path (a column removed
        # or retyped since the tables were created) — the case where a legible
        # message matters most, so it must not escape as a raw traceback.
        raise click.ClickException(str(exc)) from None

    for name in names:
        click.echo(f"  {name}")
    click.echo(f"Columnar schema synced ({len(names)} tables).")
