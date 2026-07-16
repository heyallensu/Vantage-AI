"""PostgreSQL migration tests for the complete Alembic history."""

import os
import uuid
from collections.abc import Generator

import psycopg2
import pytest
import sqlalchemy as sa
from psycopg2 import sql
from sqlalchemy import create_engine, inspect

from alembic import command
from alembic.config import Config
from scripts.database.migrate import upgrade_database

ADMIN_DATABASE_URL = os.getenv(
    "MIGRATION_TEST_ADMIN_URL",
    "postgresql://vantage:vantage@localhost:5432/postgres",
)


@pytest.fixture
def migration_database_url() -> Generator[str, None, None]:
    database_name = f"vantage_migration_{uuid.uuid4().hex}"

    try:
        admin_connection = psycopg2.connect(ADMIN_DATABASE_URL)
    except psycopg2.OperationalError:
        pytest.skip("PostgreSQL migration test database is not available")

    admin_connection.autocommit = True
    with admin_connection.cursor() as cursor:
        cursor.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(database_name)))

    database_url = ADMIN_DATABASE_URL.rsplit("/", 1)[0] + f"/{database_name}"
    try:
        yield database_url
    finally:
        with admin_connection.cursor() as cursor:
            cursor.execute(
                "SELECT pg_terminate_backend(pid) FROM pg_stat_activity "
                "WHERE datname = %s AND pid <> pg_backend_pid()",
                (database_name,),
            )
            cursor.execute(sql.SQL("DROP DATABASE {}").format(sql.Identifier(database_name)))
        admin_connection.close()


def test_migrations_upgrade_downgrade_and_restore_schema(
    migration_database_url: str,
) -> None:
    config = Config("alembic.ini")
    config.set_main_option("sqlalchemy.url", migration_database_url)

    command.upgrade(config, "head")

    engine = create_engine(migration_database_url)
    inspector = inspect(engine)
    assert set(inspector.get_table_names()) == {"alembic_version", "documents", "records"}

    document_indexes = {index["name"] for index in inspector.get_indexes("documents")}
    record_indexes = {index["name"] for index in inspector.get_indexes("records")}
    assert {"ix_documents_created_at", "ix_documents_status"} <= document_indexes
    assert {
        "ix_records_category",
        "ix_records_created_at",
        "ix_records_document_id",
    } <= record_indexes

    foreign_keys = inspector.get_foreign_keys("records")
    assert any(
        key["referred_table"] == "documents" and key["constrained_columns"] == ["document_id"]
        for key in foreign_keys
    )
    check_constraints = inspector.get_check_constraints("documents")
    assert any(constraint["name"] == "ck_documents_status" for constraint in check_constraints)

    command.downgrade(config, "base")
    assert inspect(engine).get_table_names() == ["alembic_version"]

    command.upgrade(config, "head")
    assert set(inspect(engine).get_table_names()) == {
        "alembic_version",
        "documents",
        "records",
    }
    engine.dispose()


def test_migrations_adopt_legacy_schema_without_losing_records(
    migration_database_url: str,
) -> None:
    config = Config("alembic.ini")
    config.set_main_option("sqlalchemy.url", migration_database_url)
    command.upgrade(config, "0001_initial_schema")

    engine = create_engine(migration_database_url)
    with engine.begin() as connection:
        connection.execute(
            sa.text(
                "INSERT INTO documents (id, filename, status, raw_csv) "
                "VALUES ('legacy-doc', 'legacy.csv', 'completed', 'date,amount')"
            )
        )
        connection.execute(
            sa.text(
                "INSERT INTO records (id, document_id, amount, category) "
                "VALUES ('legacy-record', 'legacy-doc', 42, 'Legacy')"
            )
        )
        connection.execute(sa.text("DROP TABLE alembic_version"))
    engine.dispose()

    upgrade_database(database_url=migration_database_url)

    migrated_engine = create_engine(migration_database_url)
    with migrated_engine.connect() as connection:
        assert connection.execute(sa.text("SELECT count(*) FROM documents")).scalar_one() == 1
        assert connection.execute(sa.text("SELECT count(*) FROM records")).scalar_one() == 1
        assert (
            connection.execute(
                sa.text("SELECT processing_attempts FROM documents WHERE id = 'legacy-doc'")
            ).scalar_one()
            == 0
        )
    assert set(inspect(migrated_engine).get_table_names()) == {
        "alembic_version",
        "documents",
        "records",
    }
    migrated_engine.dispose()
