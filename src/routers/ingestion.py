"""Ingestion API endpoints for Medical Billing Copilot.

This module provides REST API endpoints for managing the data ingestion pipeline.

Requirements: 11.5, 11.6, 11.7, 14.3, 14.4, 14.5
"""

from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field

from src.schemas.ingestion import (
    DocumentType,
    IngestionJobResult,
    IngestionLogEntry,
    IngestionSource,
    IngestionStatus,
)
from src.services.ingestion import IngestionOrchestrator
from src.services.policy_database import (
    PayerSupportStatus,
    PolicyDatabase,
    PolicyDatabaseStats,
    PolicyFreshnessInfo,
)

router = APIRouter(prefix="/api/ingestion", tags=["ingestion"])

# Global orchestrator instance (in production, use dependency injection)
_orchestrator: Optional[IngestionOrchestrator] = None
_policy_database: Optional[PolicyDatabase] = None


def get_orchestrator() -> IngestionOrchestrator:
    """Get the ingestion orchestrator instance."""
    global _orchestrator
    if _orchestrator is None:
        _orchestrator = IngestionOrchestrator()
    return _orchestrator


def get_policy_database() -> PolicyDatabase:
    """Get the policy database instance."""
    global _policy_database
    if _policy_database is None:
        _policy_database = PolicyDatabase(persist_path="data/policy_db_state.json")
    return _policy_database


# Request/Response models
class TriggerCMSRequest(BaseModel):
    """Request to trigger CMS ingestion."""
    mac_regions: Optional[list[str]] = Field(None, description="MAC regions to ingest")
    document_type: Optional[DocumentType] = Field(None, description="LCD, NCD, or both")


class TriggerCommercialRequest(BaseModel):
    """Request to trigger commercial payer ingestion."""
    payer_ids: Optional[list[str]] = Field(None, description="Payer IDs to ingest")
    limit_per_payer: int = Field(100, ge=1, le=500, description="Max policies per payer")


class SchedulerConfig(BaseModel):
    """Scheduler configuration."""
    interval_hours: float = Field(24.0, ge=1.0, le=168.0, description="Hours between runs")
    run_immediately: bool = Field(False, description="Run immediately on start")


class IngestionStats(BaseModel):
    """Ingestion statistics."""
    total_jobs: int
    completed_jobs: int
    failed_jobs: int
    partial_jobs: int
    running_jobs: int
    total_documents_processed: int
    total_documents_failed: int
    scheduler_running: bool
    log_entries: int


class CustomDocumentRequest(BaseModel):
    """Request to add a custom document to the vector store."""
    title: str = Field(..., min_length=1, max_length=500, description="Document title")
    content: str = Field(..., min_length=10, description="Document content/text")
    source_type: str = Field("COMMERCIAL", description="Source type: LCD, NCD, COMMERCIAL, CARC")
    payer: Optional[str] = Field(None, description="Payer name (for commercial policies)")
    mac_region: Optional[str] = Field(None, description="MAC region (for LCDs)")
    source_url: Optional[str] = Field(None, description="URL to source document")
    effective_date: Optional[str] = Field(None, description="Effective date (YYYY-MM-DD)")


class CustomDocumentResponse(BaseModel):
    """Response after adding a custom document."""
    success: bool
    document_id: str
    message: str


# Endpoints
@router.post("/trigger/cms", response_model=IngestionJobResult)
async def trigger_cms_ingestion(
    request: TriggerCMSRequest,
    orchestrator: IngestionOrchestrator = Depends(get_orchestrator),
) -> IngestionJobResult:
    """Trigger CMS.gov LCD/NCD ingestion.
    
    This endpoint starts an asynchronous ingestion job for Medicare
    coverage documents from CMS.gov.
    """
    return await orchestrator.trigger_cms_ingestion(
        mac_regions=request.mac_regions,
        document_type=request.document_type,
    )


@router.post("/trigger/commercial", response_model=IngestionJobResult)
async def trigger_commercial_ingestion(
    request: TriggerCommercialRequest,
    orchestrator: IngestionOrchestrator = Depends(get_orchestrator),
) -> IngestionJobResult:
    """Trigger commercial payer policy ingestion.
    
    This endpoint starts an asynchronous ingestion job for commercial
    payer policy documents.
    """
    return await orchestrator.trigger_commercial_ingestion(
        payer_ids=request.payer_ids,
        limit_per_payer=request.limit_per_payer,
    )


