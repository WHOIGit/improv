"""improv CLI — entry point for database management commands.

Usage:
    improv db upgrade --database-url postgresql://...
    improv db upgrade  # reads IMPROV_DATABASE_URL from environment
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
