"""Alembic environment wired to the application's settings and metadata."""

from __future__ import annotations

import sys
from logging.config import fileConfig
from pathlib import Path

from sqlalchemy import engine_from_config, pool

from alembic import context

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.core.config import get_settings  # noqa: E402
from app.db import models  # noqa: E402,F401 - registers every table on Base.metadata
from app.db.base import Base  # noqa: E402

config = context.config
config.set_main_option("sqlalchemy.url", get_settings().database_url.replace("%", "%%"))

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def _configure(url: str | None, connection=None) -> None:
    context.configure(
        url=url,
        connection=connection,
        target_metadata=target_metadata,
        literal_binds=url is not None,
        render_as_batch=True,
        compare_type=True,
        # Defaults live on the Python side; comparing them only produces autogenerate noise.
        compare_server_default=False,
        dialect_opts={"paramstyle": "named"},
    )


def run_migrations_offline() -> None:
    _configure(config.get_main_option("sqlalchemy.url"))
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    with connectable.connect() as connection:
        # Alembic 1.14 treats an engine-less url argument as offline mode.
        _configure(None, connection)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
