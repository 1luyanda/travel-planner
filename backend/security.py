"""Request authentication and security helpers for the FastAPI boundary."""

from __future__ import annotations

import base64
import binascii
import hashlib
import hmac
import json
from secrets import compare_digest
from time import time

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import APIKeyHeader
from starlette.responses import Response

from backend.config import ConfigurationError, get_settings
from backend.services.users import InvalidCredentialsError

api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)
SESSION_COOKIE_NAME = "travel_planner_session"


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


def _session_secret() -> bytes:
    try:
        secret = get_settings().auth_session_secret
    except ConfigurationError as error:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Authentication is not configured.",
        ) from error
    if not secret:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Authentication is not configured.",
        )
    return secret.encode("utf-8")


def _encode(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).rstrip(b"=").decode("ascii")


def _decode(value: str) -> bytes:
    padding = "=" * (-len(value) % 4)
    return base64.urlsafe_b64decode(value + padding)


def create_session_value(
    user_id: str,
    *,
    email: str = "",
    display_name: str = "",
) -> str:
    """Create a signed, short-lived cookie value with user ID and profile fields."""

    settings = get_settings()
    payload = json.dumps(
        {
            "sub": user_id,
            "email": email,
            "name": display_name,
            "exp": int(time()) + settings.auth_session_ttl_seconds,
        },
        separators=(",", ":"),
    ).encode("utf-8")
    encoded_payload = _encode(payload)
    signature = hmac.new(
        _session_secret(),
        encoded_payload.encode("ascii"),
        hashlib.sha256,
    ).digest()
    return f"{encoded_payload}.{_encode(signature)}"


def set_session_cookie(
    response: Response,
    user_id: str,
    *,
    email: str = "",
    display_name: str = "",
) -> None:
    settings = get_settings()
    response.set_cookie(
        key=settings.auth_cookie_name or SESSION_COOKIE_NAME,
        value=create_session_value(user_id, email=email, display_name=display_name),
        max_age=settings.auth_session_ttl_seconds,
        httponly=True,
        secure=settings.auth_cookie_secure,
        samesite="lax",
        path="/",
    )


def clear_session_cookie(response: Response) -> None:
    settings = get_settings()
    response.delete_cookie(
        key=settings.auth_cookie_name or SESSION_COOKIE_NAME,
        httponly=True,
        secure=settings.auth_cookie_secure,
        samesite="lax",
        path="/",
    )


def _session_payload(request: Request) -> dict:
    settings = get_settings()
    cookie_name = settings.auth_cookie_name or SESSION_COOKIE_NAME
    raw_value = request.cookies.get(cookie_name)
    if not raw_value:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required.",
            headers={"WWW-Authenticate": "Cookie"},
        )

    try:
        encoded_payload, encoded_signature = raw_value.split(".", 1)
        expected_signature = hmac.new(
            _session_secret(),
            encoded_payload.encode("ascii"),
            hashlib.sha256,
        ).digest()
        if not compare_digest(
            _encode(expected_signature),
            encoded_signature,
        ):
            raise ValueError
        payload = json.loads(_decode(encoded_payload))
        user_id = payload["sub"]
        expires_at = int(payload["exp"])
        if not isinstance(user_id, str) or not user_id:
            raise ValueError
        if expires_at <= int(time()):
            raise ValueError
        email = payload.get("email") if isinstance(payload.get("email"), str) else ""
        display_name = payload.get("name") if isinstance(payload.get("name"), str) else ""
        return {
            "sub": user_id,
            "email": email,
            "name": display_name,
        }
    except (
        ValueError,
        KeyError,
        TypeError,
        json.JSONDecodeError,
        binascii.Error,
        UnicodeError,
    ):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required.",
            headers={"WWW-Authenticate": "Cookie"},
        ) from None


def _session_user_id(request: Request) -> str:
    return _session_payload(request)["sub"]


async def require_user(request: Request):
    """Resolve the authenticated user from the signed session cookie."""

    session = _session_payload(request)
    user_service = getattr(request.app.state, "user_service", None)
    if user_service is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Authentication service is unavailable.",
        )
    try:
        user = await user_service.get_by_id(session["sub"])
    except InvalidCredentialsError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required.",
            headers={"WWW-Authenticate": "Cookie"},
        ) from None
    email = session["email"]
    display_name = session["name"] or (email.split("@", 1)[0] if email else "")
    if email:
        user = user.model_copy(
            update={
                "email": email,
                "display_name": display_name or user.display_name,
            }
        )
    return user
