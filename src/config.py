"""Application configuration settings."""

from typing import Literal, Optional

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

    # Knowledge Service Configuration
    knowledge_service_type: Literal["stubbed", "rag"] = "stubbed"
    stubbed_data_path: str = "data/stub"

    # RAG Configuration (Phase 2)
    # Vector Store
    vector_store_type: Literal["chroma", "pinecone"] = "chroma"
    chroma_persist_directory: str = "data/chroma"
    chroma_collection_name: str = "medical_billing_policies"
    pinecone_api_key: Optional[str] = None
    pinecone_environment: Optional[str] = None
    pinecone_index_name: Optional[str] = None

    # Embeddings
    embedding_model: str = "text-embedding-3-small"

    # LLM Configuration
    llm_provider: Literal["openai", "anthropic"] = "openai"
    openai_api_key: Optional[str] = None
    openai_model: str = "gpt-4-turbo-preview"
    anthropic_api_key: Optional[str] = None
    anthropic_model: str = "claude-3-sonnet-20240229"

    # RAG Retrieval Parameters
    rag_top_k: int = 5  # Number of documents to retrieve
    rag_similarity_threshold: float = 0.7  # Minimum similarity score
    rag_confidence_threshold: float = 0.6  # Below this, flag as low confidence
    rag_max_tokens: int = 4096  # Max tokens for LLM response

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"


settings = Settings()
