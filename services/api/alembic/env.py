"""
Alembic environment — configures the migration context.

Two modes
---------
offline
    Generates SQL to stdout without a live database connection.
    Useful for reviewing what a migration *would* do.

online
    Connects to the database and applies migrations directly.
    Used by ``alembic upgrade head`` and ``alembic downgrade``.

The DATABASE_URL is read from ``app.core.config.settings`` which in turn
loads it from the environment (or a ``.env`` file in ``services/api/``).
This keeps credentials out of ``alembic.ini``.
"""

from logging.config import fileConfig

from sqlalchemy import engine_from_config, pool

from alembic import context

# ---------------------------------------------------------------------------
# Load project settings and register all models with Base.metadata
# ---------------------------------------------------------------------------

# app.models must be imported before we reference Base.metadata so that
# all ORM classes are registered.  The import also transitively imports
# app.db.base (where Base is defined).
import app.models  # noqa: F401 — side-effect import registers all models
from app.db.base import Base
from app.core.config import settings

# ---------------------------------------------------------------------------
# Alembic configuration
# ---------------------------------------------------------------------------

# this is the Alembic Config object, which provides access to the values
# within the alembic.ini file.
config = context.config

# Override the sqlalchemy.url from alembic.ini with the value from settings
# so that credentials come from the environment, not from the ini file.
config.set_main_option("sqlalchemy.url", settings.DATABASE_URL)

# Interpret the config file for Python logging.
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# Target metadata tells Alembic what the schema *should* look like so it
# can autogenerate accurate diffs.
target_metadata = Base.metadata


# ---------------------------------------------------------------------------
# Migration runners
# ---------------------------------------------------------------------------


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode.

    In this scenario we don't need an actual database connection — Alembic
    generates the SQL and writes it to stdout or a file.
    """
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        # Emit CREATE TYPE statements for native Postgres enums.
        include_schemas=False,
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Run migrations in 'online' mode with a live database connection."""
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
        )

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
