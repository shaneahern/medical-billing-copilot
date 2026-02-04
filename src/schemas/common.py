"""Common shared types and enums for Medical Billing Copilot."""

from datetime import datetime
from enum import Enum
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field


class UserRole(str, Enum):
    """User role enumeration."""

    USER = "user"
    ADMIN = "admin"


class QueryType(str, Enum):
    """Query type classification."""

    COVERAGE_LOOKUP = "COVERAGE_LOOKUP"
    LCD_QUERY = "LCD_QUERY"
    DENIAL_EXPLANATION = "DENIAL_EXPLANATION"
    PRIOR_AUTH = "PRIOR_AUTH"
    GENERAL = "GENERAL"


class DataSource(str, Enum):
    """Data source type indicator."""

    STUBBED = "STUBBED"
    RAG = "RAG"


class ConditionType(str, Enum):
    """Coverage condition type."""

    DIAGNOSIS = "DIAGNOSIS"
    FREQUENCY = "FREQUENCY"
    DOCUMENTATION = "DOCUMENTATION"
    OTHER = "OTHER"


class DenialCategory(str, Enum):
    """Denial code category."""

    ELIGIBILITY = "ELIGIBILITY"
    AUTHORIZATION = "AUTHORIZATION"
    CODING = "CODING"
    DOCUMENTATION = "DOCUMENTATION"
    OTHER = "OTHER"


class Citation(BaseModel):
    """Source citation for responses."""

    source_type: str = Field(
        ..., description="Type of source: LCD, NCD, COMMERCIAL, CARC"
    )
    document_id: str = Field(..., description="Unique identifier for the document")
    document_title: str = Field(..., description="Title of the source document")
    source_url: Optional[str] = Field(None, description="URL to the source document")
    effective_date: Optional[datetime] = Field(
        None, description="Effective date of the policy"
    )


class Message(BaseModel):
    """Conversation message."""

    model_config = ConfigDict(from_attributes=True)

    id: str = Field(..., description="Unique message identifier")
    role: str = Field(..., description="Message role: user or assistant")
    content: str = Field(..., max_length=100000, description="Message content")
    citations: Optional[list[Citation]] = Field(
        None, description="Source citations for the response"
    )
    timestamp: datetime = Field(..., description="Message timestamp")
