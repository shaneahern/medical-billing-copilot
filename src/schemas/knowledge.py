"""Knowledge service schemas for Medical Billing Copilot."""

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field

from src.schemas.common import (
    Citation,
    ConditionType,
    DataSource,
    DenialCategory,
)


# Coverage-related schemas
class CoverageCondition(BaseModel):
    """Coverage condition requirement."""

    type: ConditionType = Field(..., description="Type of condition")
    description: str = Field(..., description="Condition description")
    required_icd_codes: Optional[list[str]] = Field(
        None, description="Required ICD codes for coverage"
    )
    frequency_limit: Optional[str] = Field(
        None, description="Frequency limitation description"
    )


class AlternativeCode(BaseModel):
    """Alternative CPT code suggestion."""

    cpt_code: str = Field(..., description="Alternative CPT code")
    description: str = Field(..., description="Code description")
    reason: str = Field(..., description="Reason for suggestion")


class CoverageResult(BaseModel):
    """Coverage lookup result."""

    cpt_code: str = Field(..., description="CPT code queried")
    cpt_description: str = Field(..., description="CPT code description")
    is_covered: bool = Field(..., description="Whether the code is covered")
    payer: str = Field(..., description="Payer name")
    conditions: list[CoverageCondition] = Field(
        default_factory=list, description="Coverage conditions"
    )
    restrictions: list[str] = Field(
        default_factory=list, description="Coverage restrictions"
    )
    alternative_codes: Optional[list[AlternativeCode]] = Field(
        None, description="Alternative codes if not covered"
    )
    sources: list[Citation] = Field(
        default_factory=list, description="Source citations"
    )
    confidence: float = Field(
        ..., ge=0.0, le=1.0, description="Confidence score"
    )


# LCD-related schemas
class LCDRevision(BaseModel):
    """LCD revision history entry."""

    version: str = Field(..., description="Revision version")
    effective_date: datetime = Field(..., description="Effective date of revision")
    summary: str = Field(..., description="Summary of changes")


class LCDResult(BaseModel):
    """LCD query result."""

    lcd_id: str = Field(..., description="LCD identifier")
    title: str = Field(..., description="LCD title")
    mac_region: str = Field(..., description="MAC region code")
    mac_name: str = Field(..., description="MAC name")
    effective_date: datetime = Field(..., description="Current effective date")
    revision_history: list[LCDRevision] = Field(
        default_factory=list, description="Revision history"
    )
    covered_cpt_codes: list[str] = Field(
        default_factory=list, description="Covered CPT codes"
    )
    covered_icd_codes: list[str] = Field(
        default_factory=list, description="Covered ICD codes"
    )
    limitations: list[str] = Field(
        default_factory=list, description="Coverage limitations"
    )
    documentation_requirements: list[str] = Field(
        default_factory=list, description="Documentation requirements"
    )
    source_url: str = Field(..., description="Source URL")



# Denial code schemas
class RecommendedAction(BaseModel):
    """Recommended action for denial resolution."""

    priority: int = Field(..., ge=1, description="Action priority (1 = highest)")
    action: str = Field(..., description="Action description")
    details: Optional[str] = Field(None, description="Additional details")


class DenialExplanation(BaseModel):
    """Denial code explanation."""

    carc_code: str = Field(..., description="CARC code")
    category: DenialCategory = Field(..., description="Denial category")
    short_description: str = Field(..., description="Short description")
    detailed_explanation: str = Field(..., description="Detailed explanation")
    common_causes: list[str] = Field(
        default_factory=list, description="Common causes"
    )
    recommended_actions: list[RecommendedAction] = Field(
        default_factory=list, description="Recommended actions"
    )
    related_codes: Optional[list[str]] = Field(
        None, description="Related CARC codes"
    )


# Prior authorization schemas
class PlanVariation(BaseModel):
    """Plan-specific prior auth variation."""

    plan_type: str = Field(..., description="Plan type")
    is_required: bool = Field(..., description="Whether auth is required")
    notes: Optional[str] = Field(None, description="Additional notes")


class PriorAuthResult(BaseModel):
    """Prior authorization lookup result."""

    cpt_code: str = Field(..., description="CPT code")
    payer: str = Field(..., description="Payer name")
    is_required: bool = Field(..., description="Whether prior auth is required")
    plan_variations: Optional[list[PlanVariation]] = Field(
        None, description="Plan-specific variations"
    )
    submission_requirements: Optional[list[str]] = Field(
        None, description="Submission requirements"
    )
    typical_turnaround: Optional[str] = Field(
        None, description="Typical turnaround time"
    )
    urgent_exceptions: Optional[list[str]] = Field(
        None, description="Urgent/emergent exceptions"
    )
    contact_info: Optional[str] = Field(None, description="Payer contact information")
    sources: list[Citation] = Field(
        default_factory=list, description="Source citations"
    )


# Data source info
class DataSourceInfo(BaseModel):
    """Knowledge service data source information."""

    type: DataSource = Field(..., description="Data source type")
    last_updated: datetime = Field(..., description="Last update timestamp")
    coverage: list[str] = Field(
        default_factory=list, description="Coverage areas"
    )


# Lookup parameter models
class CoverageLookupParams(BaseModel):
    """Parameters for coverage lookup."""

    cpt_code: str = Field(..., pattern=r"^[0-9]{5}$", description="CPT code (5 digits)")
    icd_codes: Optional[list[str]] = Field(None, description="ICD codes")
    payer: Optional[str] = Field(None, description="Payer name")
    mac_region: Optional[str] = Field(None, description="MAC region")


class LCDQueryParams(BaseModel):
    """Parameters for LCD query."""

    lcd_id: Optional[str] = Field(None, description="LCD identifier")
    cpt_code: Optional[str] = Field(
        None, pattern=r"^[0-9]{5}$", description="CPT code"
    )
    mac_region: str = Field(..., description="MAC region")


class PriorAuthParams(BaseModel):
    """Parameters for prior auth lookup."""

    cpt_code: str = Field(..., pattern=r"^[0-9]{5}$", description="CPT code")
    payer: str = Field(..., description="Payer name")
    plan_type: Optional[str] = Field(None, description="Plan type")


class DenialContext(BaseModel):
    """Context for denial code explanation."""

    payer: Optional[str] = Field(None, description="Payer name")
    cpt_code: Optional[str] = Field(None, description="Related CPT code")
    claim_type: Optional[str] = Field(None, description="Claim type")
