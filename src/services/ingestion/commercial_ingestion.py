"""Commercial payer policy ingestion service for Medical Billing Copilot.

This module provides functions to ingest commercial payer policies
for the top 10 national payers and verify policy freshness.

Requirements: 14.2, 14.3
"""

import asyncio
import logging
from datetime import UTC, datetime, timedelta
from typing import Any, Optional

from src.schemas.ingestion import (
    DocumentType,
    IngestedDocument,
    IngestionSource,
)
from src.services.ingestion.commercial_scraper import CommercialPayerScraper
from src.services.policy_database import PolicyDatabase

logger = logging.getLogger(__name__)


class CommercialIngestionService:
    """Service for ingesting commercial payer policies.

    This service handles:
    - Ingesting policies for top 10 national payers
    - Verifying policy freshness within 7 days
    - Tracking ingestion status per payer

    Requirements: 14.2, 14.3
    """

    # Top 10 national payers by market share (per Requirement 14.2)
    TOP_10_PAYERS = [
        {
            "id": "unitedhealthcare",
            "name": "UnitedHealthcare",
            "market_share": "14.9%",
        },
        {
            "id": "anthem",
            "name": "Anthem (Elevance Health)",
            "market_share": "12.5%",
        },
        {
            "id": "aetna",
            "name": "Aetna (CVS Health)",
            "market_share": "8.2%",
        },
        {
            "id": "cigna",
            "name": "Cigna",
            "market_share": "7.8%",
        },
        {
            "id": "humana",
            "name": "Humana",
            "market_share": "6.1%",
        },
        {
            "id": "kaiser",
            "name": "Kaiser Permanente",
            "market_share": "5.4%",
        },
        {
            "id": "bcbs",
            "name": "Blue Cross Blue Shield Association",
            "market_share": "4.8%",
        },
        {
            "id": "centene",
            "name": "Centene",
            "market_share": "4.2%",
        },
        {
            "id": "molina",
            "name": "Molina Healthcare",
            "market_share": "2.9%",
        },
        {
            "id": "wellcare",
            "name": "WellCare (Centene)",
            "market_share": "2.1%",
        },
    ]

    # Freshness threshold in days (per Requirement 14.3)
    FRESHNESS_THRESHOLD_DAYS = 7

    def __init__(
        self,
        commercial_scraper: Optional[CommercialPayerScraper] = None,
        policy_database: Optional[PolicyDatabase] = None,
        on_document_ingested: Optional[callable] = None,
        freshness_threshold_days: int = 7,
    ):
        """Initialize the commercial ingestion service.

        Args:
            commercial_scraper: Commercial payer scraper instance.
            policy_database: Policy database instance for tracking.
            on_document_ingested: Callback for each ingested document.
            freshness_threshold_days: Days before data is considered stale.
        """
        self.commercial_scraper = commercial_scraper or CommercialPayerScraper()
        self.policy_database = policy_database or PolicyDatabase()
        self.on_document_ingested = on_document_ingested
        self.freshness_threshold_days = freshness_threshold_days

        # Ingestion tracking
        self._ingestion_results: dict[str, Any] = {}
        self._last_ingestion: Optional[datetime] = None
        self._payer_ingestion_times: dict[str, datetime] = {}

    async def close(self) -> None:
        """Clean up resources."""
        await self.commercial_scraper.close()

    async def ingest_payer_policies(
        self,
        payer_id: str,
        limit: int = 100,
    ) -> dict[str, Any]:
        """Ingest policies for a specific payer.

        Args:
            payer_id: The payer identifier.
            limit: Maximum number of policies to ingest.

        Returns:
            Dictionary with ingestion results.
        """
        logger.info(f"Starting policy ingestion for payer: {payer_id}")

        result = {
            "payer_id": payer_id,
            "payer_name": self._get_payer_name(payer_id),
            "documents_ingested": 0,
            "failures": 0,
            "documents": [],
            "errors": [],
            "started_at": datetime.now(UTC).isoformat(),
            "completed_at": None,
        }

        try:
            documents = await self.commercial_scraper.scrape_payer_policies(
                payer_id, limit=limit
            )

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
                    logger.error(
                        f"Failed to process {payer_id} policy {doc.metadata.document_id}: {e}"
                    )

        except Exception as e:
            result["errors"].append({
                "payer_id": payer_id,
                "error": str(e),
            })
            logger.error(f"Failed to scrape policies for {payer_id}: {e}")

        result["completed_at"] = datetime.now(UTC).isoformat()
        self._payer_ingestion_times[payer_id] = datetime.now(UTC)
        self._ingestion_results[payer_id] = result

        logger.info(
            f"Policy ingestion for {payer_id} completed: "
            f"{result['documents_ingested']} documents, {result['failures']} failures"
        )

        return result

    async def ingest_top_10_payers(
        self,
        limit_per_payer: int = 100,
    ) -> dict[str, Any]:
        """Ingest policies for all top 10 national payers.

        Requirements: 14.2

        Args:
            limit_per_payer: Maximum policies per payer.

        Returns:
            Dictionary with combined ingestion results.
        """
        logger.info("Starting ingestion for top 10 national payers")

        results = {
            "payers": {},
            "total_documents": 0,
            "total_failures": 0,
            "payers_processed": 0,
            "payers_failed": 0,
            "started_at": datetime.now(UTC).isoformat(),
            "completed_at": None,
        }

        for payer in self.TOP_10_PAYERS:
            payer_id = payer["id"]
            logger.info(f"Processing payer: {payer['name']} ({payer_id})")

            try:
                payer_result = await self.ingest_payer_policies(
                    payer_id, limit=limit_per_payer
                )
                results["payers"][payer_id] = payer_result
                results["total_documents"] += payer_result["documents_ingested"]
                results["total_failures"] += payer_result["failures"]
                results["payers_processed"] += 1

            except Exception as e:
                results["payers"][payer_id] = {
                    "payer_id": payer_id,
                    "payer_name": payer["name"],
                    "error": str(e),
                    "documents_ingested": 0,
                    "failures": 1,
                }
                results["payers_failed"] += 1
                logger.error(f"Failed to process payer {payer_id}: {e}")

        results["completed_at"] = datetime.now(UTC).isoformat()
        self._last_ingestion = datetime.now(UTC)

        # Record full ingestion
        self.policy_database.record_full_ingestion()

        logger.info(
            f"Top 10 payer ingestion completed: {results['total_documents']} documents, "
            f"{results['payers_processed']}/{len(self.TOP_10_PAYERS)} payers processed"
        )

        return results

    def verify_freshness(self) -> dict[str, Any]:
        """Verify policy freshness for all payers.

        Requirements: 14.3

        Returns:
            Dictionary with freshness verification results.
        """
        logger.info("Verifying policy freshness")

        results = {
            "threshold_days": self.freshness_threshold_days,
            "verification_timestamp": datetime.now(UTC).isoformat(),
            "payers": {},
            "summary": {
                "total_payers": len(self.TOP_10_PAYERS),
                "fresh_payers": 0,
                "stale_payers": 0,
                "never_ingested": 0,
            },
        }

        for payer in self.TOP_10_PAYERS:
            payer_id = payer["id"]
            freshness_info = self.policy_database.get_freshness_info(payer_id)

            payer_status = {
                "payer_id": payer_id,
                "payer_name": payer["name"],
                "last_updated": (
                    freshness_info.last_updated.isoformat()
                    if freshness_info.last_updated
                    else None
                ),
                "document_count": freshness_info.document_count,
                "is_fresh": freshness_info.is_fresh,
                "days_since_update": freshness_info.days_since_update,
            }

            results["payers"][payer_id] = payer_status

            if freshness_info.last_updated is None:
                results["summary"]["never_ingested"] += 1
            elif freshness_info.is_fresh:
                results["summary"]["fresh_payers"] += 1
            else:
                results["summary"]["stale_payers"] += 1

        # Overall freshness status
        results["overall_fresh"] = (
            results["summary"]["stale_payers"] == 0
            and results["summary"]["never_ingested"] == 0
        )

        logger.info(
            f"Freshness verification: {results['summary']['fresh_payers']} fresh, "
            f"{results['summary']['stale_payers']} stale, "
            f"{results['summary']['never_ingested']} never ingested"
        )

        return results

    def get_stale_payers(self) -> list[dict[str, Any]]:
        """Get list of payers with stale data.

        Requirements: 14.3

        Returns:
            List of payers needing refresh.
        """
        stale_payers = []

        for payer in self.TOP_10_PAYERS:
            payer_id = payer["id"]
            freshness_info = self.policy_database.get_freshness_info(payer_id)

            if not freshness_info.is_fresh:
                stale_payers.append({
                    "payer_id": payer_id,
                    "payer_name": payer["name"],
                    "last_updated": (
                        freshness_info.last_updated.isoformat()
                        if freshness_info.last_updated
                        else None
                    ),
                    "days_since_update": freshness_info.days_since_update,
                })

        return stale_payers

    async def refresh_stale_payers(
        self,
        limit_per_payer: int = 100,
    ) -> dict[str, Any]:
        """Refresh policies for payers with stale data.

        Requirements: 14.3

        Args:
            limit_per_payer: Maximum policies per payer.

        Returns:
            Dictionary with refresh results.
        """
        stale_payers = self.get_stale_payers()

        if not stale_payers:
            return {
                "message": "All payers have fresh data",
                "payers_refreshed": 0,
            }

        logger.info(f"Refreshing {len(stale_payers)} stale payers")

        results = {
            "payers_refreshed": 0,
            "payers": {},
            "started_at": datetime.now(UTC).isoformat(),
            "completed_at": None,
        }

        for payer in stale_payers:
            payer_id = payer["payer_id"]
            try:
                payer_result = await self.ingest_payer_policies(
                    payer_id, limit=limit_per_payer
                )
                results["payers"][payer_id] = payer_result
                results["payers_refreshed"] += 1
            except Exception as e:
                results["payers"][payer_id] = {"error": str(e)}
                logger.error(f"Failed to refresh {payer_id}: {e}")

        results["completed_at"] = datetime.now(UTC).isoformat()

        return results

    def get_ingestion_status(self) -> dict[str, Any]:
        """Get the current ingestion status.

        Returns:
            Dictionary with ingestion status.
        """
        stats = self.policy_database.get_statistics()

        payer_status = {}
        for payer in self.TOP_10_PAYERS:
            payer_id = payer["id"]
            support_status = self.policy_database.get_payer_support_status(payer_id)
            payer_status[payer_id] = {
                "name": payer["name"],
                "document_count": support_status.document_count,
                "last_updated": (
                    support_status.last_updated.isoformat()
                    if support_status.last_updated
                    else None
                ),
                "is_supported": support_status.is_supported,
            }

        return {
            "last_ingestion": (
                self._last_ingestion.isoformat() if self._last_ingestion else None
            ),
            "total_commercial_policies": stats.commercial_policy_count,
            "payers_supported": stats.payers_supported,
            "overall_freshness": stats.overall_freshness,
            "payer_status": payer_status,
            "ingestion_results": self._ingestion_results,
        }

    def _get_payer_name(self, payer_id: str) -> str:
        """Get payer name from ID."""
        for payer in self.TOP_10_PAYERS:
            if payer["id"] == payer_id:
                return payer["name"]
        return payer_id

    def get_top_10_payers(self) -> list[dict[str, Any]]:
        """Get list of top 10 national payers.

        Returns:
            List of payer information.
        """
        return self.TOP_10_PAYERS.copy()


async def run_commercial_ingestion(
    policy_database: Optional[PolicyDatabase] = None,
    on_document_ingested: Optional[callable] = None,
    limit_per_payer: int = 100,
) -> dict[str, Any]:
    """Run full commercial payer ingestion.

    This is a convenience function to run the full commercial payer
    ingestion process for all top 10 national payers.

    Requirements: 14.2, 14.3

    Args:
        policy_database: Policy database instance for tracking.
        on_document_ingested: Callback for each ingested document.
        limit_per_payer: Maximum policies per payer.

    Returns:
        Dictionary with ingestion results.
    """
    service = CommercialIngestionService(
        policy_database=policy_database,
        on_document_ingested=on_document_ingested,
    )

    try:
        results = await service.ingest_top_10_payers(limit_per_payer=limit_per_payer)
        freshness = service.verify_freshness()
        results["freshness_verification"] = freshness
        return results
    finally:
        await service.close()
