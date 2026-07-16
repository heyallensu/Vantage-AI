"""API-key authentication dependency for portfolio-facing endpoints."""

import hmac
from typing import Annotated

from fastapi import Depends, Header, HTTPException

from app.core.config import Settings, get_settings


def require_api_key(
    x_api_key: Annotated[str | None, Header(alias="X-API-Key")] = None,
    settings: Settings = Depends(get_settings),
) -> None:
    """Reject missing or invalid keys using a timing-safe comparison."""
    supplied_key = x_api_key or ""
    if not supplied_key or not hmac.compare_digest(supplied_key, settings.api_key):
        raise HTTPException(status_code=401, detail="Invalid or missing API key")
