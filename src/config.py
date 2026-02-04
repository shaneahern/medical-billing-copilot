"""Application configuration settings."""

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    # Database
    database_url: str = "postgresql://postgres:postgres@localhost:5434/medical_billing"

    # Application
    debug: bool = False
    secret_key: str = "change-me-in-production"

    # JWT
    jwt_algorithm: str = "HS256"
    jwt_access_token_expire_minutes: int = 30
    jwt_refresh_token_expire_days: int = 7

    # Security
    max_failed_login_attempts: int = 3  # Lock after 3 consecutive failures per Requirement 7.5
    account_lockout_minutes: int = 15
    session_inactivity_timeout_minutes: int = 30  # Session timeout per Requirement 7.3

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"


settings = Settings()
