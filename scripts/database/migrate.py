"""Upgrade fresh or recognized legacy Vantage AI databases with Alembic."""

import os

from sqlalchemy import create_engine, inspect

from alembic import command
from alembic.config import Config
from app.core.database import resolve_database_url

LEGACY_SCHEMA_COLUMNS = {
    "documents": {
        "id",
        "filename",
        "status",
        "raw_csv",
        "error_msg",
        "created_at",
        "updated_at",
    },
    "records": {
        "id",
        "document_id",
        "date",
        "description",
        "amount",
        "category",
        "created_at",
    },
}


def _is_recognized_legacy_schema(database_url: str) -> bool:
    engine = create_engine(database_url, pool_pre_ping=True)
    try:
        inspector = inspect(engine)
        table_names = set(inspector.get_table_names())
        if not set(LEGACY_SCHEMA_COLUMNS) <= table_names:
            return False
        return all(
            required_columns
            <= {column["name"] for column in inspector.get_columns(table_name)}
            for table_name, required_columns in LEGACY_SCHEMA_COLUMNS.items()
        )
    finally:
        engine.dispose()


def upgrade_database(
    *,
    database_url: str | None = None,
    config_path: str = "alembic.ini",
) -> None:
    """Upgrade a fresh database or adopt the known pre-Alembic schema."""
    resolved_url = resolve_database_url(
        database_url=database_url or os.getenv("DATABASE_URL", ""),
        secret_arn=os.getenv("DB_SECRET_ARN", ""),
        database_name=os.getenv("DB_NAME", "vantage"),
        region=os.getenv("AWS_DEFAULT_REGION"),
    )

    config = Config(config_path)
    config.set_main_option("sqlalchemy.url", resolved_url)

    engine = create_engine(resolved_url, pool_pre_ping=True)
    try:
        table_names = set(inspect(engine).get_table_names())
    finally:
        engine.dispose()

    if "alembic_version" not in table_names and table_names:
        if not _is_recognized_legacy_schema(resolved_url):
            raise RuntimeError(
                "Database has unmanaged tables that do not match the recognized legacy schema"
            )
        command.stamp(config, "0001_initial_schema")

    command.upgrade(config, "head")


if __name__ == "__main__":
    upgrade_database()
