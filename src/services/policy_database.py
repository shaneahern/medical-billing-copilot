"""Policy Database service for Medical Billing Copilot.

This module provides a service for managing the payer policy database,
including ingestion tracking, freshness monitoring, and payer support status.

Requirements: 14.1, 14.2, 14.3, 14.4, 14.5
"""

import json
import logging
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, Optional

from pydantic import BaseModel, Field

from src.schemas.ingestion import (
    DocumentMetadata,
    DocumentType,
    IngestedDocument,
    IngestionSource,
)

logger = logging.getLogger(__name__)


class PolicyFreshnessInfo(BaseModel):
    """Information about policy data freshness."""

    source: str = Field(..., description="Policy source (e.g., 'Medicare', 'Aetna')")
    source_type: str = Field(..., description="Type: 'medicare' or 'commercial'")
    last_updated: Optional[datetime] = Field(None, description="Last update timestamp")
    document_count: int = Field(0, description="Number of documents ingested")
    is_fresh: bool = Field(True, description="Whether data is within freshness threshold")
    freshness_threshold_days: int = Field(7, description="Days before data is stale")
    days_since_update: Optional[int] = Field(None, description="Days since last update")


class PayerSupportStatus(BaseModel):
    """Status of payer support in the database."""

    payer_id: str = Field(..., description="Payer identifier")
    payer_name: str = Field(..., description="Payer display name")
    is_supported: bool = Field(..., description="Whether payer is supported")
    document_count: int = Field(0, description="Number of policy documents")
    last_updated: Optional[datetime] = Field(None, description="Last update timestamp")
    coverage_areas: list[str] = Field(default_factory=list, description="Coverage areas")


class PolicyDatabaseStats(BaseModel):
    """Statistics about the policy database."""

    total_documents: int = Field(0, description="Total documents in database")
    medicare_lcd_count: int = Field(0, description="Number of Medicare LCDs")
    medicare_ncd_count: int = Field(0, description="Number of Medicare NCDs")
    commercial_policy_count: int = Field(0, description="Number of commercial policies")
    mac_regions_covered: list[str] = Field(default_factory=list, description="MAC regions")
    payers_supported: list[str] = Field(default_factory=list, description="Supported payers")
    last_full_ingestion: Optional[datetime] = Field(None, description="Last full ingestion")
    overall_freshness: bool = Field(True, description="Overall data freshness status")


