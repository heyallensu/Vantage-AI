"""Resolve PostgreSQL connection URLs from local configuration or Secrets Manager."""

import json
from collections.abc import Mapping
from urllib.parse import quote

import boto3


def build_database_url(
    secret: Mapping[str, object],
    *,
    default_database: str = "",
) -> str:
    """Build an escaped PostgreSQL URL from the RDS managed-secret contract."""
    username = str(secret.get("username", ""))
    password = str(secret.get("password", ""))
    host = str(secret.get("host", ""))
    database = str(secret.get("dbname") or secret.get("database") or default_database)
    try:
        port = int(secret.get("port", 5432))
    except (TypeError, ValueError) as exc:
        raise RuntimeError("Database secret port must be an integer") from exc

    missing = [
        name
        for name, value in {
            "username": username,
            "password": password,
            "host": host,
            "database": database,
        }.items()
        if not value
    ]
    if missing:
        raise RuntimeError(
            f"Database secret is missing required fields: {', '.join(sorted(missing))}"
        )

    return (
        f"postgresql://{quote(username, safe='')}:{quote(password, safe='')}@"
        f"{host}:{port}/{quote(database, safe='')}"
    )


def resolve_database_url(
    *,
    database_url: str,
    secret_arn: str,
    database_name: str,
    region: str | None = None,
    client=None,
) -> str:
    """Prefer an explicit local URL; otherwise read the managed RDS secret."""
    if database_url:
        return database_url
    if not secret_arn:
        raise RuntimeError("DATABASE_URL or DB_SECRET_ARN is required")

    secrets_client = client or boto3.client("secretsmanager", region_name=region)
    response = secrets_client.get_secret_value(SecretId=secret_arn)
    secret_string = response.get("SecretString")
    if not secret_string:
        raise RuntimeError("Database secret must contain SecretString JSON")
    try:
        secret = json.loads(secret_string)
    except (TypeError, json.JSONDecodeError) as exc:
        raise RuntimeError("Database secret must contain valid JSON") from exc
    if not isinstance(secret, dict):
        raise RuntimeError("Database secret JSON must be an object")
    return build_database_url(secret, default_database=database_name)
