"""Tests for session management API endpoints.

Requirements: 8.4, 8.5
"""

import uuid
from datetime import datetime, timezone
from typing import Generator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from src.db.base import Base
from src.db.models import MessageRecord, Session as SessionModel, User
from src.main import app
from src.services.auth import AuthService


@pytest.fixture
def test_db() -> Generator[Session, None, None]:
    """Create a test database session with thread-safe SQLite."""
    # Use StaticPool and check_same_thread=False for thread safety
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
        echo=False,
    )
    Base.metadata.create_all(engine)
    TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()
        Base.metadata.drop_all(engine)


@pytest.fixture
def test_user(test_db: Session) -> User:
    """Create a test user."""
    user = User(
        id=str(uuid.uuid4()),
        email="test@example.com",
        password_hash=AuthService.hash_password("password123"),
    )
    test_db.add(user)
    test_db.commit()
    return user


@pytest.fixture
def auth_token(test_db: Session, test_user: User) -> str:
    """Get an auth token for the test user."""
    auth_service = AuthService(test_db)
    result = auth_service.login("test@example.com", "password123")
    return result.access_token


@pytest.fixture
def test_session(test_db: Session, test_user: User) -> SessionModel:
    """Create a test session."""
    session = SessionModel(
        id=str(uuid.uuid4()),
        user_id=test_user.id,
        title="Test Session",
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
        last_activity=datetime.now(timezone.utc),
    )
    test_db.add(session)
    test_db.commit()
    return session


@pytest.fixture
def test_messages(test_db: Session, test_session: SessionModel) -> list[MessageRecord]:
    """Create test messages in a session."""
    messages = [
        MessageRecord(
            id=str(uuid.uuid4()),
            session_id=test_session.id,
            role="user",
            content="What is the coverage for CPT 99213?",
            created_at=datetime.now(timezone.utc),
        ),
        MessageRecord(
            id=str(uuid.uuid4()),
            session_id=test_session.id,
            role="assistant",
            content="CPT 99213 is covered for Medicare.",
            created_at=datetime.now(timezone.utc),
        ),
    ]
    for msg in messages:
        test_db.add(msg)
    test_db.commit()
    return messages


@pytest.fixture
def test_client(test_db: Session) -> TestClient:
    """Create a test client with database dependency override."""
    from src.db.config import get_db
    
    def override_get_db():
        try:
            yield test_db
        finally:
            pass
    
    app.dependency_overrides[get_db] = override_get_db
    client = TestClient(app)
    yield client
    app.dependency_overrides.clear()


class TestCreateSession:
    """Tests for POST /api/sessions endpoint."""

    def test_create_session_success(
        self, test_client: TestClient, auth_token: str
    ) -> None:
        """Test creating a new session."""
        response = test_client.post(
            "/api/sessions",
            headers={"Authorization": f"Bearer {auth_token}"},
            json={"title": "New Session"},
        )
        
        assert response.status_code == 201
        data = response.json()
        assert "id" in data
        assert data["title"] == "New Session"
        assert "created_at" in data
        assert "updated_at" in data
        assert "last_activity" in data

    def test_create_session_without_title(
        self, test_client: TestClient, auth_token: str
    ) -> None:
        """Test creating a session without a title."""
        response = test_client.post(
            "/api/sessions",
            headers={"Authorization": f"Bearer {auth_token}"},
        )
        
        assert response.status_code == 201
        data = response.json()
        assert data["title"] is None

    def test_create_session_unauthorized(self, test_client: TestClient) -> None:
        """Test creating a session without authentication."""
        response = test_client.post("/api/sessions")
        assert response.status_code == 403


class TestListSessions:
    """Tests for GET /api/sessions endpoint."""

    def test_list_sessions_empty(
        self, test_client: TestClient, auth_token: str
    ) -> None:
        """Test listing sessions when none exist."""
        response = test_client.get(
            "/api/sessions",
            headers={"Authorization": f"Bearer {auth_token}"},
        )
        
        assert response.status_code == 200
        assert response.json() == []

    def test_list_sessions_with_data(
        self, test_client: TestClient, auth_token: str, test_session: SessionModel
    ) -> None:
        """Test listing sessions with existing data."""
        response = test_client.get(
            "/api/sessions",
            headers={"Authorization": f"Bearer {auth_token}"},
        )
        
        assert response.status_code == 200
        data = response.json()
        assert len(data) == 1
        assert data[0]["id"] == test_session.id
        assert data[0]["title"] == "Test Session"

    def test_list_sessions_unauthorized(self, test_client: TestClient) -> None:
        """Test listing sessions without authentication."""
        response = test_client.get("/api/sessions")
        assert response.status_code == 403