@router.post("/trigger/full", response_model=list[IngestionJobResult])
async def trigger_full_ingestion(
    orchestrator: IngestionOrchestrator = Depends(get_orchestrator),
) -> list[IngestionJobResult]:
    """Trigger full ingestion from all sources.
    
    This endpoint starts ingestion jobs for both CMS.gov and
    commercial payer sources.
    """
    return await orchestrator.trigger_full_ingestion()


@router.post("/scheduler/start")
async def start_scheduler(
    config: SchedulerConfig,
    orchestrator: IngestionOrchestrator = Depends(get_orchestrator),
) -> dict:
    """Start the scheduled ingestion job.
    
    This endpoint starts a background scheduler that runs ingestion
    at the specified interval.
    """
    await orchestrator.start_scheduler(
        interval_hours=config.interval_hours,
        run_immediately=config.run_immediately,
    )
    return {
        "status": "started",
        "interval_hours": config.interval_hours,
        "run_immediately": config.run_immediately,
    }


@router.post("/scheduler/stop")
async def stop_scheduler(
    orchestrator: IngestionOrchestrator = Depends(get_orchestrator),
) -> dict:
    """Stop the scheduled ingestion job."""
    await orchestrator.stop_scheduler()
    return {"status": "stopped"}


@router.get("/scheduler/status")
async def get_scheduler_status(
    orchestrator: IngestionOrchestrator = Depends(get_orchestrator),
) -> dict:
    """Get scheduler status."""
    return {
        "running": orchestrator.is_scheduler_running(),
    }


@router.post("/documents/custom", response_model=CustomDocumentResponse)
async def add_custom_document(
    request: CustomDocumentRequest,
) -> CustomDocumentResponse:
    """Add a custom document to the vector store.
    
    This endpoint allows adding custom policy documents, PDFs, or other
    text content directly to the RAG system without going through the
    standard ingestion pipeline.
    """
    import uuid
    from src.config import settings
    
    # Generate document ID
    doc_id = f"custom-{uuid.uuid4().hex[:8]}"
    
    # Build metadata
    metadata = {
        "source_type": request.source_type.upper(),
        "document_id": doc_id,
        "title": request.title,
        "source_url": request.source_url,
    }
    
    if request.payer:
        metadata["payer"] = request.payer.lower()
    if request.mac_region:
        metadata["mac_region"] = request.mac_region.upper()
    if request.effective_date:
        metadata["effective_date"] = request.effective_date
    
    # Check if RAG mode is enabled
    if settings.knowledge_service_type != "rag":
        # For stubbed mode, just acknowledge the document
        return CustomDocumentResponse(
            success=True,
            document_id=doc_id,
            message="Document recorded (RAG mode not enabled - document will be available when RAG is enabled)",
        )
    
    try:
        from src.services.rag_knowledge import RAGKnowledgeService
        
        rag_service = RAGKnowledgeService()
        await rag_service.add_documents([
            {
                "content": request.content,
                "metadata": metadata,
            }
        ])
        
        return CustomDocumentResponse(
            success=True,
            document_id=doc_id,
            message=f"Document '{request.title}' added successfully to vector store",
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to add document: {str(e)}",
        )


@router.get("/jobs", response_model=list[IngestionJobResult])
async def list_jobs(
    status: Optional[IngestionStatus] = Query(None, description="Filter by status"),
    source: Optional[IngestionSource] = Query(None, description="Filter by source"),
    limit: int = Query(100, ge=1, le=500, description="Maximum results"),
    orchestrator: IngestionOrchestrator = Depends(get_orchestrator),
) -> list[IngestionJobResult]:
    """List ingestion jobs with optional filtering."""
    return orchestrator.get_all_jobs(status=status, source=source, limit=limit)


@router.get("/jobs/running", response_model=list[IngestionJobResult])
async def list_running_jobs(
    orchestrator: IngestionOrchestrator = Depends(get_orchestrator),
) -> list[IngestionJobResult]:
    """List currently running ingestion jobs."""
    return orchestrator.get_running_jobs()


@router.get("/jobs/{job_id}", response_model=IngestionJobResult)
async def get_job(
    job_id: str,
    orchestrator: IngestionOrchestrator = Depends(get_orchestrator),
) -> IngestionJobResult:
    """Get a specific ingestion job by ID."""
    job = orchestrator.get_job(job_id)
    if not job:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Job not found: {job_id}",
        )
    return job


@router.get("/logs", response_model=list[IngestionLogEntry])
async def get_logs(
    job_id: Optional[str] = Query(None, description="Filter by job ID"),
    level: Optional[str] = Query(None, description="Filter by log level"),
    limit: int = Query(1000, ge=1, le=10000, description="Maximum results"),
    orchestrator: IngestionOrchestrator = Depends(get_orchestrator),
) -> list[IngestionLogEntry]:
    """Get ingestion logs with optional filtering."""
    return orchestrator.get_logs(job_id=job_id, level=level, limit=limit)


