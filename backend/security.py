"""Request authentication and security helpers for the FastAPI boundary."""

from __future__ import annotations

from secrets import compare_digest

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import APIKeyHeader

from backend.config import ConfigurationError, get_settings

api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)


def require_api_key(
    request: Request,
    provided_key: str | None = Depends(api_key_header),
) -> None:
    """Require the server-side proxy API key.

    The key is intended for a gateway or development proxy. It must never be
    embedded in the browser bundle.
    """

    try:
        settings = get_settings()
    except ConfigurationError as error:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="API authentication is not configured.",
        ) from error

    configured_keys = tuple(
        key
        for key in (
            settings.api_auth_key,
            settings.api_auth_key_previous,
        )
        if key
    )
    if not configured_keys:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="API authentication is not configured.",
        )

    header_values = request.headers.getlist("x-api-key")
    if len(header_values) != 1 or provided_key is None or not provided_key.strip():
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing API key.",
            headers={"WWW-Authenticate": "ApiKey"},
        )

    if not any(
        compare_digest(provided_key.strip(), configured)
        for configured in configured_keys
    ):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid API key.",
            headers={"WWW-Authenticate": "ApiKey"},
        )
