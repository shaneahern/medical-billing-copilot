"""Knowledge Service factory for Medical Billing Copilot.

This module provides a factory function to create the appropriate
KnowledgeService implementation based on configuration.

Requirements: 6.3, 13.6
"""

import logging
from typing import Optional

from src.config import settings
from src.services.knowledge import KnowledgeService
from src.services.rag_knowledge import RAGConfig, RAGKnowledgeService
from src.services.stubbed_knowledge import StubbedKnowledgeService

logger = logging.getLogger(__name__)

# Singleton instance for the knowledge service
_knowledge_service_instance: Optional[KnowledgeService] = None


def get_knowledge_service(force_type: Optional[str] = None) -> KnowledgeService:
    """Get the configured knowledge service instance.

    This factory function creates and returns the appropriate KnowledgeService
    implementation based on the application configuration. It uses a singleton
    pattern to ensure only one instance is created.

    Requirements: 6.3, 13.6

    Args:
        force_type: Optional override for service type ('stubbed' or 'rag').
                   If not provided, uses settings.knowledge_service_type.

    Returns:
        KnowledgeService implementation (StubbedKnowledgeService or RAGKnowledgeService).

    Raises:
        ValueError: If an invalid service type is specified.
    """
    global _knowledge_service_instance

    service_type = force_type or settings.knowledge_service_type

    # Return cached instance if type matches
    if _knowledge_service_instance is not None:
        current_type = (
            "rag"
            if isinstance(_knowledge_service_instance, RAGKnowledgeService)
            else "stubbed"
        )
        if current_type == service_type:
            return _knowledge_service_instance

    # Create new instance based on type
    if service_type == "stubbed":
        logger.info(f"Creating StubbedKnowledgeService with data path: {settings.stubbed_data_path}")
        _knowledge_service_instance = StubbedKnowledgeService(
            data_path=settings.stubbed_data_path
        )
    elif service_type == "rag":
        logger.info("Creating RAGKnowledgeService")
        config = RAGConfig(
            vector_store_type=settings.vector_store_type,
            chroma_persist_directory=settings.chroma_persist_directory,
            collection_name=settings.chroma_collection_name,
            embedding_model=settings.embedding_model,
            llm_provider=settings.llm_provider,
            llm_model=(
                settings.openai_model
                if settings.llm_provider == "openai"
                else settings.anthropic_model
            ),
            top_k=settings.rag_top_k,
            similarity_threshold=settings.rag_similarity_threshold,
            confidence_threshold=settings.rag_confidence_threshold,
            max_tokens=settings.rag_max_tokens,
            openai_api_key=settings.openai_api_key,
            anthropic_api_key=settings.anthropic_api_key,
            pinecone_api_key=settings.pinecone_api_key,
            pinecone_environment=settings.pinecone_environment,
        )
        _knowledge_service_instance = RAGKnowledgeService(config=config)
    else:
        raise ValueError(f"Invalid knowledge service type: {service_type}")

    return _knowledge_service_instance


def reset_knowledge_service() -> None:
    """Reset the knowledge service singleton.

    This is useful for testing or when configuration changes require
    a new instance to be created.
    """
    global _knowledge_service_instance
    _knowledge_service_instance = None
    logger.info("Knowledge service instance reset")


def get_data_source_indicator() -> dict:
    """Get data source indicator for UI display.

    Returns information about the current knowledge service
    for display in the frontend.

    Requirements: 9.6, 13.6

    Returns:
        Dictionary with data source information.
    """
    service = get_knowledge_service()
    info = service.get_data_source_info()

    return {
        "type": info.type.value,
        "is_stubbed": info.type.value == "STUBBED",
        "is_rag": info.type.value == "RAG",
        "last_updated": info.last_updated.isoformat(),
        "coverage": info.coverage,
        "display_message": (
            "Using demo/test data"
            if info.type.value == "STUBBED"
            else "Using live policy data"
        ),
    }
