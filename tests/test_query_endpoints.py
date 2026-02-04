"""Tests for Query API endpoints."""

import pytest
from fastapi.testclient import TestClient
from unittest.mock import patch, MagicMock
from datetime import datetime, timezone, timedelta
import uuid

from src.main import app
from src.schemas.common import UserRole
from src.routers.query import get_current_user, get_db


# Override auth dependency for all tests
def mock_current_user():
    return {
        "user_id": str(uuid.uuid4()),
        "email": "test@example.com",
        "role": UserRole.USER,
    }


def mock_db():
    """Mock database session."""
    mock_session = MagicMock()
    mock_session.query.return_value.filter.return_value.order_by.return_value.limit.return_value.all.return_value = []
    mock_session.query.return_value.filter.return_value.order_by.return_value.all.return_value = []
    mock_session.add = MagicMock()
    mock_session.commit = MagicMock()
    return mock_session


@pytest.fixture
def client():
    """Create a test client with mocked auth."""
    app.dependency_overrides[get_current_user] = mock_current_user
    app.dependency_overrides[get_db] = mock_db
    yield TestClient(app)
    app.dependency_overrides.clear()


@pytest.fixture
def auth_headers():
    """Return auth headers for requests."""
    return {"Authorization": "Bearer test-token"}


class TestCoverageEndpoint:
    """Tests for POST /api/coverage endpoint."""

    def test_coverage_lookup_success(self, client, auth_headers):
        """Test successful coverage lookup."""
        response = client.post(
            "/api/coverage",
            json={"cpt_code": "99213"},
            headers=auth_headers,
        )
        assert response.status_code == 200
        data = response.json()
        assert data["cpt_code"] == "99213"
        assert "is_covered" in data
        assert "payer" in data
        assert "sources" in data

    def test_coverage_lookup_with_payer(self, client, auth_headers):
        """Test coverage lookup with specific payer."""
        response = client.post(
            "/api/coverage",
            json={"cpt_code": "99213", "payer": "Medicare"},
            headers=auth_headers,
        )
        assert response.status_code == 200
        data = response.json()
        assert data["payer"] == "Medicare"

    def test_coverage_lookup_invalid_cpt(self, client, auth_headers):
        """Test coverage lookup with invalid CPT code."""
        response = client.post(
            "/api/coverage",
            json={"cpt_code": "123"},  # Invalid - not 5 digits
            headers=auth_headers,
        )
        assert response.status_code == 422  # Validation error

    def test_coverage_lookup_unauthorized(self):
        """Test coverage lookup without auth."""
        # Use a fresh client without auth override
        app.dependency_overrides.clear()
        client = TestClient(app)
        response = client.post(
            "/api/coverage",
            json={"cpt_code": "99213"},
        )
        assert response.status_code == 403  # No auth header


class TestLCDEndpoint:
    """Tests for GET /api/lcd endpoint."""

    def test_lcd_query_prompts_for_region(self, client, auth_headers):
        """Test LCD query without region prompts for selection."""
        response = client.get("/api/lcd", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        assert "message" in data
        assert "available_regions" in data

    def test_lcd_query_with_region(self, client, auth_headers):
        """Test LCD query with MAC region."""
        response = client.get(
            "/api/lcd",
            params={"mac_region": "Novitas"},
            headers=auth_headers,
        )
        assert response.status_code == 200
        data = response.json()
        assert "lcd_id" in data
        assert "mac_region" in data

    def test_lcd_query_unknown_region(self, client, auth_headers):
        """Test LCD query with unknown region."""
        response = client.get(
            "/api/lcd",
            params={"mac_region": "Unknown"},
            headers=auth_headers,
        )
        assert response.status_code == 404


class TestDenialCodeEndpoint:
    """Tests for GET /api/denial-codes/{code} endpoint."""

    def test_denial_code_explanation(self, client, auth_headers):
        """Test denial code explanation."""
        response = client.get("/api/denial-codes/16", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        assert data["carc_code"] == "16"
        assert "category" in data
        assert "short_description" in data
        assert "recommended_actions" in data

    def test_denial_code_unknown(self, client, auth_headers):
        """Test unknown denial code."""
        response = client.get("/api/denial-codes/999", headers=auth_headers)
        assert response.status_code == 404


class TestPriorAuthEndpoint:
    """Tests for GET /api/prior-auth endpoint."""

    def test_prior_auth_lookup(self, client, auth_headers):
        """Test prior auth lookup."""
        response = client.get(
            "/api/prior-auth",
            params={"cpt_code": "99213", "payer": "Medicare"},
            headers=auth_headers,
        )
        assert response.status_code == 200
        data = response.json()
        assert data["cpt_code"] == "99213"
        assert data["payer"] == "Medicare"
        assert "is_required" in data

    def test_prior_auth_missing_params(self, client, auth_headers):
        """Test prior auth with missing required params."""
        response = client.get(
            "/api/prior-auth",
            params={"cpt_code": "99213"},  # Missing payer
            headers=auth_headers,
        )
        assert response.status_code == 422


class TestQueryEndpoint:
    """Tests for POST /api/query endpoint."""

    def test_natural_language_query(self, client, auth_headers):
        """Test natural language query processing."""
        response = client.post(
            "/api/query",
            json={"query": "Is CPT 99213 covered by Medicare?"},
            headers=auth_headers,
        )
        
        assert response.status_code == 200
        data = response.json()
        assert "message" in data
        assert "query_type" in data
        assert "confidence" in data
        assert "data_source" in data
