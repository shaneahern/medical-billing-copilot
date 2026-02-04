"""Pytest configuration and fixtures."""

import pytest
from fastapi.testclient import TestClient
from hypothesis import settings

from src.main import app

# Configure hypothesis defaults
settings.register_profile("default", max_examples=100, deadline=3000)
settings.register_profile("ci", max_examples=200, deadline=5000)
settings.load_profile("default")


@pytest.fixture
def client():
    """Create a test client for the FastAPI app."""
    return TestClient(app)
