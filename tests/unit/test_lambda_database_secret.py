"""Lambda managed database-secret resolution tests."""

import importlib
import json
from unittest.mock import Mock

import pytest
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
    client.get_secret_value.assert_called_once_with(
        SecretId="arn:aws:secretsmanager:region:account:secret:db"
    )


def test_lambda_combines_managed_credentials_with_rds_endpoint(
    monkeypatch: MonkeyPatch,
) -> None:
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.setenv("DB_SECRET_ARN", "arn:aws:secretsmanager:region:account:secret:db")
    monkeypatch.setenv("DB_HOST", "db.internal")
    monkeypatch.setenv("DB_PORT", "5432")
    monkeypatch.setenv("DB_NAME", "vantage")
    client = Mock()
    client.get_secret_value.return_value = {
        "SecretString": json.dumps(
            {"username": "lambda-user", "password": "p@ss/word"}
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


def test_lambda_csv_parser_normalizes_whitespace_padded_headers() -> None:
    records = handler.parse_csv(
        " date , description , amount , category \n"
        "2024-01-01,Service,42,Operations\n",
        "document-123",
    )

    assert records[0]["date"] == "2024-01-01"
    assert records[0]["description"] == "Service"
    assert records[0]["amount"] == 42.0
    assert records[0]["category"] == "Operations"


@pytest.mark.parametrize("amount", ["NaN", "Infinity", "-Infinity"])
def test_lambda_csv_parser_rejects_non_finite_amount(amount: str) -> None:
    csv_text = f"date,description,amount,category\n2024-01-01,Bad,{amount},Unknown\n"

    with pytest.raises(ValueError, match="Amount must be finite on row 2"):
        handler.parse_csv(csv_text, "document-123")
