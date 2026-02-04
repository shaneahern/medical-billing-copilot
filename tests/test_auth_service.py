"""Unit tests for AuthService."""

import uuid
from datetime import datetime, timedelta, timezone
from typing import Generator

import pytest
from jose import jwt
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from src.config import settings
from src.db.base import Base
from src.db.models import User
from src.schemas.auth import TokenPayload
from src.schemas.common import UserRole
from src.services.auth import (
    AccountLockedError,
    AuthService,
    InvalidCredentialsError,
    InvalidTokenError,
    TokenExpiredError,
)


# Use SQLite for testing
TEST_DATABASE_URL = "sqlite:///:memory:"


@pytest.fixture
def test_db() -> Generator[Session, None, None]:
    """Create a test database session."""
    engine = create_engine(TEST_DATABASE_URL, echo=False)
    Base.metadata.create_all(engine)
    TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()
        Base.metadata.drop_all(engine)


@pytest.fixture
def auth_service(test_db: Session) -> AuthService:
    """Create an AuthService instance with test database."""
    return AuthService(test_db)


@pytest.fixture
def test_user(test_db: Session, auth_service: AuthService) -> User:
    """Create a test user in the database."""
    user = User(
        id=str(uuid.uuid4()),
        email="test@example.com",
        password_hash=AuthService.hash_password("TestPassword123"),
        role=UserRole.USER,
    )
    test_db.add(user)
    test_db.commit()
    return user


class TestPasswordHashing:
    """Tests for password hashing functionality."""

    def test_hash_password_returns_hash(self) -> None:
        """Test that hash_password returns a bcrypt hash."""
        password = "SecurePassword123"
        hashed = AuthService.hash_password(password)
        assert hashed != password
        assert hashed.startswith("$2b$")  # bcrypt prefix

    def test_verify_password_correct(self) -> None:
        """Test that verify_password returns True for correct password."""
        password = "SecurePassword123"
        hashed = AuthService.hash_password(password)
        assert AuthService.verify_password(password, hashed) is True

    def test_verify_password_incorrect(self) -> None:
        """Test that verify_password returns False for incorrect password."""
        password = "SecurePassword123"
        hashed = AuthService.hash_password(password)
        assert AuthService.verify_password("WrongPassword", hashed) is False


class TestLogin:
    """Tests for login functionality."""

    def test_login_success(self, auth_service: AuthService, test_user: User) -> None:
        """Test successful login returns tokens and user profile."""
        result = auth_service.login("test@example.com", "TestPassword123")

        assert result.access_token is not None
        assert result.refresh_token is not None
        assert result.expires_in == settings.jwt_access_token_expire_minutes * 60
        assert result.user.email == "test@example.com"
        assert result.user.id == test_user.id

    def test_login_invalid_email(self, auth_service: AuthService, test_user: User) -> None:
        """Test login with invalid email raises InvalidCredentialsError."""
        with pytest.raises(InvalidCredentialsError):
            auth_service.login("wrong@example.com", "TestPassword123")

    def test_login_invalid_password(self, auth_service: AuthService, test_user: User) -> None:
        """Test login with invalid password raises InvalidCredentialsError."""
        with pytest.raises(InvalidCredentialsError):
            auth_service.login("test@example.com", "WrongPassword")

    def test_login_locked_account(
        self, auth_service: AuthService, test_user: User, test_db: Session
    ) -> None:
        """Test login with locked account raises AccountLockedError."""
        test_user.locked_until = datetime.now(timezone.utc) + timedelta(minutes=15)
        test_db.commit()

        with pytest.raises(AccountLockedError):
            auth_service.login("test@example.com", "TestPassword123")

    def test_login_increments_failed_attempts(
        self, auth_service: AuthService, test_user: User, test_db: Session
    ) -> None:
        """Test that failed login attempts are tracked."""
        assert test_user.failed_login_attempts == 0

        with pytest.raises(InvalidCredentialsError):
            auth_service.login("test@example.com", "WrongPassword")

        test_db.refresh(test_user)
        assert test_user.failed_login_attempts == 1

    def test_login_locks_account_after_max_attempts(
        self, auth_service: AuthService, test_user: User, test_db: Session
    ) -> None:
        """Test that account is locked after max failed attempts."""
        # Attempt login with wrong password max_failed_login_attempts times
        for _ in range(settings.max_failed_login_attempts):
            with pytest.raises(InvalidCredentialsError):
                auth_service.login("test@example.com", "WrongPassword")

        test_db.refresh(test_user)
        assert test_user.locked_until is not None
        assert test_user.locked_until > datetime.now(timezone.utc)

        # Now correct password should fail due to lock
        with pytest.raises(AccountLockedError):
            auth_service.login("test@example.com", "TestPassword123")

    def test_login_resets_failed_attempts_on_success(
        self, auth_service: AuthService, test_user: User, test_db: Session
    ) -> None:
        """Test that successful login resets failed attempt counter."""
        # First fail a few times
        for _ in range(2):
            with pytest.raises(InvalidCredentialsError):
                auth_service.login("test@example.com", "WrongPassword")

        test_db.refresh(test_user)
        assert test_user.failed_login_attempts == 2

        # Now succeed
        auth_service.login("test@example.com", "TestPassword123")

        test_db.refresh(test_user)
        assert test_user.failed_login_attempts == 0