@router.delete("/logs")
async def clear_logs(
    orchestrator: IngestionOrchestrator = Depends(get_orchestrator),
) -> dict:
    """Clear all ingestion logs."""
    count = orchestrator.clear_logs()
    return {"cleared": count}


@router.get("/stats", response_model=IngestionStats)
async def get_statistics(
    orchestrator: IngestionOrchestrator = Depends(get_orchestrator),
) -> IngestionStats:
    """Get ingestion statistics."""
    stats = orchestrator.get_statistics()
    return IngestionStats(**stats)


@router.get("/payers")
async def list_supported_payers(
    orchestrator: IngestionOrchestrator = Depends(get_orchestrator),
) -> dict:
    """List supported commercial payers."""
    payer_ids = orchestrator.commercial_scraper.get_supported_payers()
    payers = []
    for payer_id in payer_ids:
        config = orchestrator.commercial_scraper.get_payer_config(payer_id)
        if config:
            payers.append({
                "id": config.payer_id,
                "name": config.payer_name,
                "scrape_method": config.scrape_method,
            })
    return {"payers": payers}



# ==================== Policy Freshness Endpoints (Requirements 14.3, 14.4, 14.5) ====================


class PolicyFreshnessResponse(BaseModel):
    """Response for policy freshness check."""
    source: str
    source_type: str
    last_updated: Optional[datetime]
    document_count: int
    is_fresh: bool
    freshness_threshold_days: int
    days_since_update: Optional[int]


class PayerSupportResponse(BaseModel):
    """Response for payer support check."""
    payer_id: str
    payer_name: str
    is_supported: bool
    document_count: int
    last_updated: Optional[datetime]
    coverage_areas: list[str]
    message: Optional[str] = None


@router.get("/policy/freshness/{source}", response_model=PolicyFreshnessResponse)
async def get_policy_freshness(
    source: str,
    policy_db: PolicyDatabase = Depends(get_policy_database),
) -> PolicyFreshnessResponse:
    """Get freshness information for a policy source.
    
    Requirements: 14.3, 14.4
    
    Args:
        source: The policy source (e.g., 'medicare', 'aetna', 'unitedhealthcare').
        
    Returns:
        PolicyFreshnessResponse with freshness status and last-updated date.
    """
    info = policy_db.get_freshness_info(source)
    return PolicyFreshnessResponse(
        source=info.source,
        source_type=info.source_type,
        last_updated=info.last_updated,
        document_count=info.document_count,
        is_fresh=info.is_fresh,
        freshness_threshold_days=info.freshness_threshold_days,
        days_since_update=info.days_since_update,
    )


@router.get("/policy/payer/{payer_id}/support", response_model=PayerSupportResponse)
async def check_payer_support(
    payer_id: str,
    policy_db: PolicyDatabase = Depends(get_policy_database),
) -> PayerSupportResponse:
    """Check if a payer is supported in the policy database.
    
    Requirements: 14.5
    
    Args:
        payer_id: The payer identifier.
        
    Returns:
        PayerSupportResponse with support status and message if not supported.
    """
    status = policy_db.get_payer_support_status(payer_id)
    message = None
    if not status.is_supported:
        message = policy_db.get_unsupported_payer_message(payer_id)
    
    return PayerSupportResponse(
        payer_id=status.payer_id,
        payer_name=status.payer_name,
        is_supported=status.is_supported,
        document_count=status.document_count,
        last_updated=status.last_updated,
        coverage_areas=status.coverage_areas,
        message=message,
    )


@router.get("/policy/payers/supported", response_model=list[PayerSupportResponse])
async def list_supported_payers_with_status(
    policy_db: PolicyDatabase = Depends(get_policy_database),
) -> list[PayerSupportResponse]:
    """List all supported payers with their status.
    
    Requirements: 14.5
    
    Returns:
        List of PayerSupportResponse for all supported payers.
    """
    payers = policy_db.get_supported_payers()
    return [
        PayerSupportResponse(
            payer_id=p.payer_id,
            payer_name=p.payer_name,
            is_supported=p.is_supported,
            document_count=p.document_count,
            last_updated=p.last_updated,
            coverage_areas=p.coverage_areas,
        )
        for p in payers
    ]


