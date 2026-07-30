"""API-key authentication dependency for protected endpoints."""

import hmac
from typing import Annotated

from fastapi import Depends, Header, HTTPException

from app.core.config import Settings, get_settings


def require_api_key(
    x_api_key: Annotated[str | None, Header(alias="X-API-Key")] = None,
    settings: Settings = Depends(get_settings),
) -> None:
    """Reject missing or invalid keys using a timing-safe comparison."""
    supplied_key = (x_api_key or "").encode("utf-8")
    expected_key = settings.api_key.encode("utf-8")
    if not supplied_key or not hmac.compare_digest(supplied_key, expected_key):
        raise HTTPException(status_code=401, detail="Invalid or missing API key")
