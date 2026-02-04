"""Ingestion pipeline schemas for Medical Billing Copilot."""

from datetime import datetime
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


class DocumentType(str, Enum):
    """Type of policy document."""
    LCD = "LCD"
    NCD = "NCD"
    COMMERCIAL = "COMMERCIAL"


class IngestionStatus(str, Enum):
    """Status of an ingestion job."""
    PENDING = "PENDING"
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    PARTIAL = "PARTIAL"


class IngestionSource(str, Enum):
    """Source of ingestion data."""
    CMS_GOV = "CMS_GOV"
    COMMERCIAL_PAYER = "COMMERCIAL_PAYER"
    MANUAL = "MANUAL"


class DocumentMetadata(BaseModel):
    """Metadata for an ingested document."""
    document_id: str = Field(..., description="Unique document identifier")
    document_type: DocumentType = Field(..., description="Type of document")
    title: str = Field(..., description="Document title")
    source_url: str = Field(..., description="Source URL")
    payer: Optional[str] = Field(None, description="Payer name")
    mac_region: Optional[str] = Field(None, description="MAC region for LCDs")
    effective_date: Optional[datetime] = Field(None, description="Effective date")
    last_updated: Optional[datetime] = Field(None, description="Last update date")
    version: Optional[str] = Field(None, description="Document version")


class DocumentChunk(BaseModel):
    """A chunk of text from a document."""
    chunk_id: str = Field(..., description="Unique chunk identifier")
    document_id: str = Field(..., description="Parent document ID")
    content: str = Field(..., description="Text content")
    chunk_index: int = Field(..., description="Index within document")
    metadata: dict = Field(default_factory=dict, description="Additional metadata")


class IngestedDocument(BaseModel):
    """A fully ingested document with content and metadata."""
    metadata: DocumentMetadata = Field(..., description="Document metadata")
    content: str = Field(..., description="Full text content")
    chunks: list[DocumentChunk] = Field(default_factory=list, description="Document chunks")


class IngestionJobResult(BaseModel):
    """Result of an ingestion job."""
    job_id: str = Field(..., description="Job identifier")
    source: IngestionSource = Field(..., description="Ingestion source")
    status: IngestionStatus = Field(..., description="Job status")
    started_at: datetime = Field(..., description="Job start time")
    completed_at: Optional[datetime] = Field(None, description="Job completion time")
    documents_processed: int = Field(0, description="Number of documents processed")
    documents_failed: int = Field(0, description="Number of documents that failed")
    error_message: Optional[str] = Field(None, description="Error message if failed")
    details: dict = Field(default_factory=dict, description="Additional details")


class IngestionLogEntry(BaseModel):
    """Log entry for ingestion activity."""
    id: str = Field(..., description="Log entry ID")
    job_id: str = Field(..., description="Associated job ID")
    timestamp: datetime = Field(..., description="Log timestamp")
    level: str = Field(..., description="Log level (INFO, WARNING, ERROR)")
    message: str = Field(..., description="Log message")
    document_id: Optional[str] = Field(None, description="Related document ID")


class CMSSearchParams(BaseModel):
    """Parameters for CMS.gov LCD/NCD search."""
    mac_region: Optional[str] = Field(None, description="MAC region filter")
    cpt_code: Optional[str] = Field(None, description="CPT code filter")
    keyword: Optional[str] = Field(None, description="Keyword search")
    document_type: Optional[DocumentType] = Field(None, description="LCD or NCD")
    limit: int = Field(100, ge=1, le=500, description="Maximum results")


class CommercialPayerConfig(BaseModel):
    """Configuration for commercial payer scraping."""
    payer_id: str = Field(..., description="Payer identifier")
    payer_name: str = Field(..., description="Payer display name")
    base_url: str = Field(..., description="Base URL for policy documents")
    policy_list_url: Optional[str] = Field(None, description="URL for policy listing")
    requires_auth: bool = Field(False, description="Whether authentication is required")
    scrape_method: str = Field("html", description="Scraping method: html or pdf")
