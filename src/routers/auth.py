"""Authentication API endpoints for Medical Billing Copilot.

Implements login, logout, register, and token refresh endpoints.

Requirements: 7.1, 7.2
"""

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session as DBSession

from src.db.config import get_db
from src.schemas.auth import AuthResult, LoginRequest, RefreshRequest, RegisterRequest
from src.services import (
    AccountLockedError,
    AuthService,
    InvalidCredentialsError,
    InvalidTokenError,
    TokenExpiredError,
    UserAlreadyExistsError,
)

router = APIRouter(prefix="/api/auth", tags=["auth"])
security = HTTPBearer()


def get_auth_service(db: DBSession = Depends(get_db)) -> AuthService:
    """Get the auth service instance."""
    return AuthService(db)


@router.post("/register", response_model=AuthResult)
async def register(
    request: RegisterRequest,
    auth_service: AuthService = Depends(get_auth_service),
) -> AuthResult:
    """Register a new user account.

    Args:
        request: Registration request with email and password

    Returns:
        AuthResult with access token, refresh token, and user profile
    """
    try:
        return auth_service.register(
            email=request.email,
            password=request.password,
            organization_id=request.organization_id,
        )
    except UserAlreadyExistsError:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Email is already registered",
        )


@router.post("/login", response_model=AuthResult)
async def login(
    request: LoginRequest,
    auth_service: AuthService = Depends(get_auth_service),
) -> AuthResult:
    """Authenticate a user and return tokens.

    Args:
        request: Login request with email and password

    Returns:
        AuthResult with access token, refresh token, and user profile
    """
    try:
        return auth_service.login(email=request.email, password=request.password)
    except InvalidCredentialsError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    except AccountLockedError:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Account is temporarily locked due to too many failed login attempts",
        )


@router.post("/logout")
async def logout(
    credentials: HTTPAuthorizationCredentials = Depends(security),
    auth_service: AuthService = Depends(get_auth_service),
) -> dict:
    """Log out the current user.

    Returns:
        Success message
    """
    try:
        token_payload = auth_service.validate_token(credentials.credentials)
        auth_service.logout(token_payload.user_id)
        return {"message": "Successfully logged out"}
    except (TokenExpiredError, InvalidTokenError):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
            headers={"WWW-Authenticate": "Bearer"},
        )


@router.post("/refresh", response_model=AuthResult)
async def refresh_token(
    request: RefreshRequest,
    auth_service: AuthService = Depends(get_auth_service),
) -> AuthResult:
    """Refresh an access token using a refresh token.

    Args:
        request: Refresh request with refresh token

    Returns:
        AuthResult with new access token, refresh token, and user profile
    """
    try:
        return auth_service.refresh_token(request.refresh_token)
    except TokenExpiredError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Refresh token has expired",
            headers={"WWW-Authenticate": "Bearer"},
        )
    except InvalidTokenError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid refresh token",
            headers={"WWW-Authenticate": "Bearer"},
        )
    except AccountLockedError:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Account is temporarily locked",
        )