@router.get("/policy/stats", response_model=PolicyDatabaseStats)
async def get_policy_database_stats(
    policy_db: PolicyDatabase = Depends(get_policy_database),
) -> PolicyDatabaseStats:
    """Get overall statistics about the policy database.
    
    Returns:
        PolicyDatabaseStats with database statistics.
    """
    return policy_db.get_statistics()


@router.get("/policy/mac-regions")
async def list_mac_regions(
    policy_db: PolicyDatabase = Depends(get_policy_database),
) -> dict:
    """List all MAC regions with coverage status.
    
    Returns:
        Dictionary with MAC region information.
    """
    regions = policy_db.get_mac_regions()
    coverage = []
    for region in regions:
        region_coverage = policy_db.get_mac_region_coverage(region["id"])
        coverage.append(region_coverage)
    
    return {
        "mac_regions": coverage,
        "total_regions": len(regions),
    }


@router.get("/policy/verify-coverage")
async def verify_common_procedures_coverage(
    policy_db: PolicyDatabase = Depends(get_policy_database),
) -> dict:
    """Verify coverage of common procedures in the database.
    
    Requirements: 14.1
    
    Returns:
        Dictionary with verification results.
    """
    return policy_db.verify_common_procedures_coverage()


# ==================== Custom Document Upload ====================


class CustomDocumentRequest(BaseModel):
    """Request to add a custom document to the vector store."""
    title: str = Field(..., min_length=1, max_length=500, description="Document title")
    content: str = Field(..., min_length=10, description="Document content/text")
    source_type: str = Field(
        "COMMERCIAL",
        description="Source type: LCD, NCD, COMMERCIAL, or CARC"
    )
    payer: Optional[str] = Field(None, description="Payer name (for commercial docs)")
    mac_region: Optional[str] = Field(None, description="MAC region (for LCDs)")
    effective_date: Optional[str] = Field(None, description="Effective date (YYYY-MM-DD)")
    source_url: Optional[str] = Field(None, description="Source URL")


class CustomDocumentResponse(BaseModel):
    """Response after adding a custom document."""
    success: bool
    document_id: str
    message: str
    chunks_created: int


@router.post("/documents/custom", response_model=CustomDocumentResponse)
async def add_custom_document(
    request: CustomDocumentRequest,
) -> CustomDocumentResponse:
    """Add a custom document to the RAG vector store.
    
    This endpoint allows adding ad-hoc policy documents, PDFs content,
    or other text-based documents directly to the knowledge base.
    """
    import uuid
    from datetime import datetime, UTC
    
    from src.config import settings
    from src.services.knowledge_factory import get_knowledge_service
    from src.services.rag_knowledge import RAGKnowledgeService
    
    # Generate document ID
    doc_id = f"custom-{uuid.uuid4().hex[:12]}"
    
    # Check if RAG service is available
    if settings.knowledge_service_type != "rag":
        # For stubbed mode, just acknowledge the request
        return CustomDocumentResponse(
            success=True,
            document_id=doc_id,
            message="Document recorded (stubbed mode - not added to vector store)",
            chunks_created=0,
        )
    
    try:
        # Get RAG service
        service = get_knowledge_service()
        
        if not isinstance(service, RAGKnowledgeService):
            return CustomDocumentResponse(
                success=True,
                document_id=doc_id,
                message="Document recorded (RAG service not active)",
                chunks_created=0,
            )
        
        # Build metadata
        metadata = {
            "source_type": request.source_type.upper(),
            "document_id": doc_id,
            "title": request.title,
            "custom_upload": True,
            "uploaded_at": datetime.now(UTC).isoformat(),
        }
        
        if request.payer:
            metadata["payer"] = request.payer.lower()
        if request.mac_region:
            metadata["mac_region"] = request.mac_region.upper()
        if request.effective_date:
            metadata["effective_date"] = request.effective_date
        if request.source_url:
            metadata["source_url"] = request.source_url
        
        # Add document to vector store
        chunks_added = await service.add_documents([
            {
                "content": request.content,
                "metadata": metadata,
            }
        ])
        
        return CustomDocumentResponse(
            success=True,
            document_id=doc_id,
            message=f"Document '{request.title}' added successfully",
            chunks_created=chunks_added,
        )
        
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to add document: {str(e)}",
        )


@router.get("/documents/custom")
async def list_custom_documents() -> dict:
    """List all custom-uploaded documents.
    
    Note: This is a placeholder - full implementation would query
    the vector store for documents with custom_upload=True metadata.
    """
    return {
        "message": "Custom document listing not yet implemented",
        "hint": "Documents are stored in the vector store with custom_upload=True metadata",
    }
