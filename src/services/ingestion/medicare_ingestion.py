"""Medicare LCD/NCD ingestion service for Medical Billing Copilot.

This module provides functions to ingest Medicare LCDs and NCDs
for all MAC regions and verify coverage of common procedures.

Requirements: 14.1
"""

import asyncio
import logging
from datetime import UTC, datetime
from typing import Any, Optional

from src.schemas.ingestion import (
    DocumentType,
    IngestedDocument,
    IngestionSource,
)
from src.services.ingestion.cms_scraper import CMSScraper
from src.services.policy_database import PolicyDatabase

logger = logging.getLogger(__name__)


class MedicareIngestionService:
    """Service for ingesting Medicare LCDs and NCDs.

    This service handles:
    - Ingesting LCDs for all MAC regions
    - Ingesting NCDs (national coverage)
    - Verifying coverage of common procedures
    - Tracking ingestion status

    Requirements: 14.1
    """

    # All MAC regions to ingest
    ALL_MAC_REGIONS = [
        "NOVITAS",
        "PALMETTO",
        "CGS",
        "WPS",
        "NGS",
        "FIRST_COAST",
        "NORIDIAN",
    ]

    # Common procedures to verify coverage
    COMMON_PROCEDURES = [
        {"cpt": "99213", "description": "Office visit, established patient, low complexity"},
        {"cpt": "99214", "description": "Office visit, established patient, moderate complexity"},
        {"cpt": "99215", "description": "Office visit, established patient, high complexity"},
        {"cpt": "99211", "description": "Office visit, established patient, minimal"},
        {"cpt": "99212", "description": "Office visit, established patient, straightforward"},
    ]

    def __init__(
        self,
        cms_scraper: Optional[CMSScraper] = None,
        policy_database: Optional[PolicyDatabase] = None,
        on_document_ingested: Optional[callable] = None,
    ):
        """Initialize the Medicare ingestion service.

        Args:
            cms_scraper: CMS scraper instance.
            policy_database: Policy database instance for tracking.
            on_document_ingested: Callback for each ingested document.
        """
        self.cms_scraper = cms_scraper or CMSScraper()
        self.policy_database = policy_database or PolicyDatabase()
        self.on_document_ingested = on_document_ingested

        # Ingestion tracking
        self._ingestion_results: dict[str, Any] = {}
        self._last_ingestion: Optional[datetime] = None

    async def close(self) -> None:
        """Clean up resources."""
        await self.cms_scraper.close()

    async def ingest_all_lcds(
        self,
        mac_regions: Optional[list[str]] = None,
    ) -> dict[str, Any]:
        """Ingest LCDs for all MAC regions.

        Requirements: 14.1

        Args:
            mac_regions: Specific MAC regions to ingest. If None, ingests all.

        Returns:
            Dictionary with ingestion results.
        """
        regions = mac_regions or self.ALL_MAC_REGIONS
        logger.info(f"Starting LCD ingestion for MAC regions: {regions}")

        results = {
            "mac_regions": {},
            "total_documents": 0,
            "total_failures": 0,
            "started_at": datetime.now(UTC).isoformat(),
            "completed_at": None,
        }

        for region in regions:
            logger.info(f"Ingesting LCDs for MAC region: {region}")
            region_result = await self._ingest_region_lcds(region)
            results["mac_regions"][region] = region_result
            results["total_documents"] += region_result["documents_ingested"]
            results["total_failures"] += region_result["failures"]

        results["completed_at"] = datetime.now(UTC).isoformat()
        self._ingestion_results["lcds"] = results
        self._last_ingestion = datetime.now(UTC)

        logger.info(
            f"LCD ingestion completed: {results['total_documents']} documents, "
            f"{results['total_failures']} failures"
        )

        return results

    async def _ingest_region_lcds(self, mac_region: str) -> dict[str, Any]:
        """Ingest LCDs for a specific MAC region.

        Args:
            mac_region: The MAC region to ingest.

        Returns:
            Dictionary with region ingestion results.
        """
        result = {
            "mac_region": mac_region,
            "documents_ingested": 0,
            "failures": 0,
            "documents": [],
            "errors": [],
        }

        try:
            documents = await self.cms_scraper.scrape_all_lcds([mac_region])

            for doc in documents:
                try:
                    # Record in policy database
                    self.policy_database.record_document_ingestion(doc)

                    # Call callback if set
                    if self.on_document_ingested:
                        self.on_document_ingested(doc)

                    result["documents_ingested"] += 1
                    result["documents"].append({
                        "document_id": doc.metadata.document_id,
                        "title": doc.metadata.title,
                    })

                except Exception as e:
                    result["failures"] += 1
                    result["errors"].append({
                        "document_id": doc.metadata.document_id,
                        "error": str(e),
                    })
                    logger.error(f"Failed to process LCD {doc.metadata.document_id}: {e}")

        except Exception as e:
            result["errors"].append({
                "mac_region": mac_region,
                "error": str(e),
            })
            logger.error(f"Failed to scrape LCDs for {mac_region}: {e}")

        return result

    async def ingest_all_ncds(self) -> dict[str, Any]:
        """Ingest all NCDs (National Coverage Determinations).

        Requirements: 14.1

        Returns:
            Dictionary with ingestion results.
        """
        logger.info("Starting NCD ingestion")

        results = {
            "documents_ingested": 0,
            "failures": 0,
            "documents": [],
            "errors": [],
            "started_at": datetime.now(UTC).isoformat(),
            "completed_at": None,
        }

        try:
            documents = await self.cms_scraper.scrape_all_ncds()

            for doc in documents:
                try:
                    # Record in policy database
                    self.policy_database.record_document_ingestion(doc)

                    # Call callback if set
                    if self.on_document_ingested:
                        self.on_document_ingested(doc)

                    results["documents_ingested"] += 1
                    results["documents"].append({
                        "document_id": doc.metadata.document_id,
                        "title": doc.metadata.title,
                    })

                except Exception as e:
                    results["failures"] += 1
                    results["errors"].append({
                        "document_id": doc.metadata.document_id,
                        "error": str(e),
                    })
                    logger.error(f"Failed to process NCD {doc.metadata.document_id}: {e}")

        except Exception as e:
            results["errors"].append({"error": str(e)})
            logger.error(f"Failed to scrape NCDs: {e}")

        results["completed_at"] = datetime.now(UTC).isoformat()
        self._ingestion_results["ncds"] = results
        self._last_ingestion = datetime.now(UTC)

        logger.info(
            f"NCD ingestion completed: {results['documents_ingested']} documents, "
            f"{results['failures']} failures"
        )

        return results

    async def ingest_all_medicare(self) -> dict[str, Any]:
        """Ingest all Medicare LCDs and NCDs.

        Requirements: 14.1

        Returns:
            Dictionary with combined ingestion results.
        """
        logger.info("Starting full Medicare ingestion")

        # Run LCD and NCD ingestion
        lcd_results = await self.ingest_all_lcds()
        ncd_results = await self.ingest_all_ncds()

        # Record full ingestion
        self.policy_database.record_full_ingestion()

        results = {
            "lcds": lcd_results,
            "ncds": ncd_results,
            "total_documents": lcd_results["total_documents"] + ncd_results["documents_ingested"],
            "total_failures": lcd_results["total_failures"] + ncd_results["failures"],
            "completed_at": datetime.now(UTC).isoformat(),
        }

        logger.info(
            f"Full Medicare ingestion completed: {results['total_documents']} documents"
        )

        return results

    def verify_coverage(self) -> dict[str, Any]:
        """Verify coverage of common procedures.

        Requirements: 14.1

        Returns:
            Dictionary with verification results.
        """
        logger.info("Verifying coverage of common procedures")

        # Get coverage verification from policy database
        coverage = self.policy_database.verify_common_procedures_coverage()

        # Add procedure-specific verification
        procedure_coverage = []
        for proc in self.COMMON_PROCEDURES:
            procedure_coverage.append({
                "cpt_code": proc["cpt"],
                "description": proc["description"],
                "expected_coverage": True,  # These are common E/M codes
            })

        coverage["procedures"] = procedure_coverage
        coverage["verification_timestamp"] = datetime.now(UTC).isoformat()

        # Summary
        mac_covered = coverage["covered_mac_regions"]
        mac_total = coverage["total_mac_regions"]
        coverage["summary"] = {
            "mac_regions_covered": f"{mac_covered}/{mac_total}",
            "ncd_coverage": "Yes" if coverage["ncd_coverage"]["is_covered"] else "No",
            "common_procedures_expected": len(self.COMMON_PROCEDURES),
        }

        logger.info(f"Coverage verification: {mac_covered}/{mac_total} MAC regions covered")

        return coverage

    def get_ingestion_status(self) -> dict[str, Any]:
        """Get the current ingestion status.

        Returns:
            Dictionary with ingestion status.
        """
        stats = self.policy_database.get_statistics()

        return {
            "last_ingestion": self._last_ingestion.isoformat() if self._last_ingestion else None,
            "lcd_count": stats.medicare_lcd_count,
            "ncd_count": stats.medicare_ncd_count,
            "mac_regions_covered": stats.mac_regions_covered,
            "overall_freshness": stats.overall_freshness,
            "ingestion_results": self._ingestion_results,
        }


async def run_medicare_ingestion(
    policy_database: Optional[PolicyDatabase] = None,
    on_document_ingested: Optional[callable] = None,
) -> dict[str, Any]:
    """Run full Medicare ingestion.

    This is a convenience function to run the full Medicare ingestion
    process including LCDs for all MAC regions and NCDs.

    Requirements: 14.1

    Args:
        policy_database: Policy database instance for tracking.
        on_document_ingested: Callback for each ingested document.

    Returns:
        Dictionary with ingestion results.
    """
    service = MedicareIngestionService(
        policy_database=policy_database,
        on_document_ingested=on_document_ingested,
    )

    try:
        results = await service.ingest_all_medicare()
        verification = service.verify_coverage()
        results["verification"] = verification
        return results
    finally:
        await service.close()
