"""Ingestion API endpoints for Medical Billing Copilot.

This module provides REST API endpoints for managing the data ingestion pipeline.

Requirements: 11.5, 11.6, 11.7
"""

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

router = APIRouter(prefix="/api/ingestion", tags=["ingestion"])

# Global orchestrator instance (in production, use dependency injection)
_orchestrator: Optional[IngestionOrchestrator] = None


def get_orchestrator() -> IngestionOrchestrator:
    """Get the ingestion orchestrator instance."""
    global _orchestrator
    if _orchestrator is None:
        _orchestrator = IngestionOrchestrator()
    return _orchestrator


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
