"""Local account registration, login, logout, and session inspection."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status

from backend.contracts import AuthResponse, LoginRequest, RegisterRequest
from backend.models.user import UserDocument, UserResponse
from backend.repositories import (
    RepositoryError,
)
from backend.security import (
    clear_session_cookie,
    require_api_key,
    require_user,
    set_session_cookie,
)
from backend.services import (
    DuplicateEmailError,
    InvalidCredentialsError,
    UserService,
)

router = APIRouter(
    prefix="/api/auth",
    dependencies=[Depends(require_api_key)],
)


def _user_service(request: Request) -> UserService:
    return request.app.state.user_service


def _user_response(user: UserDocument) -> UserResponse:
    return UserService.response_for(user)


@router.post(
    "/register",
    response_model=AuthResponse,
    status_code=status.HTTP_201_CREATED,
)
async def register(
    body: RegisterRequest,
    response: Response,
    user_service: UserService = Depends(_user_service),
) -> AuthResponse:
    try:
        user = await user_service.register(body)
    except DuplicateEmailError as error:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="An account with that email already exists.",
        ) from error
    except RepositoryError as error:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Account storage is temporarily unavailable.",
        ) from error

    set_session_cookie(response, user.id)
    return AuthResponse(user=_user_response(user))


@router.post("/login", response_model=AuthResponse)
async def login(
    body: LoginRequest,
    response: Response,
    user_service: UserService = Depends(_user_service),
) -> AuthResponse:
    try:
        user = await user_service.authenticate(body)
    except InvalidCredentialsError as error:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password.",
            headers={"WWW-Authenticate": "Cookie"},
        ) from error
    except RepositoryError as error:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Authentication service is temporarily unavailable.",
        ) from error

    set_session_cookie(response, user.id)
    return AuthResponse(user=_user_response(user))


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(response: Response) -> Response:
    clear_session_cookie(response)
    response.status_code = status.HTTP_204_NO_CONTENT
    return response


@router.get("/me", response_model=UserResponse)
async def me(user: UserDocument = Depends(require_user)) -> UserResponse:
    return _user_response(user)
