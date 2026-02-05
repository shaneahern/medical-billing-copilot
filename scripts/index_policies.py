#!/usr/bin/env python
"""Script to index ingested policy documents into the vector store.

Run this after ingesting documents to make them searchable via RAG.
"""

import asyncio
import logging
import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.config import settings
from src.services.policy_database import PolicyDatabase

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


async def index_documents():
    """Index all documents from the policy database into the vector store."""
    
    # Check for OpenAI API key
    if not settings.openai_api_key or settings.openai_api_key == "your-openai-api-key-here":
        logger.error("Please set OPENAI_API_KEY in your .env file")
        return
    
    # Load policy database
    logger.info("Loading policy database...")
    policy_db = PolicyDatabase(persist_path="data/policy_db_state.json")
    
    doc_count = len(policy_db._documents)
    content_count = len(policy_db._document_content)
    
    logger.info(f"Found {doc_count} documents, {content_count} with content")
    
    if content_count == 0:
        logger.error("No document content found. Run ingestion first.")
        return
    
    # Initialize RAG service
    logger.info("Initializing RAG service...")
    from src.services.rag_knowledge import RAGKnowledgeService
    
    rag_service = RAGKnowledgeService()
    rag_service._ensure_initialized()
    
    # Prepare documents for indexing
    documents_to_index = []
    
    for doc_id, metadata in policy_db._documents.items():
        content = policy_db._document_content.get(doc_id)
        if not content:
            continue
        
        doc_metadata = {
            "document_id": doc_id,
            "title": metadata.title,
            "source_type": metadata.document_type.value,
            "source_url": metadata.source_url,
        }
        
        if metadata.payer:
            doc_metadata["payer"] = metadata.payer.lower()
        if metadata.mac_region:
            doc_metadata["mac_region"] = metadata.mac_region.upper()
        if metadata.effective_date:
            doc_metadata["effective_date"] = metadata.effective_date.isoformat()
        
        documents_to_index.append({
            "content": content,
            "metadata": doc_metadata,
        })
    
    logger.info(f"Indexing {len(documents_to_index)} documents...")
    
    # Index in smaller batches with delays to avoid rate limits
    batch_size = 20  # Smaller batches to avoid rate limits
    total_indexed = 0
    
    import time
    
    for i in range(0, len(documents_to_index), batch_size):
        batch = documents_to_index[i:i + batch_size]
        
        # Add to vector store
        texts = [doc["content"] for doc in batch]
        metadatas = [doc["metadata"] for doc in batch]
        
        try:
            rag_service._vector_store.add_texts(texts=texts, metadatas=metadatas)
            total_indexed += len(batch)
            logger.info(f"Indexed {total_indexed}/{len(documents_to_index)} documents")
        except Exception as e:
            if "rate_limit" in str(e).lower() or "429" in str(e):
                logger.warning(f"Rate limit hit, waiting 30 seconds...")
                time.sleep(30)
                # Retry
                rag_service._vector_store.add_texts(texts=texts, metadatas=metadatas)
                total_indexed += len(batch)
                logger.info(f"Indexed {total_indexed}/{len(documents_to_index)} documents (after retry)")
            else:
                raise
        
        # Add delay between batches to avoid rate limits
        if i + batch_size < len(documents_to_index):
            time.sleep(2)  # 2 second delay between batches
    
    # Persist the vector store
    if hasattr(rag_service._vector_store, 'persist'):
        rag_service._vector_store.persist()
    
    logger.info(f"Successfully indexed {total_indexed} documents into ChromaDB")
    logger.info(f"Vector store location: {settings.chroma_persist_directory}")


if __name__ == "__main__":
    asyncio.run(index_documents())
