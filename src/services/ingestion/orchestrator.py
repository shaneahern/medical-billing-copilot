"""Ingestion orchestration service for Medical Billing Copilot.

This module provides orchestration for the data ingestion pipeline,
including scheduled batch jobs, manual triggers, and activity logging.

Requirements: 11.5, 11.6, 11.7
"""

import asyncio
import logging
import uuid
from datetime import datetime
from typing import Callable, Optional

from src.schemas.ingestion import (
    CMSSearchParams,
    DocumentType,
    IngestedDocument,
    IngestionJobResult,
    IngestionLogEntry,
    IngestionSource,
    IngestionStatus,
)
from src.services.ingestion.cms_scraper import CMSScraper
from src.services.ingestion.commercial_scraper import CommercialPayerScraper

logger = logging.getLogger(__name__)


class IngestionOrchestrator:
    """Orchestrates the data ingestion pipeline.
    
    This class handles:
    - Scheduling batch ingestion jobs
    - Manual trigger for on-demand ingestion
    - Logging all ingestion activities
    - Coordinating between different scrapers
    
    Requirements: 11.5, 11.6, 11.7
    """

    def __init__(
        self,
        cms_scraper: Optional[CMSScraper] = None,
        commercial_scraper: Optional[CommercialPayerScraper] = None,
        on_document_ingested: Optional[Callable[[IngestedDocument], None]] = None,
    ):
        """Initialize the ingestion orchestrator.
        
        Args:
            cms_scraper: CMS.gov scraper instance.
            commercial_scraper: Commercial payer scraper instance.
            on_document_ingested: Callback for when a document is ingested.
        """
        self.cms_scraper = cms_scraper or CMSScraper()
        self.commercial_scraper = commercial_scraper or CommercialPayerScraper()
        self.on_document_ingested = on_document_ingested
        
        # Job tracking
        self._jobs: dict[str, IngestionJobResult] = {}
        self._logs: list[IngestionLogEntry] = []
        self._running_jobs: set[str] = set()
        
        # Scheduler state
        self._scheduler_task: Optional[asyncio.Task] = None
        self._scheduler_running = False

    async def close(self) -> None:
        """Clean up resources."""
        await self.stop_scheduler()
        await self.cms_scraper.close()
        await self.commercial_scraper.close()

    # ==================== Manual Triggers ====================

    async def trigger_cms_ingestion(
        self,
        mac_regions: Optional[list[str]] = None,
        document_type: Optional[DocumentType] = None,
    ) -> IngestionJobResult:
        """Manually trigger CMS.gov ingestion.
        
        Args:
            mac_regions: Specific MAC regions to ingest. If None, ingests all.
            document_type: LCD, NCD, or both if None.
            
        Returns:
            IngestionJobResult with job status and statistics.
        """
        job_id = str(uuid.uuid4())
        job = IngestionJobResult(
            job_id=job_id,
            source=IngestionSource.CMS_GOV,
            status=IngestionStatus.RUNNING,
            started_at=datetime.utcnow(),
            details={
                "mac_regions": mac_regions,
                "document_type": document_type.value if document_type else "ALL",
            },
        )
        
        self._jobs[job_id] = job
        self._running_jobs.add(job_id)
        self._log(job_id, "INFO", f"Starting CMS ingestion job")
        
        try:
            documents_processed = 0
            documents_failed = 0
            
            # Ingest LCDs
            if document_type is None or document_type == DocumentType.LCD:
                self._log(job_id, "INFO", "Ingesting LCDs...")
                try:
                    lcd_docs = await self.cms_scraper.scrape_all_lcds(mac_regions)
                    for doc in lcd_docs:
                        try:
                            await self._process_document(job_id, doc)
                            documents_processed += 1
                        except Exception as e:
                            documents_failed += 1
                            self._log(
                                job_id, "ERROR",
                                f"Failed to process LCD {doc.metadata.document_id}: {e}",
                                doc.metadata.document_id
                            )
                except Exception as e:
                    self._log(job_id, "ERROR", f"LCD ingestion failed: {e}")
            
            # Ingest NCDs
            if document_type is None or document_type == DocumentType.NCD:
                self._log(job_id, "INFO", "Ingesting NCDs...")
                try:
                    ncd_docs = await self.cms_scraper.scrape_all_ncds()
                    for doc in ncd_docs:
                        try:
                            await self._process_document(job_id, doc)
                            documents_processed += 1
                        except Exception as e:
                            documents_failed += 1
                            self._log(
                                job_id, "ERROR",
                                f"Failed to process NCD {doc.metadata.document_id}: {e}",
                                doc.metadata.document_id
                            )
                except Exception as e:
                    self._log(job_id, "ERROR", f"NCD ingestion failed: {e}")
            
            # Update job status
            job.documents_processed = documents_processed
            job.documents_failed = documents_failed
            job.completed_at = datetime.utcnow()
            job.status = (
                IngestionStatus.COMPLETED if documents_failed == 0
                else IngestionStatus.PARTIAL if documents_processed > 0
                else IngestionStatus.FAILED
            )
            
            self._log(
                job_id, "INFO",
                f"CMS ingestion completed: {documents_processed} processed, {documents_failed} failed"
            )
            
        except Exception as e:
            job.status = IngestionStatus.FAILED
            job.error_message = str(e)
            job.completed_at = datetime.utcnow()
            self._log(job_id, "ERROR", f"CMS ingestion job failed: {e}")
            
        finally:
            self._running_jobs.discard(job_id)
        
        return job

    async def trigger_commercial_ingestion(
        self,
        payer_ids: Optional[list[str]] = None,
        limit_per_payer: int = 100,
    ) -> IngestionJobResult:
        """Manually trigger commercial payer ingestion.
        
        Args:
            payer_ids: Specific payers to ingest. If None, ingests all supported.
            limit_per_payer: Maximum policies per payer.
            
        Returns:
            IngestionJobResult with job status and statistics.
        """
        job_id = str(uuid.uuid4())
        
        # Get payer list
        if payer_ids is None:
            payer_ids = self.commercial_scraper.get_supported_payers()
        
        job = IngestionJobResult(
            job_id=job_id,
            source=IngestionSource.COMMERCIAL_PAYER,
            status=IngestionStatus.RUNNING,
            started_at=datetime.utcnow(),
            details={
                "payer_ids": payer_ids,
                "limit_per_payer": limit_per_payer,
            },
        )
        
        self._jobs[job_id] = job
        self._running_jobs.add(job_id)
        self._log(job_id, "INFO", f"Starting commercial payer ingestion for: {payer_ids}")
        
        try:
            documents_processed = 0
            documents_failed = 0
            
            for payer_id in payer_ids:
                self._log(job_id, "INFO", f"Ingesting policies for {payer_id}...")
                try:
                    docs = await self.commercial_scraper.scrape_payer_policies(
                        payer_id, limit=limit_per_payer
                    )
                    for doc in docs:
                        try:
                            await self._process_document(job_id, doc)
                            documents_processed += 1
                        except Exception as e:
                            documents_failed += 1
                            self._log(
                                job_id, "ERROR",
                                f"Failed to process {payer_id} policy {doc.metadata.document_id}: {e}",
                                doc.metadata.document_id
                            )
                except Exception as e:
                    self._log(job_id, "ERROR", f"Failed to scrape {payer_id}: {e}")
            
            # Update job status
            job.documents_processed = documents_processed
            job.documents_failed = documents_failed
            job.completed_at = datetime.utcnow()
            job.status = (
                IngestionStatus.COMPLETED if documents_failed == 0
                else IngestionStatus.PARTIAL if documents_processed > 0
                else IngestionStatus.FAILED
            )
            
            self._log(
                job_id, "INFO",
                f"Commercial ingestion completed: {documents_processed} processed, {documents_failed} failed"
            )
            
        except Exception as e:
            job.status = IngestionStatus.FAILED
            job.error_message = str(e)
            job.completed_at = datetime.utcnow()
            self._log(job_id, "ERROR", f"Commercial ingestion job failed: {e}")
            
        finally:
            self._running_jobs.discard(job_id)
        
        return job

    async def trigger_full_ingestion(self) -> list[IngestionJobResult]:
        """Trigger full ingestion from all sources.
        
        Returns:
            List of job results for each source.
        """
        self._log("system", "INFO", "Starting full ingestion from all sources")
        
        results = []
        
        # Run CMS and commercial ingestion in parallel
        cms_task = asyncio.create_task(self.trigger_cms_ingestion())
        commercial_task = asyncio.create_task(self.trigger_commercial_ingestion())
        
        cms_result = await cms_task
        commercial_result = await commercial_task
        
        results.append(cms_result)
        results.append(commercial_result)
        
        self._log("system", "INFO", "Full ingestion completed")
        return results

    # ==================== Scheduled Jobs ====================

    async def start_scheduler(
        self,
        interval_hours: float = 24.0,
        run_immediately: bool = False,
    ) -> None:
        """Start the scheduled ingestion job.
        
        Args:
            interval_hours: Hours between ingestion runs.
            run_immediately: Whether to run immediately on start.
        """
        if self._scheduler_running:
            logger.warning("Scheduler is already running")
            return
        
        self._scheduler_running = True
        self._log("scheduler", "INFO", f"Starting scheduler with {interval_hours}h interval")
        
        async def scheduler_loop():
            if run_immediately:
                await self.trigger_full_ingestion()
            
            while self._scheduler_running:
                try:
                    # Wait for next interval
                    await asyncio.sleep(interval_hours * 3600)
                    
                    if self._scheduler_running:
                        await self.trigger_full_ingestion()
                        
                except asyncio.CancelledError:
                    break
                except Exception as e:
                    self._log("scheduler", "ERROR", f"Scheduler error: {e}")
        
        self._scheduler_task = asyncio.create_task(scheduler_loop())

    async def stop_scheduler(self) -> None:
        """Stop the scheduled ingestion job."""
        if not self._scheduler_running:
            return
        
        self._scheduler_running = False
        self._log("scheduler", "INFO", "Stopping scheduler")
        
        if self._scheduler_task:
            self._scheduler_task.cancel()
            try:
                await self._scheduler_task
            except asyncio.CancelledError:
                pass
            self._scheduler_task = None

    def is_scheduler_running(self) -> bool:
        """Check if the scheduler is running."""
        return self._scheduler_running

    # ==================== Job Management ====================

    def get_job(self, job_id: str) -> Optional[IngestionJobResult]:
        """Get a job by ID."""
        return self._jobs.get(job_id)

    def get_all_jobs(
        self,
        status: Optional[IngestionStatus] = None,
        source: Optional[IngestionSource] = None,
        limit: int = 100,
    ) -> list[IngestionJobResult]:
        """Get all jobs with optional filtering.
        
        Args:
            status: Filter by status.
            source: Filter by source.
            limit: Maximum number of jobs to return.
            
        Returns:
            List of matching jobs, most recent first.
        """
        jobs = list(self._jobs.values())
        
        if status:
            jobs = [j for j in jobs if j.status == status]
        if source:
            jobs = [j for j in jobs if j.source == source]
        
        # Sort by start time, most recent first
        jobs.sort(key=lambda j: j.started_at, reverse=True)
        
        return jobs[:limit]

    def get_running_jobs(self) -> list[IngestionJobResult]:
        """Get all currently running jobs."""
        return [
            self._jobs[job_id]
            for job_id in self._running_jobs
            if job_id in self._jobs
        ]

    # ==================== Logging ====================

    def get_logs(
        self,
        job_id: Optional[str] = None,
        level: Optional[str] = None,
        limit: int = 1000,
    ) -> list[IngestionLogEntry]:
        """Get ingestion logs with optional filtering.
        
        Args:
            job_id: Filter by job ID.
            level: Filter by log level.
            limit: Maximum number of entries to return.
            
        Returns:
            List of matching log entries, most recent first.
        """
        logs = self._logs.copy()
        
        if job_id:
            logs = [l for l in logs if l.job_id == job_id]
        if level:
            logs = [l for l in logs if l.level == level]
        
        # Sort by timestamp, most recent first
        logs.sort(key=lambda l: l.timestamp, reverse=True)
        
        return logs[:limit]

    def clear_logs(self, before: Optional[datetime] = None) -> int:
        """Clear logs, optionally before a specific time.
        
        Args:
            before: Clear logs before this time. If None, clears all.
            
        Returns:
            Number of logs cleared.
        """
        if before is None:
            count = len(self._logs)
            self._logs.clear()
            return count
        
        original_count = len(self._logs)
        self._logs = [l for l in self._logs if l.timestamp >= before]
        return original_count - len(self._logs)

    def _log(
        self,
        job_id: str,
        level: str,
        message: str,
        document_id: Optional[str] = None,
    ) -> None:
        """Add a log entry."""
        entry = IngestionLogEntry(
            id=str(uuid.uuid4()),
            job_id=job_id,
            timestamp=datetime.utcnow(),
            level=level,
            message=message,
            document_id=document_id,
        )
        self._logs.append(entry)
        
        # Also log to Python logger
        log_func = getattr(logger, level.lower(), logger.info)
        log_func(f"[{job_id}] {message}")

    # ==================== Document Processing ====================

    async def _process_document(
        self, job_id: str, document: IngestedDocument
    ) -> None:
        """Process an ingested document.
        
        This method is called for each document after extraction.
        Override or set on_document_ingested callback for custom processing.
        """
        self._log(
            job_id, "INFO",
            f"Processing document: {document.metadata.document_id} - {document.metadata.title}",
            document.metadata.document_id
        )
        
        # Call callback if set
        if self.on_document_ingested:
            self.on_document_ingested(document)

    # ==================== Statistics ====================

    def get_statistics(self) -> dict:
        """Get ingestion statistics.
        
        Returns:
            Dictionary with various statistics.
        """
        total_jobs = len(self._jobs)
        completed_jobs = len([j for j in self._jobs.values() if j.status == IngestionStatus.COMPLETED])
        failed_jobs = len([j for j in self._jobs.values() if j.status == IngestionStatus.FAILED])
        partial_jobs = len([j for j in self._jobs.values() if j.status == IngestionStatus.PARTIAL])
        
        total_documents = sum(j.documents_processed for j in self._jobs.values())
        total_failures = sum(j.documents_failed for j in self._jobs.values())
        
        return {
            "total_jobs": total_jobs,
            "completed_jobs": completed_jobs,
            "failed_jobs": failed_jobs,
            "partial_jobs": partial_jobs,
            "running_jobs": len(self._running_jobs),
            "total_documents_processed": total_documents,
            "total_documents_failed": total_failures,
            "scheduler_running": self._scheduler_running,
            "log_entries": len(self._logs),
        }
