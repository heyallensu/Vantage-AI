"""PostgreSQL migration tests for the complete Alembic history."""

import sqlalchemy as sa
from pytest import MonkeyPatch
from sqlalchemy import create_engine, inspect

from alembic import command
from alembic.config import Config
from scripts.database.migrate import upgrade_database


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
    document_columns = {column["name"] for column in inspector.get_columns("documents")}
    assert "raw_csv" not in document_columns
    assert {"object_key", "checksum_sha256", "trace_id", "processing_attempts"} <= document_columns

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
    monkeypatch: MonkeyPatch,
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

    # This hostile process value is deliberately visible to alembic/env.py.
    # Config.attributes must keep the explicit migration target authoritative.
    monkeypatch.setenv(
        "DATABASE_URL",
        "postgresql://wrong:wrong@127.0.0.1:1/wrong",
    )
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
    document_columns = {
        column["name"] for column in inspect(migrated_engine).get_columns("documents")
    }
    assert "raw_csv" not in document_columns
    migrated_engine.dispose()
