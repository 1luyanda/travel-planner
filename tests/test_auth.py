"""Regression tests for local account authentication."""

from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.api import auth_router
from backend.config import Settings
from backend.contracts import LoginRequest, RegisterRequest
from backend.models.user import UserDocument
from backend.services import (
    DuplicateEmailError,
    InvalidCredentialsError,
    UserService,
)
from backend.services.identity import hash_identity


IDENTITY_SECRET = "test-session-secret-value-32chars"


class FakeUserRepository:
    def __init__(self) -> None:
        self.users: dict[str, UserDocument] = {}

    async def find_user_by_email(self, email_normalized: str):
        return next(
            (
                user
                for user in self.users.values()
                if user.email_normalized == email_normalized
            ),
            None,
        )

    async def create_user(self, user: UserDocument) -> UserDocument:
        if user.id in self.users:
            raise RuntimeError("duplicate")
        self.users[user.id] = user
        return user

    async def get_user(self, user_id: str) -> UserDocument:
        from backend.repositories import RepositoryNotFoundError

        if user_id not in self.users:
            raise RepositoryNotFoundError("missing")
        return self.users[user_id]


def auth_settings() -> Settings:
    return Settings(
        cosmos_connection_string="placeholder",
        cosmos_database_name="TravelPlaner",
        frontend_origins=("http://localhost:5173",),
        api_auth_key="test-api-key",
        trusted_hosts=("testserver",),
        app_environment="test",
        auth_session_secret="test-session-secret-value-32chars",
    )


@pytest.mark.anyio
async def test_passwords_are_argon2id_hashed_and_duplicate_emails_are_rejected():
    service = UserService(FakeUserRepository(), identity_secret=IDENTITY_SECRET)
    request = {
        "email": "Person@example.com",
        "password": "a-long-demo-password",
        "display_name": "Person",
    }

    user = await service.register(RegisterRequest(**request))

    assert user.password_hash.startswith("$argon2id$")
    assert request["password"] not in user.password_hash
    assert user.email == hash_identity(IDENTITY_SECRET, "Person@example.com")
    assert user.email_normalized == hash_identity(IDENTITY_SECRET, "person@example.com")
    assert user.display_name == hash_identity(IDENTITY_SECRET, "Person")
    assert "Person@example.com" not in user.email
    assert "person@example.com" not in user.email_normalized
    assert user.display_name != "Person"

    with pytest.raises(DuplicateEmailError):
        await service.register(RegisterRequest(**request))

    logged_in = await service.authenticate(
        LoginRequest(email="Person@example.com", password="a-long-demo-password")
    )
    assert logged_in.id == user.id


@pytest.mark.anyio
async def test_login_failures_are_generic_for_unknown_and_wrong_password():
    service = UserService(FakeUserRepository(), identity_secret=IDENTITY_SECRET)

    await service.register(
        RegisterRequest(
            email="person@example.com",
            password="a-long-demo-password",
            display_name="Person",
        )
    )

    for request in (
        LoginRequest(email="missing@example.com", password="wrong-password"),
        LoginRequest(email="person@example.com", password="wrong-password"),
    ):
        with pytest.raises(InvalidCredentialsError):
            await service.authenticate(request)


def test_session_cookie_me_logout_and_account_isolation(monkeypatch):
    import backend.security as security

    repository = FakeUserRepository()
    service = UserService(repository, identity_secret=IDENTITY_SECRET)
    app = FastAPI()
    app.include_router(auth_router)
    app.state.user_service = service
    monkeypatch.setattr(security, "get_settings", auth_settings)

    api_headers = {"X-API-Key": "test-api-key"}
    with TestClient(app) as first_client:
        registered = first_client.post(
            "/api/auth/register",
            headers=api_headers,
            json={
                "email": "first@example.com",
                "password": "a-long-demo-password",
                "display_name": "First",
            },
        )
        assert registered.status_code == 201
        cookie = registered.headers["set-cookie"]
        assert "HttpOnly" in cookie
        assert "SameSite=lax" in cookie
        assert "Secure" not in cookie

        me = first_client.get("/api/auth/me", headers=api_headers)
        assert me.status_code == 200
        assert me.json()["email"] == "first@example.com"
        assert me.json()["display_name"] == "First"
        assert "password" not in me.text
        stored = next(iter(repository.users.values()))
        assert stored.email != "first@example.com"
        assert stored.email_normalized != "first@example.com"
        assert stored.display_name != "First"

        with TestClient(app) as second_client:
            second_client.post(
                "/api/auth/register",
                headers=api_headers,
                json={
                    "email": "second@example.com",
                    "password": "another-long-password",
                    "display_name": "Second",
                },
            )
            assert second_client.get(
                "/api/auth/me",
                headers=api_headers,
            ).json()["email"] == "second@example.com"

        logged_out = first_client.post(
            "/api/auth/logout",
            headers=api_headers,
        )
        assert logged_out.status_code == 204
        assert first_client.get(
            "/api/auth/me",
            headers=api_headers,
        ).status_code == 401


def test_invalid_login_does_not_disclose_account_state(monkeypatch):
    import backend.security as security

    app = FastAPI()
    app.include_router(auth_router)
    app.state.user_service = UserService(
        FakeUserRepository(),
        identity_secret=IDENTITY_SECRET,
    )
    monkeypatch.setattr(security, "get_settings", auth_settings)

    response = TestClient(app).post(
        "/api/auth/login",
        headers={"X-API-Key": "test-api-key"},
        json={"email": "missing@example.com", "password": "wrong-password"},
    )
    assert response.status_code == 401
    assert response.json()["detail"] == "Invalid email or password."
