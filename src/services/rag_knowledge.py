"""RAG-backed Knowledge Service implementation for Medical Billing Copilot.

This module provides a RAG (Retrieval-Augmented Generation) implementation
of the KnowledgeService interface using LangChain with vector search and LLM.

Requirements: 10.1, 10.2, 10.4, 10.5, 10.6, 13.1, 13.2, 13.3, 13.5, 13.6
"""

import json
import logging
from datetime import UTC, datetime
from typing import Any, Optional

from pydantic import BaseModel, Field

from src.config import settings
from src.schemas.common import Citation, ConditionType, DataSource, DenialCategory
from src.schemas.knowledge import (
    AlternativeCode,
    CoverageCondition,
    CoverageLookupParams,
    CoverageResult,
    DataSourceInfo,
    DenialContext,
    DenialExplanation,
    LCDQueryParams,
    LCDResult,
    LCDRevision,
    PlanVariation,
    PriorAuthParams,
    PriorAuthResult,
    RecommendedAction,
)
from src.services.knowledge import KnowledgeService

logger = logging.getLogger(__name__)


class RAGConfig(BaseModel):
    """Configuration for RAG Knowledge Service."""

    vector_store_type: str = Field(default="chroma", description="Vector store type")
    chroma_persist_directory: str = Field(
        default="data/chroma", description="ChromaDB persistence directory"
    )
    collection_name: str = Field(
        default="medical_billing_policies", description="Vector store collection name"
    )
    embedding_model: str = Field(
        default="text-embedding-3-small", description="Embedding model name"
    )
    llm_provider: str = Field(default="openai", description="LLM provider")
    llm_model: str = Field(default="gpt-4-turbo-preview", description="LLM model name")
    top_k: int = Field(default=5, description="Number of documents to retrieve")
    similarity_threshold: float = Field(
        default=0.7, description="Minimum similarity score for retrieval"
    )
    confidence_threshold: float = Field(
        default=0.6, description="Threshold for low-confidence flagging"
    )
    max_tokens: int = Field(default=4096, description="Max tokens for LLM response")
    openai_api_key: Optional[str] = Field(default=None, description="OpenAI API key")
    anthropic_api_key: Optional[str] = Field(default=None, description="Anthropic API key")
    pinecone_api_key: Optional[str] = Field(default=None, description="Pinecone API key")
    pinecone_environment: Optional[str] = Field(default=None, description="Pinecone environment")


class RetrievedDocument(BaseModel):
    """A document retrieved from the vector store."""

    content: str
    metadata: dict[str, Any]
    score: float


