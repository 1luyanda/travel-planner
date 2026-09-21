"""Local account registration and password authentication."""

from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

from pwdlib import PasswordHash

from backend.contracts import LoginRequest, RegisterRequest
from backend.models.user import UserDocument, UserResponse
from backend.repositories import (
    CosmosDestinationRepository,
    RepositoryConflictError,
    RepositoryNotFoundError,
)


class DuplicateEmailError(RuntimeError):
    """Raised when an email already belongs to an account."""


class InvalidCredentialsError(RuntimeError):
    """Raised without revealing whether email or password was incorrect."""


class UserService:
    """Owns local user creation, lookup, and password verification."""

    def __init__(self, repository: CosmosDestinationRepository) -> None:
        self._repository = repository
        self._password_hash = PasswordHash.recommended()
        self._dummy_hash = self._password_hash.hash(
            "unavailable-password-for-timing-equality"
        )

    async def register(self, body: RegisterRequest) -> UserDocument:
        email_normalized = str(body.email).strip().lower()
        existing = await self._repository.find_user_by_email(email_normalized)
        if existing is not None:
            raise DuplicateEmailError

        now = datetime.now(timezone.utc)
        user = UserDocument(
            id=str(uuid4()),
            email=body.email,
            email_normalized=email_normalized,
            display_name=body.display_name,
            password_hash=self._password_hash.hash(body.password),
            created_at=now,
            updated_at=now,
        )
        try:
            return await self._repository.create_user(user)
        except RepositoryConflictError as error:
            raise DuplicateEmailError from error

    async def authenticate(self, body: LoginRequest) -> UserDocument:
        email_normalized = str(body.email).strip().lower()
        user = await self._repository.find_user_by_email(email_normalized)
        password_hash = user.password_hash if user else self._dummy_hash

        try:
            password_matches = self._password_hash.verify(
                body.password,
                password_hash,
            )
        except Exception:
            password_matches = False

        if user is None or not password_matches:
            raise InvalidCredentialsError
        return user

    async def get_by_id(self, user_id: str) -> UserDocument:
        try:
            return await self._repository.get_user(user_id)
        except RepositoryNotFoundError:
            raise InvalidCredentialsError from None

    @staticmethod
    def response_for(user: UserDocument) -> UserResponse:
        return UserResponse(
            id=user.id,
            email=user.email,
            display_name=user.display_name,
            created_at=user.created_at,
        )
