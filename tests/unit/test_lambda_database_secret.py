"""Lambda managed database-secret resolution tests."""

import importlib
import json
from unittest.mock import Mock

from pytest import MonkeyPatch

handler = importlib.import_module("lambda.processor.handler")


def test_lambda_resolves_managed_database_secret(monkeypatch: MonkeyPatch) -> None:
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.setenv("DB_SECRET_ARN", "arn:aws:secretsmanager:region:account:secret:db")
    monkeypatch.setenv("DB_NAME", "vantage")
    client = Mock()
    client.get_secret_value.return_value = {
        "SecretString": json.dumps(
            {
                "username": "lambda-user",
                "password": "p@ss/word",
                "host": "db.internal",
                "port": 5432,
            }
        )
    }

    resolved = handler.resolve_database_url(client=client)

    assert resolved == "postgresql://lambda-user:p%40ss%2Fword@db.internal:5432/vantage"


def test_lambda_connection_prefers_local_database_url(monkeypatch: MonkeyPatch) -> None:
    local_url = "postgresql://local:local@db:5432/vantage"
    monkeypatch.setenv("DATABASE_URL", local_url)
    connect = Mock()
    monkeypatch.setattr(handler.psycopg2, "connect", connect)

    handler.get_connection()

    connect.assert_called_once_with(local_url)