class PolicyDatabase:
    """Service for managing the payer policy database.

    This class handles:
    - Tracking ingested policy documents
    - Monitoring data freshness
    - Managing payer support status
    - Providing policy metadata for responses

    Requirements: 14.1, 14.2, 14.3, 14.4, 14.5
    """

    # Top 10 national commercial payers by market share
    TOP_COMMERCIAL_PAYERS = [
        {"id": "unitedhealthcare", "name": "UnitedHealthcare"},
        {"id": "anthem", "name": "Anthem (Elevance Health)"},
        {"id": "aetna", "name": "Aetna (CVS Health)"},
        {"id": "cigna", "name": "Cigna"},
        {"id": "humana", "name": "Humana"},
        {"id": "kaiser", "name": "Kaiser Permanente"},
        {"id": "bcbs", "name": "Blue Cross Blue Shield"},
        {"id": "centene", "name": "Centene"},
        {"id": "molina", "name": "Molina Healthcare"},
        {"id": "wellcare", "name": "WellCare (Centene)"},
    ]

    # All MAC regions for Medicare
    ALL_MAC_REGIONS = [
        {"id": "NOVITAS", "name": "Novitas Solutions", "jurisdictions": ["JH", "JL"]},
        {"id": "PALMETTO", "name": "Palmetto GBA", "jurisdictions": ["JM", "J11"]},
        {"id": "CGS", "name": "CGS Administrators", "jurisdictions": ["J15"]},
        {"id": "WPS", "name": "WPS Government Health Administrators", "jurisdictions": ["J5", "J8"]},
        {"id": "NGS", "name": "National Government Services", "jurisdictions": ["J6", "JK"]},
        {"id": "FIRST_COAST", "name": "First Coast Service Options", "jurisdictions": ["J9", "JN"]},
        {"id": "NORIDIAN", "name": "Noridian Healthcare Solutions", "jurisdictions": ["JA", "JB", "JE", "JF"]},
    ]

    # Freshness threshold in days (per Requirement 14.3)
    FRESHNESS_THRESHOLD_DAYS = 7

    def __init__(
        self,
        persist_path: Optional[str] = None,
        freshness_threshold_days: int = 7,
    ):
        """Initialize the policy database service.

        Args:
            persist_path: Path to persist database state. If None, uses in-memory only.
            freshness_threshold_days: Days before data is considered stale.
        """
        self.persist_path = Path(persist_path) if persist_path else None
        self.freshness_threshold_days = freshness_threshold_days

        # In-memory tracking
        self._documents: dict[str, DocumentMetadata] = {}
        self._ingestion_timestamps: dict[str, datetime] = {}
        self._payer_document_counts: dict[str, int] = {}
        self._mac_region_document_counts: dict[str, int] = {}
        self._last_full_ingestion: Optional[datetime] = None

        # Load persisted state if available
        if self.persist_path and self.persist_path.exists():
            self._load_state()

    def _load_state(self) -> None:
        """Load persisted state from disk."""
        try:
            with open(self.persist_path, "r") as f:
                state = json.load(f)

            self._ingestion_timestamps = {
                k: datetime.fromisoformat(v)
                for k, v in state.get("ingestion_timestamps", {}).items()
            }
            self._payer_document_counts = state.get("payer_document_counts", {})
            self._mac_region_document_counts = state.get("mac_region_document_counts", {})

            if state.get("last_full_ingestion"):
                self._last_full_ingestion = datetime.fromisoformat(
                    state["last_full_ingestion"]
                )

            logger.info(f"Loaded policy database state from {self.persist_path}")
        except Exception as e:
            logger.warning(f"Failed to load policy database state: {e}")

    def _save_state(self) -> None:
        """Save state to disk."""
        if not self.persist_path:
            return

        try:
            self.persist_path.parent.mkdir(parents=True, exist_ok=True)

            state = {
                "ingestion_timestamps": {
                    k: v.isoformat() for k, v in self._ingestion_timestamps.items()
                },
                "payer_document_counts": self._payer_document_counts,
                "mac_region_document_counts": self._mac_region_document_counts,
                "last_full_ingestion": (
                    self._last_full_ingestion.isoformat()
                    if self._last_full_ingestion
                    else None
                ),
            }

            with open(self.persist_path, "w") as f:
                json.dump(state, f, indent=2)

            logger.info(f"Saved policy database state to {self.persist_path}")
        except Exception as e:
            logger.error(f"Failed to save policy database state: {e}")

    # ==================== Document Tracking ====================

    def record_document_ingestion(self, document: IngestedDocument) -> None:
        """Record that a document has been ingested.

        Args:
            document: The ingested document.
        """
        doc_id = document.metadata.document_id
        self._documents[doc_id] = document.metadata

        # Update timestamps
        source_key = self._get_source_key(document.metadata)
        self._ingestion_timestamps[source_key] = datetime.now(UTC)

        # Update counts
        if document.metadata.document_type == DocumentType.LCD:
            mac_region = document.metadata.mac_region or "UNKNOWN"
            self._mac_region_document_counts[mac_region] = (
                self._mac_region_document_counts.get(mac_region, 0) + 1
            )
        elif document.metadata.document_type == DocumentType.NCD:
            self._mac_region_document_counts["NCD"] = (
                self._mac_region_document_counts.get("NCD", 0) + 1
            )
        elif document.metadata.document_type == DocumentType.COMMERCIAL:
            payer = document.metadata.payer or "UNKNOWN"
            payer_key = payer.lower().replace(" ", "_")
            self._payer_document_counts[payer_key] = (
                self._payer_document_counts.get(payer_key, 0) + 1
            )

        self._save_state()

    def record_batch_ingestion(
        self,
        documents: list[IngestedDocument],
        source: IngestionSource,
    ) -> None:
        """Record a batch of ingested documents.

        Args:
            documents: List of ingested documents.
            source: The ingestion source.
        """
        for doc in documents:
            self.record_document_ingestion(doc)

        if source == IngestionSource.CMS_GOV:
            self._ingestion_timestamps["medicare"] = datetime.now(UTC)
        elif source == IngestionSource.COMMERCIAL_PAYER:
            self._ingestion_timestamps["commercial"] = datetime.now(UTC)

        self._save_state()

    def record_full_ingestion(self) -> None:
        """Record that a full ingestion has completed."""
        self._last_full_ingestion = datetime.now(UTC)
        self._save_state()

    def _get_source_key(self, metadata: DocumentMetadata) -> str:
        """Get a source key for tracking timestamps."""
        if metadata.document_type in (DocumentType.LCD, DocumentType.NCD):
            return f"medicare_{metadata.document_type.value.lower()}"
        elif metadata.document_type == DocumentType.COMMERCIAL:
            payer = metadata.payer or "unknown"
            return f"commercial_{payer.lower().replace(' ', '_')}"
        return "unknown"

    # ==================== Freshness Tracking ====================

    def get_freshness_info(self, source: str) -> PolicyFreshnessInfo:
        """Get freshness information for a policy source.

        Requirements: 14.3, 14.4

        Args:
            source: The policy source (e.g., 'medicare', 'aetna').

        Returns:
            PolicyFreshnessInfo with freshness status.
        """
        source_lower = source.lower().replace(" ", "_")

        # Determine source type
        if source_lower in ("medicare", "medicare_lcd", "medicare_ncd"):
            source_type = "medicare"
            last_updated = self._ingestion_timestamps.get(source_lower)
            doc_count = sum(
                count
                for key, count in self._mac_region_document_counts.items()
            )
        else:
            source_type = "commercial"
            last_updated = self._ingestion_timestamps.get(f"commercial_{source_lower}")
            doc_count = self._payer_document_counts.get(source_lower, 0)

        # Calculate freshness
        is_fresh = True
        days_since_update = None

        if last_updated:
            days_since_update = (datetime.now(UTC) - last_updated).days
            is_fresh = days_since_update <= self.freshness_threshold_days

        return PolicyFreshnessInfo(
            source=source,
            source_type=source_type,
            last_updated=last_updated,
            document_count=doc_count,
            is_fresh=is_fresh,
            freshness_threshold_days=self.freshness_threshold_days,
            days_since_update=days_since_update,
        )

    def get_last_updated_date(self, source: str) -> Optional[datetime]:
        """Get the last updated date for a policy source.

        Requirements: 14.4

        Args:
            source: The policy source.

        Returns:
            Last updated datetime or None if never updated.
        """
        info = self.get_freshness_info(source)
        return info.last_updated

    def is_data_fresh(self, source: str) -> bool:
        """Check if data for a source is fresh (within threshold).

        Requirements: 14.3

        Args:
            source: The policy source.

        Returns:
            True if data is fresh, False otherwise.
        """
        info = self.get_freshness_info(source)
        return info.is_fresh

    # ==================== Payer Support ====================

    def get_payer_support_status(self, payer_id: str) -> PayerSupportStatus:
        """Get support status for a specific payer.

        Requirements: 14.5

        Args:
            payer_id: The payer identifier.

        Returns:
            PayerSupportStatus with support information.
        """
        payer_key = payer_id.lower().replace(" ", "_")

        # Check if it's a known payer
        known_payer = None
        for payer in self.TOP_COMMERCIAL_PAYERS:
            if payer["id"] == payer_key:
                known_payer = payer
                break

        # Check if we have documents for this payer
        doc_count = self._payer_document_counts.get(payer_key, 0)
        last_updated = self._ingestion_timestamps.get(f"commercial_{payer_key}")

        is_supported = doc_count > 0 or known_payer is not None

        return PayerSupportStatus(
            payer_id=payer_key,
            payer_name=known_payer["name"] if known_payer else payer_id,
            is_supported=is_supported,
            document_count=doc_count,
            last_updated=last_updated,
            coverage_areas=["Medical policies", "Prior authorization"] if is_supported else [],
        )

    def is_payer_supported(self, payer_id: str) -> bool:
        """Check if a payer is supported.

        Requirements: 14.5

        Args:
            payer_id: The payer identifier.

        Returns:
            True if payer is supported, False otherwise.
        """
        status = self.get_payer_support_status(payer_id)
        return status.is_supported

    def get_unsupported_payer_message(self, payer_id: str) -> str:
        """Get a message for unsupported payers.

        Requirements: 14.5

        Args:
            payer_id: The payer identifier.

        Returns:
            Message indicating payer is not supported.
        """
        return (
            f"The payer '{payer_id}' is not currently supported in our policy database. "
            f"Please contact the payer directly for coverage information. "
            f"Supported payers include: {', '.join(p['name'] for p in self.TOP_COMMERCIAL_PAYERS[:5])}."
        )

    def get_supported_payers(self) -> list[PayerSupportStatus]:
        """Get list of all supported payers.

        Returns:
            List of PayerSupportStatus for all supported payers.
        """
        payers = []

        # Add Medicare
        medicare_count = sum(self._mac_region_document_counts.values())
        payers.append(
            PayerSupportStatus(
                payer_id="medicare",
                payer_name="Medicare",
                is_supported=True,
                document_count=medicare_count,
                last_updated=self._ingestion_timestamps.get("medicare"),
                coverage_areas=["LCDs", "NCDs", "Coverage policies"],
            )
        )

        # Add commercial payers
        for payer in self.TOP_COMMERCIAL_PAYERS:
            status = self.get_payer_support_status(payer["id"])
            payers.append(status)

        return payers

    # ==================== Statistics ====================

    def get_statistics(self) -> PolicyDatabaseStats:
        """Get overall statistics about the policy database.

        Returns:
            PolicyDatabaseStats with database statistics.
        """
        lcd_count = sum(
            count
            for key, count in self._mac_region_document_counts.items()
            if key != "NCD"
        )
        ncd_count = self._mac_region_document_counts.get("NCD", 0)
        commercial_count = sum(self._payer_document_counts.values())

        mac_regions = [
            key for key in self._mac_region_document_counts.keys() if key != "NCD"
        ]

        payers_with_docs = [
            payer["name"]
            for payer in self.TOP_COMMERCIAL_PAYERS
            if self._payer_document_counts.get(payer["id"], 0) > 0
        ]

        # Check overall freshness
        overall_fresh = True
        for source in ["medicare", "commercial"]:
            if source in self._ingestion_timestamps:
                days = (datetime.now(UTC) - self._ingestion_timestamps[source]).days
                if days > self.freshness_threshold_days:
                    overall_fresh = False
                    break

        return PolicyDatabaseStats(
            total_documents=lcd_count + ncd_count + commercial_count,
            medicare_lcd_count=lcd_count,
            medicare_ncd_count=ncd_count,
            commercial_policy_count=commercial_count,
            mac_regions_covered=mac_regions,
            payers_supported=["Medicare"] + payers_with_docs,
            last_full_ingestion=self._last_full_ingestion,
            overall_freshness=overall_fresh,
        )

    # ==================== MAC Region Support ====================

    def get_mac_regions(self) -> list[dict[str, Any]]:
        """Get list of all MAC regions.

        Returns:
            List of MAC region information.
        """
        return self.ALL_MAC_REGIONS

    def get_mac_region_coverage(self, mac_region: str) -> dict[str, Any]:
        """Get coverage information for a MAC region.

        Args:
            mac_region: The MAC region identifier.

        Returns:
            Dictionary with MAC region coverage info.
        """
        mac_upper = mac_region.upper()
        doc_count = self._mac_region_document_counts.get(mac_upper, 0)

        # Find MAC info
        mac_info = None
        for mac in self.ALL_MAC_REGIONS:
            if mac["id"] == mac_upper:
                mac_info = mac
                break

        return {
            "mac_region": mac_upper,
            "mac_name": mac_info["name"] if mac_info else "Unknown",
            "document_count": doc_count,
            "is_covered": doc_count > 0,
            "jurisdictions": mac_info["jurisdictions"] if mac_info else [],
        }

    def verify_common_procedures_coverage(self) -> dict[str, Any]:
        """Verify coverage of common procedures in the database.

        Requirements: 14.1

        Returns:
            Dictionary with verification results.
        """
        # Common E/M procedure codes
        common_cpt_codes = ["99213", "99214", "99215", "99211", "99212"]

        # Check MAC region coverage
        mac_coverage = {}
        for mac in self.ALL_MAC_REGIONS:
            mac_coverage[mac["id"]] = {
                "name": mac["name"],
                "document_count": self._mac_region_document_counts.get(mac["id"], 0),
                "is_covered": self._mac_region_document_counts.get(mac["id"], 0) > 0,
            }

        # Check NCD coverage
        ncd_coverage = {
            "document_count": self._mac_region_document_counts.get("NCD", 0),
            "is_covered": self._mac_region_document_counts.get("NCD", 0) > 0,
        }

        return {
            "common_cpt_codes": common_cpt_codes,
            "mac_region_coverage": mac_coverage,
            "ncd_coverage": ncd_coverage,
            "total_mac_regions": len(self.ALL_MAC_REGIONS),
            "covered_mac_regions": sum(
                1 for mac in mac_coverage.values() if mac["is_covered"]
            ),
        }
