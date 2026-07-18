import os
import uuid
from collections.abc import Generator

import psycopg2
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from psycopg2 import sql
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

os.environ.setdefault("AWS_DEFAULT_REGION", "ap-southeast-2")
os.environ.setdefault("AWS_EC2_METADATA_DISABLED", "true")
os.environ.setdefault("ENV", "local")
os.environ.setdefault("API_KEY", "test-api-key")

from app.models.record import Base, get_db  # noqa: E402

MIGRATION_ADMIN_DATABASE_URL = os.getenv(
    "MIGRATION_TEST_ADMIN_URL",
    "postgresql://vantage:vantage@localhost:5432/postgres",
)


@pytest.fixture
def migration_database_url() -> Generator[str, None, None]:
    """Create an isolated PostgreSQL database when the local service is available."""
    database_name = f"vantage_migration_{uuid.uuid4().hex}"

    try:
        admin_connection = psycopg2.connect(MIGRATION_ADMIN_DATABASE_URL)
    except psycopg2.OperationalError:
        pytest.skip("PostgreSQL migration test database is not available")

    admin_connection.autocommit = True
    with admin_connection.cursor() as cursor:
        cursor.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(database_name)))

    database_url = MIGRATION_ADMIN_DATABASE_URL.rsplit("/", 1)[0] + f"/{database_name}"
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


@pytest.fixture
def db_session() -> Generator[Session, None, None]:
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    testing_session = sessionmaker(bind=engine)
    Base.metadata.create_all(bind=engine)
    session = testing_session()

    try:
        yield session
    finally:
        session.close()
        Base.metadata.drop_all(bind=engine)
        engine.dispose()


@pytest.fixture
def test_app(db_session: Session) -> Generator[FastAPI, None, None]:
    from app.main import create_app

    application = create_app()

    def override_get_db() -> Generator[Session, None, None]:
        yield db_session

    application.dependency_overrides[get_db] = override_get_db
    yield application
    application.dependency_overrides.clear()


@pytest.fixture
def client(test_app: FastAPI) -> Generator[TestClient, None, None]:
    with TestClient(test_app, headers={"X-API-Key": "test-api-key"}) as test_client:
        yield test_client
