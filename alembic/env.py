"""Alembic migration environment for Vantage AI."""

import os
from logging.config import fileConfig

from sqlalchemy import engine_from_config, pool

from alembic import context
from app.core.database import resolve_database_url
from app.models.record import Base

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

database_url = config.attributes.get("database_url")
if not isinstance(database_url, str) or not database_url:
    runtime_url = os.getenv("DATABASE_URL", "")
    secret_arn = os.getenv("DB_SECRET_ARN", "")
    if runtime_url or secret_arn:
        database_url = resolve_database_url(
            database_url=runtime_url,
            secret_arn=secret_arn,
            database_name=os.getenv("DB_NAME", "vantage"),
            region=os.getenv("AWS_DEFAULT_REGION"),
        )
    else:
        database_url = config.get_main_option("sqlalchemy.url")
config.set_main_option("sqlalchemy.url", database_url)

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    """Run migrations without creating a database connection."""
    context.configure(
        url=config.get_main_option("sqlalchemy.url"),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Run migrations against a live database connection."""
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            compare_type=True,
        )

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
