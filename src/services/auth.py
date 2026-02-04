"""Authentication service for Medical Billing Copilot.

Implements JWT-based authentication with password hashing using bcrypt.
"""

import uuid
from datetime import datetime, timedelta, timezone
from typing import Optional

import bcrypt
from jose import ExpiredSignatureError, JWTError, jwt
from sqlalchemy.orm import Session

from src.config import settings
from src.db.models import User
from src.schemas.auth import AuthResult, TokenPayload, UserProfile
from src.schemas.common import UserRole


class AuthenticationError(Exception):
    """Base exception for authentication errors."""

    pass


class InvalidCredentialsError(AuthenticationError):
    """Raised when credentials are invalid."""

    pass


class TokenExpiredError(AuthenticationError):
    """Raised when token has expired."""

    pass


class InvalidTokenError(AuthenticationError):
    """Raised when token is invalid."""

    pass


class AccountLockedError(AuthenticationError):
    """Raised when account is locked."""

    pass


class AuthService:
    """Service for handling authentication operations.

    Provides JWT-based authentication with:
    - Password hashing using bcrypt
    - Access and refresh token generation
    - Token validation and refresh
    - Session persistence support
    - Brute force protection via account lockout
    """

    # Dummy hash for timing attack mitigation
    _DUMMY_HASH = b"$2b$12$LQv3c1yqBWVHxkd0LHAkCOYz6TtxMQJqhN8/X4.0vjqK8e5C5QKPK"

    def __init__(self, db: Session) -> None:
        """Initialize AuthService with database session.

        Args:
            db: SQLAlchemy database session
        """
        self.db = db

    @staticmethod
    def hash_password(password: str) -> str:
        """Hash a password using bcrypt.

        Args:
            password: Plain text password

        Returns:
            Hashed password string
        """
        password_bytes = password.encode("utf-8")
        salt = bcrypt.gensalt()
        return bcrypt.hashpw(password_bytes, salt).decode("utf-8")

    @staticmethod
    def verify_password(plain_password: str, hashed_password: str) -> bool:
        """Verify a password against its hash.

        Args:
            plain_password: Plain text password to verify
            hashed_password: Stored password hash

        Returns:
            True if password matches, False otherwise
        """
        password_bytes = plain_password.encode("utf-8")
        hashed_bytes = hashed_password.encode("utf-8")
        return bcrypt.checkpw(password_bytes, hashed_bytes)

    def _create_access_token(self, user: User) -> str:
        """Create a JWT access token for a user.

        Args:
            user: User model instance

        Returns:
            Encoded JWT access token
        """
        expire = datetime.now(timezone.utc) + timedelta(
            minutes=settings.jwt_access_token_expire_minutes
        )
        payload = {
            "sub": user.id,
            "email": user.email,
            "role": user.role.value,
            "exp": expire,
            "type": "access",
        }
        return jwt.encode(payload, settings.secret_key, algorithm=settings.jwt_algorithm)

    def _create_refresh_token(self, user: User) -> str:
        """Create a JWT refresh token for a user.

        Args:
            user: User model instance

        Returns:
            Encoded JWT refresh token
        """
        expire = datetime.now(timezone.utc) + timedelta(days=settings.jwt_refresh_token_expire_days)
        payload = {
            "sub": user.id,
            "exp": expire,
            "type": "refresh",
            "jti": str(uuid.uuid4()),  # Unique token ID for potential revocation
        }
        return jwt.encode(payload, settings.secret_key, algorithm=settings.jwt_algorithm)

    def _get_user_by_email(self, email: str) -> Optional[User]:
        """Get a user by email address.

        Args:
            email: User email address

        Returns:
            User instance if found, None otherwise
        """
        return self.db.query(User).filter(User.email == email).first()

    def _get_user_by_id(self, user_id: str) -> Optional[User]:
        """Get a user by ID.

        Args:
            user_id: User ID

        Returns:
            User instance if found, None otherwise
        """
        return self.db.query(User).filter(User.id == user_id).first()

    def _is_account_locked(self, user: User) -> bool:
        """Check if a user account is locked.

        Args:
            user: User model instance

        Returns:
            True if account is locked, False otherwise
        """
        if user.locked_until is None:
            return False
        # Make locked_until timezone-aware if it isn't
        locked_until = user.locked_until
        if locked_until.tzinfo is None:
            locked_until = locked_until.replace(tzinfo=timezone.utc)
        return datetime.now(timezone.utc) < locked_until

    def _decode_token(self, token: str, expected_type: str) -> dict:
        """Decode and validate a JWT token.

        Args:
            token: JWT token string
            expected_type: Expected token type ('access' or 'refresh')

        Returns:
            Decoded token payload

        Raises:
            TokenExpiredError: If token has expired
            InvalidTokenError: If token is invalid or wrong type
        """
        try:
            payload = jwt.decode(
                token, settings.secret_key, algorithms=[settings.jwt_algorithm]
            )
        except ExpiredSignatureError:
            raise TokenExpiredError(f"{expected_type.capitalize()} token has expired")
        except JWTError:
            raise InvalidTokenError(f"Invalid {expected_type} token")

        if payload.get("type") != expected_type:
            raise InvalidTokenError("Invalid token type")

        return payload

    def _build_auth_result(
        self, user: User, access_token: str, refresh_token: str
    ) -> AuthResult:
        """Build an AuthResult from user and tokens.

        Args:
            user: User model instance
            access_token: JWT access token
            refresh_token: JWT refresh token

        Returns:
            AuthResult with tokens and user profile
        """
        return AuthResult(
            access_token=access_token,
            refresh_token=refresh_token,
            expires_in=settings.jwt_access_token_expire_minutes * 60,
            user=UserProfile(
                id=user.id,
                email=user.email,
                organization_id=user.organization_id,
                role=UserRole(user.role.value),
            ),
        )

    def _handle_failed_login(self, user: User) -> None:
        """Handle a failed login attempt by incrementing counter and locking if needed.

        Args:
            user: User model instance
        """
        user.failed_login_attempts += 1
        if user.failed_login_attempts >= settings.max_failed_login_attempts:
            user.locked_until = datetime.now(timezone.utc) + timedelta(
                minutes=settings.account_lockout_minutes
            )
        self.db.commit()

    def login(self, email: str, password: str) -> AuthResult:
        """Authenticate a user and return tokens.

        Args:
            email: User email address
            password: User password

        Returns:
            AuthResult with access token, refresh token, and user profile

        Raises:
            InvalidCredentialsError: If email or password is invalid
            AccountLockedError: If account is locked due to failed attempts
        """
        user = self._get_user_by_email(email)

        if user is None:
            # Perform dummy hash to prevent timing attacks on user enumeration
            bcrypt.checkpw(b"dummy", self._DUMMY_HASH)
            raise InvalidCredentialsError("Invalid email or password")

        # Check if account is locked
        if self._is_account_locked(user):
            raise AccountLockedError("Account is temporarily locked")

        # Verify password
        if not self.verify_password(password, user.password_hash):
            self._handle_failed_login(user)
            raise InvalidCredentialsError("Invalid email or password")

        # Reset failed login attempts on successful login
        user.failed_login_attempts = 0
        user.locked_until = None
        self.db.commit()

        # Generate tokens
        access_token = self._create_access_token(user)
        refresh_token = self._create_refresh_token(user)

        return self._build_auth_result(user, access_token, refresh_token)

    def logout(self, user_id: str) -> None:
        """Log out a user.

        In a stateless JWT implementation, logout is handled client-side
        by discarding tokens. This method can be extended to implement
        token blacklisting if needed.

        Args:
            user_id: ID of the user to log out

        Raises:
            InvalidCredentialsError: If user not found
        """
        # Verify user exists
        user = self._get_user_by_id(user_id)
        if user is None:
            raise InvalidCredentialsError("Invalid credentials")

        # In a stateless JWT system, logout is primarily client-side.
        # For enhanced security, implement token blacklisting here.
        # For now, this is a no-op that validates the user exists.

    def refresh_token(self, refresh_token: str) -> AuthResult:
        """Refresh an access token using a refresh token.

        Args:
            refresh_token: Valid refresh token

        Returns:
            AuthResult with new access token, refresh token, and user profile

        Raises:
            TokenExpiredError: If refresh token has expired
            InvalidTokenError: If refresh token is invalid
            AccountLockedError: If account is locked
        """
        payload = self._decode_token(refresh_token, "refresh")

        user_id = payload.get("sub")
        if not user_id:
            raise InvalidTokenError("Invalid refresh token")

        user = self._get_user_by_id(user_id)
        if user is None:
            raise InvalidTokenError("User not found")

        # Check if account is locked
        if self._is_account_locked(user):
            raise AccountLockedError("Account is temporarily locked")

        # Generate new tokens
        new_access_token = self._create_access_token(user)
        new_refresh_token = self._create_refresh_token(user)

        return self._build_auth_result(user, new_access_token, new_refresh_token)

    def validate_token(self, token: str) -> TokenPayload:
        """Validate a JWT access token and return its payload.

        Args:
            token: JWT access token to validate

        Returns:
            TokenPayload with user information

        Raises:
            TokenExpiredError: If token has expired
            InvalidTokenError: If token is invalid or user no longer exists
        """
        payload = self._decode_token(token, "access")

        user_id = payload.get("sub")
        email = payload.get("email")
        role = payload.get("role")
        exp = payload.get("exp")

        if not all([user_id, email, role, exp]):
            raise InvalidTokenError("Invalid token payload")

        # Verify user still exists and is not locked
        user = self._get_user_by_id(user_id)
        if user is None:
            raise InvalidTokenError("User no longer exists")
        if self._is_account_locked(user):
            raise InvalidTokenError("Account is locked")

        # Convert exp to datetime
        exp_datetime = datetime.fromtimestamp(exp, tz=timezone.utc)

        return TokenPayload(
            user_id=user_id,
            email=email,
            role=UserRole(role),
            exp=exp_datetime,
        )
