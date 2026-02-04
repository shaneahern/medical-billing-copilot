"""Authentication service for Medical Billing Copilot.

Implements JWT-based authentication with password hashing using bcrypt.
Includes account lockout mechanism per Requirement 7.5.
Includes session timeout per Requirement 7.3.
"""

import uuid
from datetime import datetime, timedelta, timezone
from typing import Optional

import bcrypt
from jose import ExpiredSignatureError, JWTError, jwt
from sqlalchemy.orm import Session

from src.config import settings
from src.db.models import User, Session as SessionModel
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
    """Raised when account is locked due to failed login attempts."""

    pass


class SessionTimeoutError(AuthenticationError):
    """Raised when session has timed out due to inactivity."""

    pass


class SessionNotFoundError(AuthenticationError):
    """Raised when session is not found."""

    pass


class AuthService:
    """Service for handling authentication operations.

    Provides JWT-based authentication with:
    - Password hashing using bcrypt
    - Access and refresh token generation
    - Token validation and refresh
    - Session persistence support
    - Brute force protection via account lockout (locks after 3 consecutive failures)
    - Session timeout after 30 minutes of inactivity (Requirement 7.3)
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
            "jti": str(uuid.uuid4()),
        }
        return jwt.encode(payload, settings.secret_key, algorithm=settings.jwt_algorithm)

    def _get_user_by_email(self, email: str) -> Optional[User]:
        """Get a user by email address."""
        return self.db.query(User).filter(User.email == email).first()

    def _get_user_by_id(self, user_id: str) -> Optional[User]:
        """Get a user by ID."""
        return self.db.query(User).filter(User.id == user_id).first()

    def _get_session_by_id(self, session_id: str) -> Optional[SessionModel]:
        """Get a session by ID."""
        return self.db.query(SessionModel).filter(SessionModel.id == session_id).first()

    def _is_account_locked(self, user: User) -> bool:
        """Check if a user account is locked."""
        if user.locked_until is None:
            return False
        locked_until = user.locked_until
        if locked_until.tzinfo is None:
            locked_until = locked_until.replace(tzinfo=timezone.utc)
        return datetime.now(timezone.utc) < locked_until

    def _is_session_timed_out(self, session: SessionModel) -> bool:
        """Check if a session has timed out due to inactivity.

        Per Requirement 7.3: Session times out after 30 minutes of inactivity.

        Args:
            session: Session model instance

        Returns:
            True if session has timed out, False otherwise
        """
        last_activity = session.last_activity
        if last_activity.tzinfo is None:
            last_activity = last_activity.replace(tzinfo=timezone.utc)
        
        timeout_threshold = datetime.now(timezone.utc) - timedelta(
            minutes=settings.session_inactivity_timeout_minutes
        )
        return last_activity < timeout_threshold

    def _decode_token(self, token: str, expected_type: str) -> dict:
        """Decode and validate a JWT token."""
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
        """Build an AuthResult from user and tokens."""
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
        """Handle a failed login attempt by incrementing counter and locking if needed."""
        user.failed_login_attempts += 1
        if user.failed_login_attempts >= settings.max_failed_login_attempts:
            user.locked_until = datetime.now(timezone.utc) + timedelta(
                minutes=settings.account_lockout_minutes
            )
        self.db.commit()

    def _reset_failed_attempts(self, user: User) -> None:
        """Reset failed login attempts and unlock account on successful login."""
        user.failed_login_attempts = 0
        user.locked_until = None
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
            bcrypt.checkpw(b"dummy", self._DUMMY_HASH)
            raise InvalidCredentialsError("Invalid email or password")

        if self._is_account_locked(user):
            raise AccountLockedError("Account is temporarily locked")

        if not self.verify_password(password, user.password_hash):
            self._handle_failed_login(user)
            raise InvalidCredentialsError("Invalid email or password")

        self._reset_failed_attempts(user)

        access_token = self._create_access_token(user)
        refresh_token = self._create_refresh_token(user)

        return self._build_auth_result(user, access_token, refresh_token)

    def logout(self, user_id: str) -> None:
        """Log out a user.

        Args:
            user_id: ID of the user to log out

        Raises:
            InvalidCredentialsError: If user not found
        """
        user = self._get_user_by_id(user_id)
        if user is None:
            raise InvalidCredentialsError("Invalid credentials")

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

        if self._is_account_locked(user):
            raise AccountLockedError("Account is temporarily locked")

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

        user = self._get_user_by_id(user_id)
        if user is None:
            raise InvalidTokenError("User no longer exists")
        if self._is_account_locked(user):
            raise InvalidTokenError("Account is locked")

        exp_datetime = datetime.fromtimestamp(exp, tz=timezone.utc)

        return TokenPayload(
            user_id=user_id,
            email=email,
            role=UserRole(role),
            exp=exp_datetime,
        )

    def validate_session_freshness(self, session_id: str) -> bool:
        """Validate that a session is still fresh (not timed out).

        Per Requirement 7.3: Sessions time out after 30 minutes of inactivity.
        This method should be called on each request to validate session freshness.

        Args:
            session_id: ID of the session to validate

        Returns:
            True if session is fresh

        Raises:
            SessionNotFoundError: If session does not exist
            SessionTimeoutError: If session has timed out due to inactivity
        """
        session = self._get_session_by_id(session_id)
        if session is None:
            raise SessionNotFoundError("Session not found")

        if self._is_session_timed_out(session):
            raise SessionTimeoutError(
                "Session has timed out due to inactivity. Please re-authenticate."
            )

        return True

    def update_session_activity(self, session_id: str) -> None:
        """Update the last activity timestamp for a session.

        This method should be called on each request to keep the session alive.

        Args:
            session_id: ID of the session to update

        Raises:
            SessionNotFoundError: If session does not exist
            SessionTimeoutError: If session has already timed out
        """
        session = self._get_session_by_id(session_id)
        if session is None:
            raise SessionNotFoundError("Session not found")

        if self._is_session_timed_out(session):
            raise SessionTimeoutError(
                "Session has timed out due to inactivity. Please re-authenticate."
            )

        session.last_activity = datetime.now(timezone.utc)
        self.db.commit()

    def validate_and_refresh_session(self, session_id: str) -> bool:
        """Validate session freshness and update activity in one operation.

        This is a convenience method that combines validation and activity update.
        Use this on each authenticated request to ensure session is valid and
        keep it alive.

        Args:
            session_id: ID of the session to validate and refresh

        Returns:
            True if session is valid and was refreshed

        Raises:
            SessionNotFoundError: If session does not exist
            SessionTimeoutError: If session has timed out due to inactivity
        """
        session = self._get_session_by_id(session_id)
        if session is None:
            raise SessionNotFoundError("Session not found")

        if self._is_session_timed_out(session):
            raise SessionTimeoutError(
                "Session has timed out due to inactivity. Please re-authenticate."
            )

        session.last_activity = datetime.now(timezone.utc)
        self.db.commit()
        return True

    def get_session_timeout_info(self, session_id: str) -> dict:
        """Get timeout information for a session.

        Args:
            session_id: ID of the session to check

        Returns:
            Dictionary with session timeout information:
            - is_timed_out: Whether the session has timed out
            - last_activity: Last activity timestamp
            - timeout_at: When the session will/did timeout
            - remaining_seconds: Seconds until timeout (0 if timed out)

        Raises:
            SessionNotFoundError: If session does not exist
        """
        session = self._get_session_by_id(session_id)
        if session is None:
            raise SessionNotFoundError("Session not found")

        last_activity = session.last_activity
        if last_activity.tzinfo is None:
            last_activity = last_activity.replace(tzinfo=timezone.utc)

        timeout_at = last_activity + timedelta(
            minutes=settings.session_inactivity_timeout_minutes
        )
        now = datetime.now(timezone.utc)
        is_timed_out = now >= timeout_at
        remaining_seconds = max(0, int((timeout_at - now).total_seconds()))

        return {
            "is_timed_out": is_timed_out,
            "last_activity": last_activity,
            "timeout_at": timeout_at,
            "remaining_seconds": remaining_seconds,
        }

    def lock_account(self, user_id: str) -> None:
        """Manually lock a user account.

        Args:
            user_id: ID of the user to lock

        Raises:
            InvalidCredentialsError: If user not found
        """
        user = self._get_user_by_id(user_id)
        if user is None:
            raise InvalidCredentialsError("User not found")

        user.locked_until = datetime.now(timezone.utc) + timedelta(
            minutes=settings.account_lockout_minutes
        )
        self.db.commit()

    def unlock_account(self, user_id: str) -> None:
        """Manually unlock a user account.

        Args:
            user_id: ID of the user to unlock

        Raises:
            InvalidCredentialsError: If user not found
        """
        user = self._get_user_by_id(user_id)
        if user is None:
            raise InvalidCredentialsError("User not found")

        user.locked_until = None
        user.failed_login_attempts = 0
        self.db.commit()

    def get_lockout_status(self, user_id: str) -> dict:
        """Get the lockout status of a user account.

        Args:
            user_id: ID of the user to check

        Returns:
            Dictionary with lockout status information

        Raises:
            InvalidCredentialsError: If user not found
        """
        user = self._get_user_by_id(user_id)
        if user is None:
            raise InvalidCredentialsError("User not found")

        is_locked = self._is_account_locked(user)
        remaining_attempts = max(
            0, settings.max_failed_login_attempts - user.failed_login_attempts
        )

        return {
            "is_locked": is_locked,
            "failed_attempts": user.failed_login_attempts,
            "locked_until": user.locked_until if is_locked else None,
            "remaining_attempts": remaining_attempts if not is_locked else 0,
        }