class TestGetSession:
    """Tests for GET /api/sessions/{id} endpoint."""

    def test_get_session_success(
        self,
        test_client: TestClient,
        auth_token: str,
        test_session: SessionModel,
        test_messages: list[MessageRecord],
    ) -> None:
        """Test getting a session with messages."""
        response = test_client.get(
            f"/api/sessions/{test_session.id}",
            headers={"Authorization": f"Bearer {auth_token}"},
        )
        
        assert response.status_code == 200
        data = response.json()
        assert data["id"] == test_session.id
        assert data["title"] == "Test Session"
        assert len(data["messages"]) == 2
        assert data["messages"][0]["role"] == "user"
        assert data["messages"][1]["role"] == "assistant"

    def test_get_session_not_found(
        self, test_client: TestClient, auth_token: str
    ) -> None:
        """Test getting a non-existent session."""
        response = test_client.get(
            f"/api/sessions/{uuid.uuid4()}",
            headers={"Authorization": f"Bearer {auth_token}"},
        )
        
        assert response.status_code == 404

    def test_get_session_unauthorized(
        self, test_client: TestClient, test_session: SessionModel
    ) -> None:
        """Test getting a session without authentication."""
        response = test_client.get(f"/api/sessions/{test_session.id}")
        assert response.status_code == 403


class TestDeleteSession:
    """Tests for DELETE /api/sessions/{id} endpoint."""

    def test_delete_session_success(
        self,
        test_client: TestClient,
        auth_token: str,
        test_session: SessionModel,
        test_messages: list[MessageRecord],
        test_db: Session,
    ) -> None:
        """Test deleting a session and its messages."""
        response = test_client.delete(
            f"/api/sessions/{test_session.id}",
            headers={"Authorization": f"Bearer {auth_token}"},
        )
        
        assert response.status_code == 204
        
        # Verify session is deleted
        session = test_db.query(SessionModel).filter(
            SessionModel.id == test_session.id
        ).first()
        assert session is None
        
        # Verify messages are deleted
        messages = test_db.query(MessageRecord).filter(
            MessageRecord.session_id == test_session.id
        ).all()
        assert len(messages) == 0

    def test_delete_session_not_found(
        self, test_client: TestClient, auth_token: str
    ) -> None:
        """Test deleting a non-existent session."""
        response = test_client.delete(
            f"/api/sessions/{uuid.uuid4()}",
            headers={"Authorization": f"Bearer {auth_token}"},
        )
        
        assert response.status_code == 404

    def test_delete_session_unauthorized(
        self, test_client: TestClient, test_session: SessionModel
    ) -> None:
        """Test deleting a session without authentication."""
        response = test_client.delete(f"/api/sessions/{test_session.id}")
        assert response.status_code == 403


class TestSessionIsolation:
    """Tests for session isolation between users."""

    def test_cannot_access_other_user_session(
        self,
        test_client: TestClient,
        test_db: Session,
        test_session: SessionModel,
    ) -> None:
        """Test that users cannot access other users' sessions."""
        # Create another user
        other_user = User(
            id=str(uuid.uuid4()),
            email="other@example.com",
            password_hash=AuthService.hash_password("password123"),
        )
        test_db.add(other_user)
        test_db.commit()
        
        # Get token for other user
        auth_service = AuthService(test_db)
        result = auth_service.login("other@example.com", "password123")
        other_token = result.access_token
        
        # Try to access the first user's session
        response = test_client.get(
            f"/api/sessions/{test_session.id}",
            headers={"Authorization": f"Bearer {other_token}"},
        )
        
        assert response.status_code == 404

    def test_cannot_delete_other_user_session(
        self,
        test_client: TestClient,
        test_db: Session,
        test_session: SessionModel,
    ) -> None:
        """Test that users cannot delete other users' sessions."""
        # Create another user
        other_user = User(
            id=str(uuid.uuid4()),
            email="other2@example.com",
            password_hash=AuthService.hash_password("password123"),
        )
        test_db.add(other_user)
        test_db.commit()
        
        # Get token for other user
        auth_service = AuthService(test_db)
        result = auth_service.login("other2@example.com", "password123")
        other_token = result.access_token
        
        # Try to delete the first user's session
        response = test_client.delete(
            f"/api/sessions/{test_session.id}",
            headers={"Authorization": f"Bearer {other_token}"},
        )
        
        assert response.status_code == 404
        
        # Verify session still exists
        session = test_db.query(SessionModel).filter(
            SessionModel.id == test_session.id
        ).first()
        assert session is not None