class RAGKnowledgeService(KnowledgeService):
    """RAG-backed implementation of KnowledgeService.

    This implementation uses LangChain with vector search and LLM
    to provide policy data retrieval and response generation.

    Requirements: 10.1, 10.2, 10.6, 13.1, 13.2, 13.3
    """

    def __init__(self, config: Optional[RAGConfig] = None):
        """Initialize the RAG knowledge service.

        Args:
            config: RAG configuration. If None, uses settings from config.py.
        """
        self.config = config or self._config_from_settings()
        self._vector_store = None
        self._embeddings = None
        self._llm = None
        self._retriever = None
        self._last_updated: datetime = datetime.now(UTC)
        self._initialized = False

    def _config_from_settings(self) -> RAGConfig:
        """Create RAGConfig from application settings."""
        return RAGConfig(
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

    def _ensure_initialized(self) -> None:
        """Ensure the RAG components are initialized."""
        if self._initialized:
            return

        self._init_embeddings()
        self._init_vector_store()
        self._init_llm()
        self._init_retriever()
        self._initialized = True

    def _init_embeddings(self) -> None:
        """Initialize the embedding model."""
        try:
            from langchain_openai import OpenAIEmbeddings

            self._embeddings = OpenAIEmbeddings(
                model=self.config.embedding_model,
                openai_api_key=self.config.openai_api_key,
            )
            logger.info(f"Initialized OpenAI embeddings with model: {self.config.embedding_model}")
        except Exception as e:
            logger.error(f"Failed to initialize embeddings: {e}")
            raise

    def _init_vector_store(self) -> None:
        """Initialize the vector store."""
        try:
            if self.config.vector_store_type == "chroma":
                from langchain_community.vectorstores import Chroma

                self._vector_store = Chroma(
                    collection_name=self.config.collection_name,
                    embedding_function=self._embeddings,
                    persist_directory=self.config.chroma_persist_directory,
                )
                logger.info(
                    f"Initialized ChromaDB vector store: {self.config.collection_name}"
                )
            elif self.config.vector_store_type == "pinecone":
                from langchain_pinecone import PineconeVectorStore

                self._vector_store = PineconeVectorStore(
                    index_name=self.config.collection_name,
                    embedding=self._embeddings,
                    pinecone_api_key=self.config.pinecone_api_key,
                )
                logger.info(
                    f"Initialized Pinecone vector store: {self.config.collection_name}"
                )
            else:
                raise ValueError(
                    f"Unsupported vector store type: {self.config.vector_store_type}"
                )
        except Exception as e:
            logger.error(f"Failed to initialize vector store: {e}")
            raise

    def _init_llm(self) -> None:
        """Initialize the LLM."""
        try:
            if self.config.llm_provider == "openai":
                from langchain_openai import ChatOpenAI

                self._llm = ChatOpenAI(
                    model=self.config.llm_model,
                    openai_api_key=self.config.openai_api_key,
                    max_tokens=self.config.max_tokens,
                    temperature=0.1,  # Low temperature for factual responses
                )
                logger.info(f"Initialized OpenAI LLM: {self.config.llm_model}")
            elif self.config.llm_provider == "anthropic":
                from langchain_anthropic import ChatAnthropic

                self._llm = ChatAnthropic(
                    model=self.config.llm_model,
                    anthropic_api_key=self.config.anthropic_api_key,
                    max_tokens=self.config.max_tokens,
                )
                logger.info(f"Initialized Anthropic LLM: {self.config.llm_model}")
            else:
                raise ValueError(f"Unsupported LLM provider: {self.config.llm_provider}")
        except Exception as e:
            logger.error(f"Failed to initialize LLM: {e}")
            raise

    def _init_retriever(self) -> None:
        """Initialize the retriever with hybrid search support.

        Implements hybrid search combining semantic similarity and keyword matching.
        Requirements: 10.6
        """
        if self._vector_store is None:
            raise RuntimeError("Vector store must be initialized before retriever")

        # Create retriever with similarity score threshold
        self._retriever = self._vector_store.as_retriever(
            search_type="similarity_score_threshold",
            search_kwargs={
                "k": self.config.top_k,
                "score_threshold": self.config.similarity_threshold,
            },
        )
        logger.info(
            f"Initialized retriever with top_k={self.config.top_k}, "
            f"threshold={self.config.similarity_threshold}"
        )

    async def _retrieve_documents(
        self,
        query: str,
        filter_metadata: Optional[dict[str, Any]] = None,
    ) -> list[RetrievedDocument]:
        """Retrieve relevant documents from the vector store.

        Args:
            query: The search query.
            filter_metadata: Optional metadata filters.

        Returns:
            List of retrieved documents with scores.

        Requirements: 10.1, 10.2
        """
        self._ensure_initialized()

        try:
            # Use similarity search with score for confidence calculation
            if filter_metadata:
                results = self._vector_store.similarity_search_with_score(
                    query,
                    k=self.config.top_k,
                    filter=filter_metadata,
                )
            else:
                results = self._vector_store.similarity_search_with_score(
                    query,
                    k=self.config.top_k,
                )

            documents = []
            for doc, score in results:
                # Filter by similarity threshold
                if score >= self.config.similarity_threshold:
                    documents.append(
                        RetrievedDocument(
                            content=doc.page_content,
                            metadata=doc.metadata,
                            score=score,
                        )
                    )

            logger.info(f"Retrieved {len(documents)} documents for query: {query[:50]}...")
            return documents

        except Exception as e:
            logger.error(f"Document retrieval failed: {e}")
            return []

    def _calculate_confidence(self, documents: list[RetrievedDocument]) -> float:
        """Calculate confidence score based on retrieved documents.

        Requirements: 10.4, 10.5

        Args:
            documents: List of retrieved documents with scores.

        Returns:
            Confidence score between 0 and 1.
        """
        if not documents:
            return 0.0

        # Average the top document scores
        scores = [doc.score for doc in documents]
        avg_score = sum(scores) / len(scores)

        # Boost confidence if multiple relevant documents found
        coverage_boost = min(len(documents) / self.config.top_k, 1.0) * 0.1

        confidence = min(avg_score + coverage_boost, 1.0)
        return round(confidence, 2)

    def _is_low_confidence(self, confidence: float) -> bool:
        """Check if confidence is below threshold.

        Requirements: 10.5, 13.5
        """
        return confidence < self.config.confidence_threshold

    def _build_citations_from_documents(
        self, documents: list[RetrievedDocument]
    ) -> list[Citation]:
        """Build citations from retrieved documents."""
        citations = []
        for doc in documents:
            metadata = doc.metadata
            source_type = metadata.get("source_type", "RAG")
            effective_date = None
            if "effective_date" in metadata:
                try:
                    effective_date = datetime.fromisoformat(
                        metadata["effective_date"].replace("Z", "+00:00")
                    )
                except (ValueError, AttributeError):
                    pass

            citations.append(
                Citation(
                    source_type=source_type,
                    document_id=metadata.get("document_id", f"RAG-{hash(doc.content)[:8]}"),
                    document_title=metadata.get("title", "Policy Document"),
                    source_url=metadata.get("source_url"),
                    effective_date=effective_date,
                )
            )
        return citations


    async def _generate_response(
        self,
        query: str,
        documents: list[RetrievedDocument],
        system_prompt: str,
    ) -> str:
        """Generate a response using the LLM with retrieved context.

        Requirements: 13.1, 13.2, 13.3

        Args:
            query: The user query.
            documents: Retrieved documents for context.
            system_prompt: System prompt for the LLM.

        Returns:
            Generated response text.
        """
        self._ensure_initialized()

        # Build context from documents
        context_parts = []
        for i, doc in enumerate(documents, 1):
            context_parts.append(
                f"[Document {i}]\n"
                f"Source: {doc.metadata.get('title', 'Unknown')}\n"
                f"Type: {doc.metadata.get('source_type', 'Unknown')}\n"
                f"Content: {doc.content}\n"
            )

        context = "\n---\n".join(context_parts) if context_parts else "No relevant documents found."

        # Build the prompt
        from langchain_core.messages import HumanMessage, SystemMessage

        messages = [
            SystemMessage(content=system_prompt),
            HumanMessage(
                content=f"Context from policy documents:\n{context}\n\nUser Query: {query}"
            ),
        ]

        try:
            response = await self._llm.ainvoke(messages)
            return response.content
        except Exception as e:
            logger.error(f"LLM generation failed: {e}")
            raise

    async def lookup_coverage(self, params: CoverageLookupParams) -> CoverageResult:
        """Look up coverage information using RAG.

        Requirements: 10.1, 10.2, 13.1, 13.2, 13.3
        """
        # Build search query
        query = f"Coverage policy for CPT code {params.cpt_code}"
        if params.icd_codes:
            query += f" with diagnosis codes {', '.join(params.icd_codes)}"
        if params.payer:
            query += f" for payer {params.payer}"
        if params.mac_region:
            query += f" in MAC region {params.mac_region}"

        # Build metadata filter
        filter_metadata = {}
        if params.payer:
            filter_metadata["payer"] = params.payer.lower()
        if params.mac_region:
            filter_metadata["mac_region"] = params.mac_region.upper()

        # Retrieve relevant documents
        documents = await self._retrieve_documents(
            query, filter_metadata if filter_metadata else None
        )

        confidence = self._calculate_confidence(documents)
        citations = self._build_citations_from_documents(documents)

        # Generate response using LLM
        system_prompt = """You are a medical billing expert assistant. Analyze the provided policy documents 
and determine coverage for the requested CPT code and diagnosis combination.

Your response must be a valid JSON object with the following structure:
{
    "is_covered": boolean,
    "cpt_description": "description of the CPT code",
    "conditions": [{"type": "DIAGNOSIS|FREQUENCY|DOCUMENTATION|OTHER", "description": "condition text"}],
    "restrictions": ["list of restrictions"],
    "alternative_codes": [{"cpt_code": "code", "description": "desc", "reason": "reason"}] or null,
    "explanation": "brief explanation of the coverage determination"
}

Base your response ONLY on the provided documents. If information is not available, indicate uncertainty."""

        payer = params.payer or "Medicare"

        if not documents:
            # No documents found - return not found result
            return CoverageResult(
                cpt_code=params.cpt_code,
                cpt_description="Unknown procedure code",
                is_covered=False,
                payer=payer,
                conditions=[],
                restrictions=["No coverage information found in policy database"],
                alternative_codes=None,
                sources=citations
                or [
                    Citation(
                        source_type="RAG",
                        document_id="RAG-NOT-FOUND",
                        document_title="No matching policy documents",
                        effective_date=self._last_updated,
                    )
                ],
                confidence=0.0,
            )

        try:
            response_text = await self._generate_response(query, documents, system_prompt)
            # Parse JSON response
            response_data = json.loads(response_text)

            conditions = [
                CoverageCondition(
                    type=ConditionType(c.get("type", "OTHER")),
                    description=c["description"],
                )
                for c in response_data.get("conditions", [])
            ]

            alternative_codes = None
            if response_data.get("alternative_codes"):
                alternative_codes = [
                    AlternativeCode(
                        cpt_code=ac["cpt_code"],
                        description=ac["description"],
                        reason=ac["reason"],
                    )
                    for ac in response_data["alternative_codes"]
                ]

            return CoverageResult(
                cpt_code=params.cpt_code,
                cpt_description=response_data.get("cpt_description", ""),
                is_covered=response_data.get("is_covered", False),
                payer=payer,
                conditions=conditions,
                restrictions=response_data.get("restrictions", []),
                alternative_codes=alternative_codes,
                sources=citations,
                confidence=confidence,
            )

        except json.JSONDecodeError:
            logger.warning("Failed to parse LLM response as JSON, using fallback")
            return CoverageResult(
                cpt_code=params.cpt_code,
                cpt_description="See policy documents for details",
                is_covered=True,  # Default to covered with low confidence
                payer=payer,
                conditions=[],
                restrictions=["Unable to parse detailed coverage information"],
                alternative_codes=None,
                sources=citations,
                confidence=confidence * 0.5,  # Reduce confidence for parse failures
            )

    async def query_lcd(self, params: LCDQueryParams) -> LCDResult:
        """Query Local Coverage Determination using RAG.

        Requirements: 10.1, 10.2, 13.1, 13.2, 13.3
        """
        # Build search query
        query = f"Local Coverage Determination LCD for MAC region {params.mac_region}"
        if params.lcd_id:
            query += f" with LCD ID {params.lcd_id}"
        if params.cpt_code:
            query += f" covering CPT code {params.cpt_code}"

        # Build metadata filter
        filter_metadata = {"mac_region": params.mac_region.upper()}
        if params.lcd_id:
            filter_metadata["lcd_id"] = params.lcd_id

        # Retrieve relevant documents
        documents = await self._retrieve_documents(query, filter_metadata)

        if not documents:
            raise LookupError(
                f"No LCD found for MAC region {params.mac_region}"
                + (f" and CPT code {params.cpt_code}" if params.cpt_code else "")
            )

        confidence = self._calculate_confidence(documents)

        # Generate response using LLM
        system_prompt = """You are a medical billing expert assistant. Analyze the provided LCD documents 
and extract the relevant information.

Your response must be a valid JSON object with the following structure:
{
    "lcd_id": "LCD identifier",
    "title": "LCD title",
    "mac_name": "MAC contractor name",
    "effective_date": "YYYY-MM-DD",
    "revision_history": [{"version": "v1", "effective_date": "YYYY-MM-DD", "summary": "changes"}],
    "covered_cpt_codes": ["list of CPT codes"],
    "covered_icd_codes": ["list of ICD codes"],
    "limitations": ["list of limitations"],
    "documentation_requirements": ["list of requirements"],
    "source_url": "URL to source document"
}

Base your response ONLY on the provided documents."""

        try:
            response_text = await self._generate_response(query, documents, system_prompt)
            response_data = json.loads(response_text)

            revision_history = [
                LCDRevision(
                    version=rev["version"],
                    effective_date=datetime.fromisoformat(rev["effective_date"]),
                    summary=rev["summary"],
                )
                for rev in response_data.get("revision_history", [])
            ]

            return LCDResult(
                lcd_id=response_data.get("lcd_id", f"LCD-{params.mac_region}"),
                title=response_data.get("title", "Local Coverage Determination"),
                mac_region=params.mac_region,
                mac_name=response_data.get("mac_name", "Unknown MAC"),
                effective_date=datetime.fromisoformat(
                    response_data.get("effective_date", datetime.now(UTC).isoformat())
                ),
                revision_history=revision_history,
                covered_cpt_codes=response_data.get("covered_cpt_codes", []),
                covered_icd_codes=response_data.get("covered_icd_codes", []),
                limitations=response_data.get("limitations", []),
                documentation_requirements=response_data.get("documentation_requirements", []),
                source_url=response_data.get("source_url", ""),
            )

        except json.JSONDecodeError:
            logger.warning("Failed to parse LLM response as JSON for LCD query")
            # Return basic result from document metadata
            doc = documents[0]
            return LCDResult(
                lcd_id=doc.metadata.get("lcd_id", f"LCD-{params.mac_region}"),
                title=doc.metadata.get("title", "Local Coverage Determination"),
                mac_region=params.mac_region,
                mac_name=doc.metadata.get("mac_name", "Unknown MAC"),
                effective_date=self._last_updated,
                revision_history=[],
                covered_cpt_codes=[],
                covered_icd_codes=[],
                limitations=[],
                documentation_requirements=[],
                source_url=doc.metadata.get("source_url", ""),
            )


    async def explain_denial_code(
        self, code: str, context: Optional[DenialContext] = None
    ) -> DenialExplanation:
        """Explain a CARC denial code using RAG.

        Requirements: 10.1, 10.2, 13.1, 13.2, 13.3
        """
        # Build search query
        query = f"CARC denial code {code} explanation and recommended actions"
        if context:
            if context.payer:
                query += f" for payer {context.payer}"
            if context.cpt_code:
                query += f" related to CPT code {context.cpt_code}"
            if context.claim_type:
                query += f" for {context.claim_type} claims"

        # Build metadata filter for CARC codes
        filter_metadata = {"source_type": "CARC"}

        # Retrieve relevant documents
        documents = await self._retrieve_documents(query, filter_metadata)

        if not documents:
            raise LookupError(f"CARC code {code} not found in database")

        confidence = self._calculate_confidence(documents)

        # Generate response using LLM
        system_prompt = """You are a medical billing expert assistant. Analyze the provided CARC code documentation 
and explain the denial reason with recommended corrective actions.

Your response must be a valid JSON object with the following structure:
{
    "category": "ELIGIBILITY|AUTHORIZATION|CODING|DOCUMENTATION|OTHER",
    "short_description": "brief description",
    "detailed_explanation": "detailed explanation of the denial reason",
    "common_causes": ["list of common causes"],
    "recommended_actions": [{"priority": 1, "action": "action text", "details": "optional details"}],
    "related_codes": ["list of related CARC codes"] or null
}

Base your response ONLY on the provided documents. Prioritize actionable recommendations."""

        try:
            response_text = await self._generate_response(query, documents, system_prompt)
            response_data = json.loads(response_text)

            category_map = {
                "ELIGIBILITY": DenialCategory.ELIGIBILITY,
                "AUTHORIZATION": DenialCategory.AUTHORIZATION,
                "CODING": DenialCategory.CODING,
                "DOCUMENTATION": DenialCategory.DOCUMENTATION,
                "OTHER": DenialCategory.OTHER,
            }
            category = category_map.get(
                response_data.get("category", "OTHER"), DenialCategory.OTHER
            )

            recommended_actions = [
                RecommendedAction(
                    priority=action["priority"],
                    action=action["action"],
                    details=action.get("details"),
                )
                for action in response_data.get("recommended_actions", [])
            ]

            return DenialExplanation(
                carc_code=code,
                category=category,
                short_description=response_data.get("short_description", ""),
                detailed_explanation=response_data.get("detailed_explanation", ""),
                common_causes=response_data.get("common_causes", []),
                recommended_actions=recommended_actions,
                related_codes=response_data.get("related_codes"),
            )

        except json.JSONDecodeError:
            logger.warning("Failed to parse LLM response as JSON for denial code")
            # Return basic result from document content
            doc = documents[0]
            return DenialExplanation(
                carc_code=code,
                category=DenialCategory.OTHER,
                short_description=doc.content[:100] if doc.content else "Unknown denial reason",
                detailed_explanation=doc.content,
                common_causes=[],
                recommended_actions=[
                    RecommendedAction(
                        priority=1,
                        action="Review claim details and contact payer for clarification",
                        details=None,
                    )
                ],
                related_codes=None,
            )

    async def lookup_prior_auth(self, params: PriorAuthParams) -> PriorAuthResult:
        """Look up prior authorization requirements using RAG.

        Requirements: 10.1, 10.2, 13.1, 13.2, 13.3
        """
        # Build search query
        query = (
            f"Prior authorization requirements for CPT code {params.cpt_code} "
            f"with payer {params.payer}"
        )
        if params.plan_type:
            query += f" for {params.plan_type} plan"

        # Build metadata filter
        filter_metadata = {"payer": params.payer.lower()}

        # Retrieve relevant documents
        documents = await self._retrieve_documents(query, filter_metadata)

        confidence = self._calculate_confidence(documents)
        citations = self._build_citations_from_documents(documents)

        if not documents:
            # Return unknown payer result
            return PriorAuthResult(
                cpt_code=params.cpt_code,
                payer=params.payer,
                is_required=False,
                plan_variations=None,
                submission_requirements=None,
                typical_turnaround=None,
                urgent_exceptions=None,
                contact_info=f"Contact {params.payer} directly for prior auth requirements",
                sources=citations
                or [
                    Citation(
                        source_type="RAG",
                        document_id="RAG-PA-UNKNOWN",
                        document_title="Prior Auth Database - Payer Not Found",
                        effective_date=self._last_updated,
                    )
                ],
            )

        # Generate response using LLM
        system_prompt = """You are a medical billing expert assistant. Analyze the provided prior authorization 
policy documents and determine the requirements.

Your response must be a valid JSON object with the following structure:
{
    "is_required": boolean,
    "plan_variations": [{"plan_type": "type", "is_required": boolean, "notes": "optional notes"}] or null,
    "submission_requirements": ["list of requirements"] or null,
    "typical_turnaround": "turnaround time" or null,
    "urgent_exceptions": ["list of exceptions"] or null,
    "contact_info": "contact information" or null
}

Base your response ONLY on the provided documents."""

        try:
            response_text = await self._generate_response(query, documents, system_prompt)
            response_data = json.loads(response_text)

            plan_variations = None
            if response_data.get("plan_variations"):
                plan_variations = [
                    PlanVariation(
                        plan_type=pv["plan_type"],
                        is_required=pv["is_required"],
                        notes=pv.get("notes"),
                    )
                    for pv in response_data["plan_variations"]
                ]

            return PriorAuthResult(
                cpt_code=params.cpt_code,
                payer=params.payer,
                is_required=response_data.get("is_required", False),
                plan_variations=plan_variations,
                submission_requirements=response_data.get("submission_requirements"),
                typical_turnaround=response_data.get("typical_turnaround"),
                urgent_exceptions=response_data.get("urgent_exceptions"),
                contact_info=response_data.get("contact_info"),
                sources=citations,
            )

        except json.JSONDecodeError:
            logger.warning("Failed to parse LLM response as JSON for prior auth")
            return PriorAuthResult(
                cpt_code=params.cpt_code,
                payer=params.payer,
                is_required=True,  # Default to required for safety
                plan_variations=None,
                submission_requirements=["Contact payer for specific requirements"],
                typical_turnaround=None,
                urgent_exceptions=None,
                contact_info=f"Contact {params.payer} directly",
                sources=citations,
            )

    def get_data_source_info(self) -> DataSourceInfo:
        """Get information about the RAG knowledge service data source.

        Requirements: 6.4, 13.6
        """
        coverage_areas = [
            f"Vector Store: {self.config.vector_store_type}",
            f"Collection: {self.config.collection_name}",
            f"LLM Provider: {self.config.llm_provider}",
            f"LLM Model: {self.config.llm_model}",
        ]

        return DataSourceInfo(
            type=DataSource.RAG,
            last_updated=self._last_updated,
            coverage=coverage_areas,
        )

    async def add_documents(
        self,
        documents: list[dict[str, Any]],
    ) -> int:
        """Add documents to the vector store.

        Args:
            documents: List of documents with 'content' and 'metadata' keys.

        Returns:
            Number of documents added.
        """
        self._ensure_initialized()

        from langchain_core.documents import Document

        langchain_docs = [
            Document(
                page_content=doc["content"],
                metadata=doc.get("metadata", {}),
            )
            for doc in documents
        ]

        self._vector_store.add_documents(langchain_docs)
        self._last_updated = datetime.now(UTC)

        logger.info(f"Added {len(documents)} documents to vector store")
        return len(documents)

    async def search_hybrid(
        self,
        query: str,
        keyword_filter: Optional[str] = None,
        metadata_filter: Optional[dict[str, Any]] = None,
    ) -> list[RetrievedDocument]:
        """Perform hybrid search combining semantic and keyword matching.

        Requirements: 10.6

        Args:
            query: Semantic search query.
            keyword_filter: Optional keyword to filter results.
            metadata_filter: Optional metadata filters.

        Returns:
            List of retrieved documents.
        """
        # Get semantic search results
        documents = await self._retrieve_documents(query, metadata_filter)

        # Apply keyword filter if provided
        if keyword_filter:
            keyword_lower = keyword_filter.lower()
            documents = [
                doc
                for doc in documents
                if keyword_lower in doc.content.lower()
                or keyword_lower in str(doc.metadata).lower()
            ]

        return documents
