"""Authentication schemas for Medical Billing Copilot."""

import re
from datetime import datetime
from typing import Annotated, Optional

from pydantic import AfterValidator, BaseModel, ConfigDict, Field

from src.schemas.common import UserRole

# Email validation pattern
EMAIL_PATTERN = r"^[^\s@]+@[^\s@]+\.[^\s@]+$"


def _validate_email(v: str) -> str:
    """Validate email format."""
    if not re.match(EMAIL_PATTERN, v):
        raise ValueError("Invalid email format")
    return v


# Reusable email type with validation
ValidatedEmail = Annotated[str, AfterValidator(_validate_email)]


class UserProfile(BaseModel):
    """User profile information."""

    model_config = ConfigDict(from_attributes=True)

    id: str = Field(..., description="Unique user identifier")
    email: ValidatedEmail = Field(..., description="User email address")
    organization_id: Optional[str] = Field(None, description="Organization identifier")
    role: UserRole = Field(default=UserRole.USER, description="User role")


class LoginRequest(BaseModel):
    """Login request payload."""

    email: ValidatedEmail = Field(..., description="User email address")
    password: str = Field(
        ..., min_length=8, max_length=128, description="User password"
    )


class RefreshRequest(BaseModel):
    """Token refresh request payload."""

    refresh_token: str = Field(..., description="Refresh token")


class AuthResult(BaseModel):
    """Authentication result with tokens."""

    access_token: str = Field(..., description="JWT access token")
    refresh_token: str = Field(..., description="JWT refresh token")
    expires_in: int = Field(..., description="Token expiration time in seconds")
    user: UserProfile = Field(..., description="Authenticated user profile")


class TokenPayload(BaseModel):
    """JWT token payload."""

    user_id: str = Field(..., description="User identifier")
    email: str = Field(..., description="User email")
    role: UserRole = Field(..., description="User role")
    exp: datetime = Field(..., description="Token expiration timestamp")