class TestLogout:
    """Tests for logout functionality."""

    def test_logout_success(self, auth_service: AuthService, test_user: User) -> None:
        """Test successful logout."""
        # Should not raise any exception
        auth_service.logout(test_user.id)

    def test_logout_invalid_user(self, auth_service: AuthService) -> None:
        """Test logout with invalid user raises InvalidCredentialsError."""
        with pytest.raises(InvalidCredentialsError):
            auth_service.logout("nonexistent-user-id")


class TestRefreshToken:
    """Tests for token refresh functionality."""

    def test_refresh_token_success(
        self, auth_service: AuthService, test_user: User
    ) -> None:
        """Test successful token refresh."""
        # First login to get tokens
        login_result = auth_service.login("test@example.com", "TestPassword123")

        # Refresh the token
        refresh_result = auth_service.refresh_token(login_result.refresh_token)

        assert refresh_result.access_token is not None
        assert refresh_result.refresh_token is not None
        assert refresh_result.user.id == test_user.id

    def test_refresh_token_invalid(self, auth_service: AuthService) -> None:
        """Test refresh with invalid token raises InvalidTokenError."""
        with pytest.raises(InvalidTokenError):
            auth_service.refresh_token("invalid-token")

    def test_refresh_token_wrong_type(
        self, auth_service: AuthService, test_user: User
    ) -> None:
        """Test refresh with access token raises InvalidTokenError."""
        login_result = auth_service.login("test@example.com", "TestPassword123")

        with pytest.raises(InvalidTokenError):
            auth_service.refresh_token(login_result.access_token)

    def test_refresh_token_expired(
        self, auth_service: AuthService, test_user: User
    ) -> None:
        """Test refresh with expired token raises TokenExpiredError."""
        # Create an expired refresh token
        expire = datetime.now(timezone.utc) - timedelta(days=1)
        payload = {
            "sub": test_user.id,
            "exp": expire,
            "type": "refresh",
            "jti": str(uuid.uuid4()),
        }
        expired_token = jwt.encode(
            payload, settings.secret_key, algorithm=settings.jwt_algorithm
        )

        with pytest.raises(TokenExpiredError):
            auth_service.refresh_token(expired_token)


class TestValidateToken:
    """Tests for token validation functionality."""

    def test_validate_token_success(
        self, auth_service: AuthService, test_user: User
    ) -> None:
        """Test successful token validation."""
        login_result = auth_service.login("test@example.com", "TestPassword123")

        payload = auth_service.validate_token(login_result.access_token)

        assert isinstance(payload, TokenPayload)
        assert payload.user_id == test_user.id
        assert payload.email == test_user.email

    def test_validate_token_invalid(self, auth_service: AuthService) -> None:
        """Test validation of invalid token raises InvalidTokenError."""
        with pytest.raises(InvalidTokenError):
            auth_service.validate_token("invalid-token")

    def test_validate_token_wrong_type(
        self, auth_service: AuthService, test_user: User
    ) -> None:
        """Test validation of refresh token raises InvalidTokenError."""
        login_result = auth_service.login("test@example.com", "TestPassword123")

        with pytest.raises(InvalidTokenError):
            auth_service.validate_token(login_result.refresh_token)

    def test_validate_token_expired(
        self, auth_service: AuthService, test_user: User
    ) -> None:
        """Test validation of expired token raises TokenExpiredError."""
        # Create an expired access token
        expire = datetime.now(timezone.utc) - timedelta(minutes=1)
        payload = {
            "sub": test_user.id,
            "email": test_user.email,
            "role": test_user.role.value,
            "exp": expire,
            "type": "access",
        }
        expired_token = jwt.encode(
            payload, settings.secret_key, algorithm=settings.jwt_algorithm
        )

        with pytest.raises(TokenExpiredError):
            auth_service.validate_token(expired_token)

    def test_validate_token_user_deleted(
        self, auth_service: AuthService, test_user: User, test_db: Session
    ) -> None:
        """Test validation fails if user has been deleted."""
        login_result = auth_service.login("test@example.com", "TestPassword123")

        # Delete the user
        test_db.delete(test_user)
        test_db.commit()

        with pytest.raises(InvalidTokenError, match="User no longer exists"):
            auth_service.validate_token(login_result.access_token)

    def test_validate_token_user_locked(
        self, auth_service: AuthService, test_user: User, test_db: Session
    ) -> None:
        """Test validation fails if user account is locked."""
        login_result = auth_service.login("test@example.com", "TestPassword123")

        # Lock the user account
        test_user.locked_until = datetime.now(timezone.utc) + timedelta(minutes=15)
        test_db.commit()

        with pytest.raises(InvalidTokenError, match="Account is locked"):
            auth_service.validate_token(login_result.access_token)
