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
from backend.services.identity import hash_identity


class DuplicateEmailError(RuntimeError):
    """Raised when an email already belongs to an account."""


class InvalidCredentialsError(RuntimeError):
    """Raised without revealing whether email or password was incorrect."""


class UserService:
    """Owns local user creation, lookup, and password verification."""

    def __init__(
        self,
        repository: CosmosDestinationRepository,
        *,
        identity_secret: str,
    ) -> None:
        if not identity_secret:
            raise ValueError("identity_secret is required to hash user identity fields.")
        self._repository = repository
        self._identity_secret = identity_secret
        self._password_hash = PasswordHash.recommended()
        self._dummy_hash = self._password_hash.hash(
            "unavailable-password-for-timing-equality"
        )

    def hash_email(self, email: str) -> str:
        return hash_identity(self._identity_secret, str(email).strip())

    def hash_email_normalized(self, email: str) -> str:
        return hash_identity(self._identity_secret, str(email).strip().lower())

    def hash_display_name(self, display_name: str) -> str:
        return hash_identity(self._identity_secret, display_name)

    async def register(self, body: RegisterRequest) -> UserDocument:
        email_normalized = str(body.email).strip().lower()
        existing = await self._repository.find_user_by_email(
            self.hash_email_normalized(email_normalized)
        )
        if existing is not None:
            raise DuplicateEmailError

        now = datetime.now(timezone.utc)
        user = UserDocument(
            id=str(uuid4()),
            email=self.hash_email(str(body.email).strip()),
            email_normalized=self.hash_email_normalized(email_normalized),
            display_name=self.hash_display_name(body.display_name),
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
        user = await self._repository.find_user_by_email(
            self.hash_email_normalized(email_normalized)
        )
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
    def response_for(
        user: UserDocument,
        *,
        email: str,
        display_name: str,
    ) -> UserResponse:
        return UserResponse(
            id=user.id,
            email=email,
            display_name=display_name,
            created_at=user.created_at,
        )
