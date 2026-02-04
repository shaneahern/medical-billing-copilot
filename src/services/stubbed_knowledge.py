"""Stubbed Knowledge Service implementation for Medical Billing Copilot.

This module provides a stubbed implementation of the KnowledgeService
interface using static JSON data files for MVP testing.
"""

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Optional

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


class StubbedKnowledgeService(KnowledgeService):
    """Stubbed implementation of KnowledgeService using JSON files.
    
    This implementation loads policy data from JSON stub files and
    provides all KnowledgeService methods for MVP testing.
    
    Requirements: 6.2, 6.4, 9.6
    """

    def __init__(self, data_path: str = "data/stub"):
        """Initialize the stubbed knowledge service.
        
        Args:
            data_path: Path to the directory containing stub JSON files.
        """
        self.data_path = Path(data_path)
        self._coverage_data: list[dict] = []
        self._lcd_data: list[dict] = []
        self._ncd_data: list[dict] = []
        self._carc_data: list[dict] = []
        self._prior_auth_data: list[dict] = []
        self._mac_regions: list[dict] = []
        self._payers: list[dict] = []
        self._last_updated: datetime = datetime.now(UTC)
        self._load_data()

    def _load_data(self) -> None:
        """Load all JSON stub files."""
        # Load coverage data
        coverage_file = self.data_path / "coverage.json"
        if coverage_file.exists():
            with open(coverage_file) as f:
                data = json.load(f)
                self._coverage_data = data.get("coverage", [])
                self._payers = data.get("payers", [])
                if "metadata" in data:
                    self._last_updated = datetime.fromisoformat(
                        data["metadata"]["last_updated"].replace("Z", "+00:00")
                    )

        # Load LCD data
        lcd_file = self.data_path / "lcds.json"
        if lcd_file.exists():
            with open(lcd_file) as f:
                data = json.load(f)
                self._lcd_data = data.get("lcds", [])

        # Load NCD data
        ncd_file = self.data_path / "ncds.json"
        if ncd_file.exists():
            with open(ncd_file) as f:
                data = json.load(f)
                self._ncd_data = data.get("ncds", [])

        # Load CARC codes
        carc_file = self.data_path / "carc_codes.json"
        if carc_file.exists():
            with open(carc_file) as f:
                data = json.load(f)
                self._carc_data = data.get("carc_codes", [])

        # Load prior auth data
        prior_auth_file = self.data_path / "prior_auth.json"
        if prior_auth_file.exists():
            with open(prior_auth_file) as f:
                data = json.load(f)
                self._prior_auth_data = data.get("prior_auth", [])

        # Load MAC regions
        mac_file = self.data_path / "mac_regions.json"
        if mac_file.exists():
            with open(mac_file) as f:
                data = json.load(f)
                self._mac_regions = data.get("mac_regions", [])

    async def lookup_coverage(
        self, params: CoverageLookupParams
    ) -> CoverageResult:
        """Look up coverage information for a CPT/ICD combination."""
        payer = params.payer or "Medicare"
        
        # Find matching coverage record
        matching_coverage = None
        for record in self._coverage_data:
            if (
                record["cpt_code"] == params.cpt_code
                and record["payer"].lower() == payer.lower()
            ):
                matching_coverage = record
                break

        if not matching_coverage:
            # Return not covered result with alternative suggestions
            return CoverageResult(
                cpt_code=params.cpt_code,
                cpt_description="Unknown procedure code",
                is_covered=False,
                payer=payer,
                conditions=[],
                restrictions=["CPT code not found in coverage database"],
                alternative_codes=self._get_alternative_codes(params.cpt_code),
                sources=[
                    Citation(
                        source_type="STUBBED",
                        document_id="STUB-001",
                        document_title="Stubbed Coverage Database",
                        effective_date=self._last_updated,
                    )
                ],
                confidence=0.0,
            )

        # Check ICD code coverage if provided
        is_covered = True
        conditions: list[CoverageCondition] = []
        restrictions: list[str] = []

        if params.icd_codes:
            icd_mappings = matching_coverage.get("icd_mappings", [])
            for icd_code in params.icd_codes:
                icd_match = next(
                    (m for m in icd_mappings if m["icd_code"] == icd_code),
                    None,
                )
                if icd_match:
                    if not icd_match.get("is_covered", True):
                        is_covered = False
                    for condition in icd_match.get("conditions", []):
                        conditions.append(
                            CoverageCondition(
                                type=ConditionType.DOCUMENTATION,
                                description=condition,
                            )
                        )
                else:
                    restrictions.append(
                        f"ICD code {icd_code} not found in coverage mappings"
                    )

        return CoverageResult(
            cpt_code=params.cpt_code,
            cpt_description=matching_coverage.get("description", ""),
            is_covered=is_covered,
            payer=payer,
            conditions=conditions,
            restrictions=restrictions,
            alternative_codes=None if is_covered else self._get_alternative_codes(params.cpt_code),
            sources=[
                Citation(
                    source_type="LCD" if params.mac_region else "NCD",
                    document_id=f"STUB-COV-{params.cpt_code}",
                    document_title=f"Coverage Policy for {params.cpt_code}",
                    effective_date=self._last_updated,
                )
            ],
            confidence=0.95 if is_covered else 0.5,
        )

    def _get_alternative_codes(self, cpt_code: str) -> list[AlternativeCode]:
        """Get alternative CPT codes for a non-covered code."""
        # Simple logic to suggest related E/M codes
        em_codes = ["99211", "99212", "99213", "99214", "99215"]
        if cpt_code in em_codes:
            alternatives = []
            for code in em_codes:
                if code != cpt_code:
                    alternatives.append(
                        AlternativeCode(
                            cpt_code=code,
                            description=f"E/M visit level {code[-1]}",
                            reason="Consider different complexity level",
                        )
                    )
            return alternatives[:2]  # Return top 2 alternatives
        return []

    async def query_lcd(self, params: LCDQueryParams) -> LCDResult:
        """Query Local Coverage Determination by MAC region."""
        # Find matching LCD
        matching_lcd = None
        for lcd in self._lcd_data:
            if lcd["mac_region"].upper() == params.mac_region.upper():
                if params.lcd_id and lcd["lcd_id"] != params.lcd_id:
                    continue
                if params.cpt_code and params.cpt_code not in lcd.get(
                    "covered_cpt_codes", []
                ):
                    continue
                matching_lcd = lcd
                break

        if not matching_lcd:
            raise LookupError(
                f"No LCD found for MAC region {params.mac_region}"
                + (f" and CPT code {params.cpt_code}" if params.cpt_code else "")
            )

        # Parse revision history
        revision_history = [
            LCDRevision(
                version=rev["version"],
                effective_date=datetime.fromisoformat(
                    rev["effective_date"].replace("Z", "+00:00")
                ),
                summary=rev["summary"],
            )
            for rev in matching_lcd.get("revision_history", [])
        ]

        return LCDResult(
            lcd_id=matching_lcd["lcd_id"],
            title=matching_lcd["title"],
            mac_region=matching_lcd["mac_region"],
            mac_name=matching_lcd["mac_name"],
            effective_date=datetime.fromisoformat(
                matching_lcd["effective_date"].replace("Z", "+00:00")
            ),
            revision_history=revision_history,
            covered_cpt_codes=matching_lcd.get("covered_cpt_codes", []),
            covered_icd_codes=matching_lcd.get("covered_icd_codes", []),
            limitations=matching_lcd.get("limitations", []),
            documentation_requirements=matching_lcd.get(
                "documentation_requirements", []
            ),
            source_url=matching_lcd.get("source_url", ""),
        )

    async def explain_denial_code(
        self, code: str, context: Optional[DenialContext] = None
    ) -> DenialExplanation:
        """Explain a CARC denial code with recommended actions."""
        # Find matching CARC code
        matching_carc = next(
            (c for c in self._carc_data if c["code"] == code),
            None,
        )

        if not matching_carc:
            raise LookupError(f"CARC code {code} not found in database")

        # Parse category
        category_map = {
            "ELIGIBILITY": DenialCategory.ELIGIBILITY,
            "AUTHORIZATION": DenialCategory.AUTHORIZATION,
            "CODING": DenialCategory.CODING,
            "DOCUMENTATION": DenialCategory.DOCUMENTATION,
            "OTHER": DenialCategory.OTHER,
        }
        category = category_map.get(
            matching_carc.get("category", "OTHER"),
            DenialCategory.OTHER,
        )

        # Parse recommended actions
        recommended_actions = [
            RecommendedAction(
                priority=action["priority"],
                action=action["action"],
                details=action.get("details"),
            )
            for action in matching_carc.get("recommended_actions", [])
        ]

        return DenialExplanation(
            carc_code=code,
            category=category,
            short_description=matching_carc.get("short_description", ""),
            detailed_explanation=matching_carc.get("detailed_explanation", ""),
            common_causes=matching_carc.get("common_causes", []),
            recommended_actions=recommended_actions,
            related_codes=matching_carc.get("related_codes"),
        )

    async def lookup_prior_auth(
        self, params: PriorAuthParams
    ) -> PriorAuthResult:
        """Look up prior authorization requirements."""
        # Find matching prior auth record
        matching_auth = next(
            (
                pa
                for pa in self._prior_auth_data
                if pa["cpt_code"] == params.cpt_code
                and pa["payer"].lower() == params.payer.lower()
            ),
            None,
        )

        if not matching_auth:
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
                sources=[
                    Citation(
                        source_type="STUBBED",
                        document_id="STUB-PA-UNKNOWN",
                        document_title="Prior Auth Database - Payer Not Found",
                        effective_date=self._last_updated,
                    )
                ],
            )

        # Parse plan variations
        plan_variations = None
        if matching_auth.get("plan_variations"):
            plan_variations = [
                PlanVariation(
                    plan_type=pv["plan_type"],
                    is_required=pv["is_required"],
                    notes=pv.get("notes"),
                )
                for pv in matching_auth["plan_variations"]
            ]

        return PriorAuthResult(
            cpt_code=params.cpt_code,
            payer=params.payer,
            is_required=matching_auth.get("is_required", False),
            plan_variations=plan_variations,
            submission_requirements=matching_auth.get("submission_requirements"),
            typical_turnaround=matching_auth.get("typical_turnaround"),
            urgent_exceptions=matching_auth.get("urgent_exceptions"),
            contact_info=matching_auth.get("contact_info"),
            sources=[
                Citation(
                    source_type="COMMERCIAL" if params.payer != "Medicare" else "NCD",
                    document_id=f"STUB-PA-{params.cpt_code}-{params.payer}",
                    document_title=f"Prior Auth Policy - {params.payer}",
                    effective_date=self._last_updated,
                )
            ],
        )

    def get_data_source_info(self) -> DataSourceInfo:
        """Get information about the knowledge service data source."""
        coverage_areas = []
        
        # Add payer coverage
        for payer in self._payers:
            coverage_areas.append(f"Payer: {payer['name']}")
        
        # Add MAC region coverage
        for mac in self._mac_regions:
            coverage_areas.append(f"MAC Region: {mac['mac_name']}")

        return DataSourceInfo(
            type=DataSource.STUBBED,
            last_updated=self._last_updated,
            coverage=coverage_areas,
        )
